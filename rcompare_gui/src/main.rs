slint::include_modules!();

use rcompare_common::{
    DiffNode, DiffStatus, FileEntry, SessionProfile, Vfs,
    ThreeWayDiffNode, ThreeWayDiffStatus,
    default_cache_dir, ensure_config, save_config,
};
use rcompare_core::{BinaryDiffEngine, ComparisonEngine, FileOperations, FolderScanner, HashCache};
use rcompare_core::text_diff::{DiffChangeType, DiffLine, HighlightedSegment};
use rcompare_core::TextDiffEngine;
use rcompare_core::image_diff::{ImageDiffEngine, is_image_file};
use rcompare_core::vfs::{SevenZVfs, TarVfs, ZipVfs};
use std::collections::HashSet;
use std::io::Read;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

enum ArchiveKind {
    Zip,
    Tar,
    SevenZ,
}

enum ScanSource {
    Local { root: PathBuf },
    Vfs { vfs: Box<dyn Vfs>, root: PathBuf },
}

const CHANGE_EQUAL: i32 = 0;
const CHANGE_INSERT: i32 = 1;
const CHANGE_DELETE: i32 = 2;

type AnyError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Clone)]
struct CompareRoots {
    left_root: PathBuf,
    right_root: PathBuf,
    left_is_vfs: bool,
    right_is_vfs: bool,
}

struct ComparisonResult {
    left_items: Vec<FileItem>,
    right_items: Vec<FileItem>,
    status: String,
    roots: CompareRoots,
    tree_state: TreeState,
}

#[derive(Clone)]
struct RawTextSegment {
    text: String,
    color: (u8, u8, u8),
    bold: bool,
    italic: bool,
}

#[derive(Clone)]
struct RawTextDiffLine {
    line_left: String,
    line_right: String,
    change: i32,
    segments: Vec<RawTextSegment>,
}

#[derive(Clone)]
struct TreeNode {
    name: String,
    path: PathBuf,
    left: Option<FileEntry>,
    right: Option<FileEntry>,
    status: DiffStatus,
    is_dir: bool,
    children: Vec<TreeNode>,
}

#[derive(Clone)]
struct TreeState {
    root: TreeNode,
    expanded: HashSet<PathBuf>,
}

struct CompareState {
    generation: AtomicU64,
    cancel: Mutex<Option<Arc<AtomicBool>>>,
}

enum TextSide {
    Left,
    Right,
}

#[derive(Clone, Default)]
struct FilterFlags {
    show_identical: bool,
    show_different: bool,
    show_left_only: bool,
    show_right_only: bool,
    search_text: String,
}

impl FilterFlags {
    fn from_ui(ui: &MainWindow) -> Self {
        Self {
            show_identical: ui.get_show_identical(),
            show_different: ui.get_show_different(),
            show_left_only: ui.get_show_left_only(),
            show_right_only: ui.get_show_right_only(),
            search_text: ui.get_search_text().to_string().to_lowercase(),
        }
    }

    fn should_show(&self, status: DiffStatus, name: &str) -> bool {
        let status_match = match status {
            DiffStatus::Same => self.show_identical,
            DiffStatus::Different => self.show_different,
            DiffStatus::OrphanLeft => self.show_left_only,
            DiffStatus::OrphanRight => self.show_right_only,
            DiffStatus::Unchecked => true,
        };

        let search_match = self.search_text.is_empty()
            || name.to_lowercase().contains(&self.search_text);

        status_match && search_match
    }
}

impl ScanSource {
    fn root(&self) -> &std::path::Path {
        match self {
            ScanSource::Local { root } => root.as_path(),
            ScanSource::Vfs { root, .. } => root.as_path(),
        }
    }

    fn vfs(&self) -> Option<&dyn Vfs> {
        match self {
            ScanSource::Vfs { vfs, .. } => Some(vfs.as_ref()),
            _ => None,
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info"))
        )
        .init();

    info!("Starting RCompare GUI");

    let ui = MainWindow::new()?;
    let ui_weak = ui.as_weak();
    let compare_roots: Arc<Mutex<Option<CompareRoots>>> = Arc::new(Mutex::new(None));
    let tree_state: Arc<Mutex<Option<TreeState>>> = Arc::new(Mutex::new(None));
    let compare_state = Arc::new(CompareState {
        generation: AtomicU64::new(0),
        cancel: Mutex::new(None),
    });

    // Set up callbacks
    ui.on_select_left_path({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_folder() {
                    ui.set_left_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_right_path({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_folder() {
                    ui.set_right_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_base_path({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_folder() {
                    ui.set_base_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    // Archive selection callbacks (for right-click context menu)
    ui.on_select_left_archive({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_archive() {
                    ui.set_left_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_right_archive({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_archive() {
                    ui.set_right_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_base_archive({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_archive() {
                    ui.set_base_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_toggle_three_way_mode({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let current = ui.get_three_way_mode();
                ui.set_three_way_mode(!current);
                if !current {
                    ui.set_status_text("Three-way comparison mode enabled. Select a base path.".into());
                } else {
                    ui.set_status_text("Two-way comparison mode.".into());
                    ui.set_base_path("".into());
                }
            }
        }
    });

    ui.on_open_base_item({
        let ui_weak = ui_weak.clone();
        move |_path, _is_dir| {
            if let Some(ui) = ui_weak.upgrade() {
                // For now, just update status - can be expanded later
                ui.set_status_text("Base item selected".into());
            }
        }
    });

    ui.on_compare_clicked({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        let tree_state = tree_state.clone();
        let compare_state = compare_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_path().to_string();
                let right_path = ui.get_right_path().to_string();
                let three_way_mode = ui.get_three_way_mode();
                let base_path = if three_way_mode {
                    let bp = ui.get_base_path().to_string();
                    if bp.is_empty() { None } else { Some(bp) }
                } else {
                    None
                };

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Please select both directories".into());
                    return;
                }

                if three_way_mode && base_path.is_none() {
                    ui.set_status_text("Please select a base directory for three-way comparison".into());
                    return;
                }

                ui.set_status_text("Comparing...".into());
                let (generation, cancel) = start_comparison(&compare_state);
                spawn_comparison(
                    ui_weak.clone(),
                    compare_state.clone(),
                    compare_roots.clone(),
                    tree_state.clone(),
                    left_path,
                    right_path,
                    base_path,
                    generation,
                    cancel,
                );
            }
        }
    });

    ui.on_refresh_clicked({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        let tree_state = tree_state.clone();
        let compare_state = compare_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_path().to_string();
                let right_path = ui.get_right_path().to_string();
                let three_way_mode = ui.get_three_way_mode();
                let base_path = if three_way_mode {
                    let bp = ui.get_base_path().to_string();
                    if bp.is_empty() { None } else { Some(bp) }
                } else {
                    None
                };

                if !left_path.is_empty() && !right_path.is_empty() {
                    ui.set_status_text("Refreshing...".into());
                    let (generation, cancel) = start_comparison(&compare_state);
                    spawn_comparison(
                        ui_weak.clone(),
                        compare_state.clone(),
                        compare_roots.clone(),
                        tree_state.clone(),
                        left_path,
                        right_path,
                        base_path,
                        generation,
                        cancel,
                    );
                }
            }
        }
    });

    ui.on_cancel_clicked({
        let ui_weak = ui_weak.clone();
        let compare_state = compare_state.clone();
        move || {
            if let Ok(guard) = compare_state.cancel.lock() {
                if let Some(flag) = guard.as_ref() {
                    flag.store(true, Ordering::SeqCst);
                }
            }

            if let Some(ui) = ui_weak.upgrade() {
                ui.set_status_text("Canceling...".into());
            }
        }
    });

    ui.on_open_left_item({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        let tree_state = tree_state.clone();
        move |path, is_dir| {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_selected_path(path.clone());
                handle_item_click(
                    TextSide::Left,
                    path.to_string(),
                    &ui,
                    ui_weak.clone(),
                    &compare_roots,
                    &tree_state,
                    is_dir,
                );
            }
        }
    });

    ui.on_open_right_item({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        let tree_state = tree_state.clone();
        move |path, is_dir| {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_selected_path(path.clone());
                handle_item_click(
                    TextSide::Right,
                    path.to_string(),
                    &ui,
                    ui_weak.clone(),
                    &compare_roots,
                    &tree_state,
                    is_dir,
                );
            }
        }
    });

    ui.on_select_left_text({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_left_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_right_text({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_right_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_left_binary({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_left_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_right_binary({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_right_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_left_image({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_left_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_select_right_image({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_text_file() {
                    ui.set_right_text_path(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    ui.on_compare_text_clicked({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_text_path().to_string();
                let right_path = ui.get_right_text_path().to_string();

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Please select both text files".into());
                    return;
                }

                ui.set_status_text("Comparing text...".into());
                spawn_text_diff(ui_weak.clone(), left_path, right_path);
            }
        }
    });

    ui.on_compare_image_clicked({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_text_path().to_string();
                let right_path = ui.get_right_text_path().to_string();

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Please select both image files".into());
                    return;
                }

                let left_buf = PathBuf::from(&left_path);
                let right_buf = PathBuf::from(&right_path);

                if !left_buf.is_file() || !right_buf.is_file() {
                    ui.set_status_text("Selected image files not found on both sides".into());
                    return;
                }

                if !is_image_file(&left_buf) || !is_image_file(&right_buf) {
                    ui.set_status_text("Selected files do not look like images".into());
                    return;
                }

                ui.set_status_text("Comparing images...".into());
                spawn_image_diff(ui_weak.clone(), left_path, right_path);
            }
        }
    });

    ui.on_compare_binary_clicked({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_text_path().to_string();
                let right_path = ui.get_right_text_path().to_string();

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Please select both binary files".into());
                    return;
                }

                ui.set_status_text("Comparing binary files...".into());
                spawn_binary_diff(ui_weak.clone(), left_path, right_path);
            }
        }
    });

    ui.on_new_session({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_left_path("".into());
                ui.set_right_path("".into());
                ui.set_left_items(Rc::new(slint::VecModel::from(Vec::<FileItem>::new())).into());
                ui.set_right_items(Rc::new(slint::VecModel::from(Vec::<FileItem>::new())).into());
                ui.set_status_text("Ready".into());
            }
        }
    });

    ui.on_open_settings({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                // Load current settings
                match ensure_config(false) {
                    Ok(loaded) => {
                        let config = loaded.config;
                        ui.set_settings_ignore_patterns(config.ignore_patterns.join("\n").into());
                        ui.set_settings_follow_symlinks(config.follow_symlinks);
                        ui.set_settings_hash_verification(config.use_hash_verification);
                        ui.set_settings_cache_dir(
                            config.cache_dir.map(|p| p.to_string_lossy().to_string())
                                .unwrap_or_default().into()
                        );
                        ui.set_show_settings(true);
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load settings: {}", e).into());
                    }
                }
            }
        }
    });

    ui.on_save_settings({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                match ensure_config(false) {
                    Ok(mut loaded) => {
                        // Parse ignore patterns
                        let patterns_text = ui.get_settings_ignore_patterns().to_string();
                        loaded.config.ignore_patterns = patterns_text
                            .lines()
                            .map(|s| s.trim().to_string())
                            .filter(|s| !s.is_empty())
                            .collect();

                        loaded.config.follow_symlinks = ui.get_settings_follow_symlinks();
                        loaded.config.use_hash_verification = ui.get_settings_hash_verification();

                        let cache_dir = ui.get_settings_cache_dir().to_string();
                        loaded.config.cache_dir = if cache_dir.is_empty() {
                            None
                        } else {
                            Some(PathBuf::from(cache_dir))
                        };

                        // Save config
                        match rcompare_common::save_config(&loaded.path, &loaded.config) {
                            Ok(_) => {
                                ui.set_status_text("Settings saved".into());
                            }
                            Err(e) => {
                                ui.set_status_text(format!("Failed to save settings: {}", e).into());
                            }
                        }
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load settings: {}", e).into());
                    }
                }
            }
        }
    });

    ui.on_cancel_settings({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_status_text("Settings cancelled".into());
            }
        }
    });

    ui.on_select_cache_dir({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Some(path) = select_folder() {
                    ui.set_settings_cache_dir(path.to_string_lossy().to_string().into());
                }
            }
        }
    });

    // Profile management callbacks
    ui.on_open_profiles({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                match ensure_config(false) {
                    Ok(loaded) => {
                        let profile_items = profiles_to_ui_items(&loaded.config.profiles);
                        ui.set_profiles(Rc::new(slint::VecModel::from(profile_items)).into());
                        ui.set_selected_profile_index(-1);
                        ui.set_new_profile_name("".into());
                        ui.set_show_profiles(true);
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load profiles: {}", e).into());
                    }
                }
            }
        }
    });

    ui.on_close_profiles({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_show_profiles(false);
            }
        }
    });

    ui.on_save_current_profile({
        let ui_weak = ui_weak.clone();
        move |name| {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_path().to_string();
                let right_path = ui.get_right_path().to_string();

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Cannot save profile: paths not set".into());
                    return false;
                }

                match ensure_config(false) {
                    Ok(mut loaded) => {
                        // Create new profile
                        let now = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs())
                            .unwrap_or(0);

                        let profile = SessionProfile {
                            name: name.to_string(),
                            left_path: PathBuf::from(&left_path),
                            right_path: PathBuf::from(&right_path),
                            ignore_patterns: vec![],
                            last_used: now,
                        };

                        loaded.config.profiles.push(profile);

                        // Save config
                        match save_config(&loaded.path, &loaded.config) {
                            Ok(_) => {
                                // Refresh profiles list
                                let profile_items = profiles_to_ui_items(&loaded.config.profiles);
                                ui.set_profiles(Rc::new(slint::VecModel::from(profile_items)).into());
                                ui.set_status_text(format!("Profile '{}' saved", name).into());
                                return true;
                            }
                            Err(e) => {
                                ui.set_status_text(format!("Failed to save profile: {}", e).into());
                                return false;
                            }
                        }
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load config: {}", e).into());
                        return false;
                    }
                }
            }
            false
        }
    });

    ui.on_load_profile({
        let ui_weak = ui_weak.clone();
        move |index| {
            if let Some(ui) = ui_weak.upgrade() {
                if index < 0 {
                    return;
                }

                match ensure_config(false) {
                    Ok(mut loaded) => {
                        let idx = index as usize;
                        if idx >= loaded.config.profiles.len() {
                            return;
                        }

                        // Update last_used
                        let now = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs())
                            .unwrap_or(0);
                        loaded.config.profiles[idx].last_used = now;

                        let profile = &loaded.config.profiles[idx];
                        let left_path = profile.left_path.to_string_lossy().to_string();
                        let right_path = profile.right_path.to_string_lossy().to_string();
                        let name = profile.name.clone();

                        // Save updated last_used
                        let _ = save_config(&loaded.path, &loaded.config);

                        // Set paths in UI
                        ui.set_left_path(left_path.clone().into());
                        ui.set_right_path(right_path.clone().into());
                        ui.set_status_text(format!("Loaded profile '{}' - click Compare to scan", name).into());
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load profile: {}", e).into());
                    }
                }
            }
        }
    });

    ui.on_delete_profile({
        let ui_weak = ui_weak.clone();
        move |index| {
            if let Some(ui) = ui_weak.upgrade() {
                if index < 0 {
                    return;
                }

                match ensure_config(false) {
                    Ok(mut loaded) => {
                        let idx = index as usize;
                        if idx >= loaded.config.profiles.len() {
                            return;
                        }

                        let name = loaded.config.profiles[idx].name.clone();
                        loaded.config.profiles.remove(idx);

                        // Save config
                        match save_config(&loaded.path, &loaded.config) {
                            Ok(_) => {
                                // Refresh profiles list
                                let profile_items = profiles_to_ui_items(&loaded.config.profiles);
                                ui.set_profiles(Rc::new(slint::VecModel::from(profile_items)).into());
                                ui.set_status_text(format!("Profile '{}' deleted", name).into());
                            }
                            Err(e) => {
                                ui.set_status_text(format!("Failed to delete profile: {}", e).into());
                            }
                        }
                    }
                    Err(e) => {
                        ui.set_status_text(format!("Failed to load config: {}", e).into());
                    }
                }
            }
        }
    });

    ui.on_validate_profile_name({
        let ui_weak = ui_weak.clone();
        move |name| {
            if let Some(_ui) = ui_weak.upgrade() {
                let name_str = name.to_string();

                // Check if name is empty
                if name_str.is_empty() {
                    return "Profile name cannot be empty".into();
                }

                // Check for invalid characters (basic validation)
                if name_str.contains('/') || name_str.contains('\\') || name_str.contains(':') {
                    return "Profile name contains invalid characters".into();
                }

                // Check length
                if name_str.len() > 100 {
                    return "Profile name is too long (max 100 characters)".into();
                }

                // Check for duplicates
                match ensure_config(false) {
                    Ok(loaded) => {
                        if loaded.config.profiles.iter().any(|p| p.name == name_str) {
                            return "A profile with this name already exists".into();
                        }
                    }
                    Err(_) => {
                        // If we can't load config, allow the name
                    }
                }

                // Name is valid
                "".into()
            } else {
                "".into()
            }
        }
    });

    ui.on_exit_application({
        move || {
            std::process::exit(0);
        }
    });

    // Sync callbacks
    ui.on_open_sync_dialog({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let left_path = ui.get_left_path().to_string();
                let right_path = ui.get_right_path().to_string();

                if left_path.is_empty() || right_path.is_empty() {
                    ui.set_status_text("Please select both directories first".into());
                    return;
                }

                ui.set_show_sync_dialog(true);
            }
        }
    });

    ui.on_close_sync_dialog({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_show_sync_dialog(false);
            }
        }
    });

    ui.on_execute_sync({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        let tree_state = tree_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let sync_mode = ui.get_sync_mode();
                let dry_run = ui.get_sync_dry_run();
                let use_trash = ui.get_sync_use_trash();

                let roots = {
                    let guard = compare_roots.lock().ok();
                    guard.and_then(|g| g.clone())
                };

                let tree = {
                    let guard = tree_state.lock().ok();
                    guard.and_then(|g| g.clone())
                };

                if roots.is_none() || tree.is_none() {
                    ui.set_status_text("Please run a comparison first".into());
                    return;
                }

                let roots = roots.unwrap();
                let tree = tree.unwrap();

                ui.set_show_sync_dialog(false);
                ui.set_status_text("Syncing...".into());

                // Spawn sync operation
                let ui_weak = ui_weak.clone();
                std::thread::spawn(move || {
                    let result = execute_sync_operation(
                        &roots,
                        &tree.root,
                        sync_mode,
                        dry_run,
                        use_trash,
                    );

                    let _ = slint::invoke_from_event_loop(move || {
                        if let Some(ui) = ui_weak.upgrade() {
                            match result {
                                Ok(msg) => ui.set_status_text(msg.into()),
                                Err(e) => ui.set_status_text(format!("Sync error: {}", e).into()),
                            }
                        }
                    });
                });
            }
        }
    });

    ui.on_expand_all({
        let ui_weak = ui_weak.clone();
        let tree_state = tree_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Ok(mut guard) = tree_state.lock() {
                    if let Some(state) = guard.as_mut() {
                        expand_all_dirs(&state.root, &mut state.expanded);
                        let filters = FilterFlags::from_ui(&ui);
                        let (left_items, right_items) = flatten_tree_filtered(&state.root, &state.expanded, &filters);
                        ui.set_left_items(Rc::new(slint::VecModel::from(left_items)).into());
                        ui.set_right_items(Rc::new(slint::VecModel::from(right_items)).into());
                        ui.set_status_text("All folders expanded".into());
                    }
                }
            }
        }
    });

    ui.on_collapse_all({
        let ui_weak = ui_weak.clone();
        let tree_state = tree_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Ok(mut guard) = tree_state.lock() {
                    if let Some(state) = guard.as_mut() {
                        state.expanded.clear();
                        let filters = FilterFlags::from_ui(&ui);
                        let (left_items, right_items) = flatten_tree_filtered(&state.root, &state.expanded, &filters);
                        ui.set_left_items(Rc::new(slint::VecModel::from(left_items)).into());
                        ui.set_right_items(Rc::new(slint::VecModel::from(right_items)).into());
                        ui.set_status_text("All folders collapsed".into());
                    }
                }
            }
        }
    });

    ui.on_copy_left_to_right({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let selected = ui.get_selected_path().to_string();
                if selected.is_empty() {
                    ui.set_status_text("No file selected".into());
                    return;
                }

                let roots = match compare_roots.lock() {
                    Ok(guard) => guard.clone(),
                    Err(_) => None,
                };

                let Some(roots) = roots else {
                    ui.set_status_text("Run comparison first".into());
                    return;
                };

                if roots.left_is_vfs || roots.right_is_vfs {
                    ui.set_status_text("Copy not supported for archives".into());
                    return;
                }

                let source = roots.left_root.join(&selected);
                let dest = roots.right_root.join(&selected);

                if !source.exists() {
                    ui.set_status_text("Source file does not exist on left side".into());
                    return;
                }

                ui.set_status_text(format!("Copying {}...", selected).into());
                let ui_weak_clone = ui_weak.clone();

                std::thread::spawn(move || {
                    let ops = FileOperations::new(false, false);
                    let result = if source.is_dir() {
                        copy_directory_recursive(&ops, &source, &dest)
                    } else {
                        ops.copy_file(&source, &dest).map(|r| r.bytes_processed)
                    };

                    let _ = slint::invoke_from_event_loop(move || {
                        if let Some(ui) = ui_weak_clone.upgrade() {
                            match result {
                                Ok(bytes) => {
                                    ui.set_status_text(format!("Copied {} bytes", bytes).into());
                                }
                                Err(e) => {
                                    ui.set_status_text(format!("Copy failed: {}", e).into());
                                }
                            }
                        }
                    });
                });
            }
        }
    });

    ui.on_copy_right_to_left({
        let ui_weak = ui_weak.clone();
        let compare_roots = compare_roots.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                let selected = ui.get_selected_path().to_string();
                if selected.is_empty() {
                    ui.set_status_text("No file selected".into());
                    return;
                }

                let roots = match compare_roots.lock() {
                    Ok(guard) => guard.clone(),
                    Err(_) => None,
                };

                let Some(roots) = roots else {
                    ui.set_status_text("Run comparison first".into());
                    return;
                };

                if roots.left_is_vfs || roots.right_is_vfs {
                    ui.set_status_text("Copy not supported for archives".into());
                    return;
                }

                let source = roots.right_root.join(&selected);
                let dest = roots.left_root.join(&selected);

                if !source.exists() {
                    ui.set_status_text("Source file does not exist on right side".into());
                    return;
                }

                ui.set_status_text(format!("Copying {}...", selected).into());
                let ui_weak_clone = ui_weak.clone();

                std::thread::spawn(move || {
                    let ops = FileOperations::new(false, false);
                    let result = if source.is_dir() {
                        copy_directory_recursive(&ops, &source, &dest)
                    } else {
                        ops.copy_file(&source, &dest).map(|r| r.bytes_processed)
                    };

                    let _ = slint::invoke_from_event_loop(move || {
                        if let Some(ui) = ui_weak_clone.upgrade() {
                            match result {
                                Ok(bytes) => {
                                    ui.set_status_text(format!("Copied {} bytes", bytes).into());
                                }
                                Err(e) => {
                                    ui.set_status_text(format!("Copy failed: {}", e).into());
                                }
                            }
                        }
                    });
                });
            }
        }
    });

    ui.on_show_about({
        let ui_weak = ui_weak.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                ui.set_status_text("RCompare v0.1.0 - High-performance file comparison tool".into());
            }
        }
    });

    ui.on_filter_changed({
        let ui_weak = ui_weak.clone();
        let tree_state = tree_state.clone();
        move || {
            if let Some(ui) = ui_weak.upgrade() {
                if let Ok(guard) = tree_state.lock() {
                    if let Some(state) = guard.as_ref() {
                        let filters = FilterFlags::from_ui(&ui);
                        let (left_items, right_items) = flatten_tree_filtered(
                            &state.root,
                            &state.expanded,
                            &filters,
                        );
                        let visible_count = left_items.len();
                        ui.set_left_items(Rc::new(slint::VecModel::from(left_items)).into());
                        ui.set_right_items(Rc::new(slint::VecModel::from(right_items)).into());
                        ui.set_status_text(format!("Showing {} items", visible_count).into());
                    }
                }
            }
        }
    });

    ui.run()?;
    Ok(())
}

fn spawn_comparison(
    ui_weak: slint::Weak<MainWindow>,
    compare_state: Arc<CompareState>,
    compare_roots: Arc<Mutex<Option<CompareRoots>>>,
    tree_state: Arc<Mutex<Option<TreeState>>>,
    left_path: String,
    right_path: String,
    base_path: Option<String>,
    generation: u64,
    cancel: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        let result = run_comparison(&left_path, &right_path, base_path.as_deref(), Some(cancel.as_ref()));

        let _ = slint::invoke_from_event_loop(move || {
            if compare_state.generation.load(Ordering::SeqCst) != generation {
                return;
            }
            if cancel.load(Ordering::SeqCst) {
                return;
            }

            if let Some(ui) = ui_weak.upgrade() {
                match result {
                    Ok(result) => {
                        ui.set_left_items(Rc::new(slint::VecModel::from(result.left_items)).into());
                        ui.set_right_items(Rc::new(slint::VecModel::from(result.right_items)).into());
                        ui.set_status_text(result.status.into());

                        if let Ok(mut roots) = compare_roots.lock() {
                            *roots = Some(result.roots);
                        }
                        if let Ok(mut state) = tree_state.lock() {
                            *state = Some(result.tree_state);
                        }
                    }
                    Err(e) => {
                        error!("Comparison failed: {}", e);
                        ui.set_status_text(format!("Error: {}", e).into());
                    }
                }
            }
        });
    });
}

fn spawn_text_diff(
    ui_weak: slint::Weak<MainWindow>,
    left_path: String,
    right_path: String,
) {
    std::thread::spawn(move || {
        let result = run_text_diff(&left_path, &right_path);

        let _ = slint::invoke_from_event_loop(move || {
            if let Some(ui) = ui_weak.upgrade() {
                match result {
                    Ok(lines) => {
                        let ui_lines = to_ui_text_lines(lines);
                        ui.set_text_lines(Rc::new(slint::VecModel::from(ui_lines)).into());
                        ui.set_status_text("Text diff ready".into());
                    }
                    Err(e) => {
                        error!("Text diff failed: {}", e);
                        ui.set_status_text(format!("Error: {}", e).into());
                    }
                }
            }
        });
    });
}

fn spawn_binary_diff(
    ui_weak: slint::Weak<MainWindow>,
    left_path: String,
    right_path: String,
) {
    std::thread::spawn(move || {
        let result = run_binary_diff(&left_path, &right_path);

        let _ = slint::invoke_from_event_loop(move || {
            if let Some(ui) = ui_weak.upgrade() {
                match result {
                    Ok(lines) => {
                        let diff_count = lines.iter().filter(|l| l.has_diff).count();
                        ui.set_hex_lines(Rc::new(slint::VecModel::from(lines)).into());
                        ui.set_status_text(format!("Binary diff ready - {} differences found", diff_count).into());
                    }
                    Err(e) => {
                        error!("Binary diff failed: {}", e);
                        ui.set_status_text(format!("Error: {}", e).into());
                    }
                }
            }
        });
    });
}

fn run_binary_diff(left: &str, right: &str) -> Result<Vec<HexDiffLine>, AnyError> {
    let left_path = PathBuf::from(left);
    let right_path = PathBuf::from(right);

    if !left_path.exists() {
        return Err(format!("Left file does not exist: {}", left).into());
    }
    if !right_path.exists() {
        return Err(format!("Right file does not exist: {}", right).into());
    }

    let engine = BinaryDiffEngine::new(256); // 256 bytes per chunk (16 lines)
    let chunks = engine.compare_files(&left_path, &right_path)?;

    let mut hex_lines = Vec::new();
    for chunk in chunks {
        // Process 16 bytes per line
        let max_len = chunk.left_data.len().max(chunk.right_data.len());
        let lines_in_chunk = (max_len + 15) / 16;

        for line_idx in 0..lines_in_chunk {
            let start = line_idx * 16;
            let end = (start + 16).min(max_len);
            let offset = chunk.offset + start as u64;

            let left_slice = if start < chunk.left_data.len() {
                &chunk.left_data[start..end.min(chunk.left_data.len())]
            } else {
                &[]
            };

            let right_slice = if start < chunk.right_data.len() {
                &chunk.right_data[start..end.min(chunk.right_data.len())]
            } else {
                &[]
            };

            // Check if this line has differences
            let has_diff = chunk.differences.iter().any(|&idx| idx >= start && idx < end);

            hex_lines.push(HexDiffLine {
                offset: format!("{:08X}", offset).into(),
                left_hex: format_hex_bytes(left_slice).into(),
                right_hex: format_hex_bytes(right_slice).into(),
                left_ascii: format_ascii_bytes(left_slice).into(),
                right_ascii: format_ascii_bytes(right_slice).into(),
                has_diff,
            });
        }
    }

    Ok(hex_lines)
}

fn spawn_image_diff(
    ui_weak: slint::Weak<MainWindow>,
    left_path: String,
    right_path: String,
) {
    std::thread::spawn(move || {
        let result = run_image_diff(&left_path, &right_path);

        let _ = slint::invoke_from_event_loop(move || {
            if let Some(ui) = ui_weak.upgrade() {
                match result {
                    Ok(diff_result) => {
                        ui.set_image_diff_result(diff_result);
                        ui.set_active_view(3); // Switch to image view
                        ui.set_status_text("Image comparison complete".into());
                    }
                    Err(e) => {
                        error!("Image diff failed: {}", e);
                        ui.set_status_text(format!("Error: {}", e).into());
                    }
                }
            }
        });
    });
}

fn run_image_diff(left: &str, right: &str) -> Result<ImageDiffResult, AnyError> {
    let left_path = PathBuf::from(left);
    let right_path = PathBuf::from(right);

    if !left_path.exists() {
        return Err(format!("Left image does not exist: {}", left).into());
    }
    if !right_path.exists() {
        return Err(format!("Right image does not exist: {}", right).into());
    }

    let engine = ImageDiffEngine::new();
    let result = engine.compare_files(&left_path, &right_path)?;

    Ok(ImageDiffResult {
        total_pixels: result.total_pixels as i32,
        different_pixels: result.different_pixels as i32,
        difference_percentage: result.difference_percentage as f32,
        mean_diff: result.mean_diff as f32,
        same_dimensions: result.same_dimensions,
        left_width: result.left_dimensions.0 as i32,
        left_height: result.left_dimensions.1 as i32,
        right_width: result.right_dimensions.0 as i32,
        right_height: result.right_dimensions.1 as i32,
        left_path: left.into(),
        right_path: right.into(),
    })
}

fn format_hex_bytes(data: &[u8]) -> String {
    let mut result = String::new();
    for (i, byte) in data.iter().enumerate() {
        if i == 8 {
            result.push(' ');
        }
        result.push_str(&format!("{:02X} ", byte));
    }
    // Pad if less than 16 bytes
    for i in data.len()..16 {
        if i == 8 {
            result.push(' ');
        }
        result.push_str("   ");
    }
    result
}

fn format_ascii_bytes(data: &[u8]) -> String {
    data.iter()
        .map(|&b| if b >= 0x20 && b < 0x7F { b as char } else { '.' })
        .collect()
}

fn start_comparison(compare_state: &Arc<CompareState>) -> (u64, Arc<AtomicBool>) {
    let generation = compare_state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let cancel = Arc::new(AtomicBool::new(false));

    if let Ok(mut guard) = compare_state.cancel.lock() {
        if let Some(old) = guard.replace(cancel.clone()) {
            old.store(true, Ordering::SeqCst);
        }
    }

    (generation, cancel)
}

fn run_comparison(
    left: &str,
    right: &str,
    base: Option<&str>,
    cancel: Option<&AtomicBool>,
) -> Result<ComparisonResult, AnyError> {
    let left_path = PathBuf::from(left);
    let right_path = PathBuf::from(right);

    if !left_path.exists() {
        return Err(format!("Left path does not exist: {}", left).into());
    }
    if !right_path.exists() {
        return Err(format!("Right path does not exist: {}", right).into());
    }

    let loaded = ensure_config(false)?;
    let config = loaded.config;
    let verify_hashes = config.use_hash_verification;

    // Determine cache directory
    let cache_path = match config.cache_dir.clone() {
        Some(path) => path,
        None => default_cache_dir(loaded.portable, &loaded.path)?,
    };

    let hash_cache = HashCache::new(cache_path)?;
    let mut scanner = FolderScanner::new(config);

    if left_path.is_dir() {
        let _ = scanner.load_gitignore(&left_path);
    }

    info!("Scanning left directory...");
    let left_source = build_scan_source(&left_path)?;
    let right_source = build_scan_source(&right_path)?;

    let left_entries = scan_source(&scanner, &left_source, cancel)?;
    info!("Found {} entries in left directory", left_entries.len());

    info!("Scanning right directory...");
    let right_entries = scan_source(&scanner, &right_source, cancel)?;
    info!("Found {} entries in right directory", right_entries.len());

    let comparison_engine = ComparisonEngine::new(hash_cache)
        .with_hash_verification(verify_hashes);

    // Check if three-way comparison
    if let Some(base_str) = base {
        let base_path = PathBuf::from(base_str);
        if !base_path.exists() {
            return Err(format!("Base path does not exist: {}", base_str).into());
        }

        info!("Scanning base directory...");
        let base_source = build_scan_source(&base_path)?;
        let base_entries = scan_source(&scanner, &base_source, cancel)?;
        info!("Found {} entries in base directory", base_entries.len());

        info!("Performing three-way comparison...");
        let three_way_nodes = comparison_engine.compare_three_way_with_vfs(
            base_source.root(),
            left_source.root(),
            right_source.root(),
            base_entries,
            left_entries,
            right_entries,
            base_source.vfs(),
            left_source.vfs(),
            right_source.vfs(),
        )?;
        comparison_engine.persist_cache()?;

        // Count statuses
        let mut all_same = 0;
        let mut left_changed = 0;
        let mut right_changed = 0;
        let mut both_changed = 0;

        for node in &three_way_nodes {
            match node.status {
                ThreeWayDiffStatus::AllSame => all_same += 1,
                ThreeWayDiffStatus::LeftChanged => left_changed += 1,
                ThreeWayDiffStatus::RightChanged => right_changed += 1,
                ThreeWayDiffStatus::BothChanged | ThreeWayDiffStatus::BothAdded => both_changed += 1,
                _ => {}
            }
        }

        let tree_state = build_tree_state_from_three_way(three_way_nodes);
        let (left_items, right_items) = flatten_tree(&tree_state.root, &tree_state.expanded);

        let status = format!(
            "Three-way | Same: {} | Left changed: {} | Right changed: {} | Both changed: {}",
            all_same, left_changed, right_changed, both_changed
        );

        return Ok(ComparisonResult {
            left_items,
            right_items,
            status,
            roots: CompareRoots {
                left_root: left_source.root().to_path_buf(),
                right_root: right_source.root().to_path_buf(),
                left_is_vfs: left_source.vfs().is_some(),
                right_is_vfs: right_source.vfs().is_some(),
            },
            tree_state,
        });
    }

    // Two-way comparison
    info!("Comparing directories...");
    let diff_nodes = comparison_engine.compare_with_vfs_and_cancel(
        left_source.root(),
        right_source.root(),
        left_entries,
        right_entries,
        left_source.vfs(),
        right_source.vfs(),
        cancel,
    )?;
    comparison_engine.persist_cache()?;

    let mut same_count = 0;
    let mut different_count = 0;
    let mut orphan_left_count = 0;
    let mut orphan_right_count = 0;

    for node in &diff_nodes {
        match node.status {
            DiffStatus::Same => same_count += 1,
            DiffStatus::Different => different_count += 1,
            DiffStatus::OrphanLeft => orphan_left_count += 1,
            DiffStatus::OrphanRight => orphan_right_count += 1,
            DiffStatus::Unchecked => {}
        }
    }

    let tree_state = build_tree_state(diff_nodes);
    let (left_items, right_items) = flatten_tree(&tree_state.root, &tree_state.expanded);

    let status = format!(
        "Total: {} | Same: {} | Different: {} | Left only: {} | Right only: {}",
        left_items.len().max(right_items.len()),
        same_count,
        different_count,
        orphan_left_count,
        orphan_right_count
    );

    Ok(ComparisonResult {
        left_items,
        right_items,
        status,
        roots: CompareRoots {
            left_root: left_source.root().to_path_buf(),
            right_root: right_source.root().to_path_buf(),
            left_is_vfs: left_source.vfs().is_some(),
            right_is_vfs: right_source.vfs().is_some(),
        },
        tree_state,
    })
}

fn run_text_diff(
    left: &str,
    right: &str,
) -> Result<Vec<RawTextDiffLine>, AnyError> {
    let left_path = PathBuf::from(left);
    let right_path = PathBuf::from(right);

    if !left_path.is_file() {
        return Err(format!("Left path is not a file: {}", left).into());
    }
    if !right_path.is_file() {
        return Err(format!("Right path is not a file: {}", right).into());
    }

    let left_content = std::fs::read_to_string(&left_path)?;
    let right_content = std::fs::read_to_string(&right_path)?;

    let engine = TextDiffEngine::new();
    let diff_lines = engine.compare_text_patience(&left_content, &right_content, &left_path)?;

    Ok(build_raw_text_lines(diff_lines))
}

fn handle_item_click(
    _side: TextSide,
    rel_path: String,
    ui: &MainWindow,
    ui_weak: slint::Weak<MainWindow>,
    compare_roots: &Arc<Mutex<Option<CompareRoots>>>,
    tree_state: &Arc<Mutex<Option<TreeState>>>,
    is_dir: bool,
) {
    if is_dir {
        if let Ok(mut guard) = tree_state.lock() {
            if let Some(state) = guard.as_mut() {
                let path = PathBuf::from(&rel_path);
                if state.expanded.contains(&path) {
                    state.expanded.remove(&path);
                } else {
                    state.expanded.insert(path);
                }

                let filters = FilterFlags::from_ui(ui);
                let (left_items, right_items) = flatten_tree_filtered(&state.root, &state.expanded, &filters);
                ui.set_left_items(Rc::new(slint::VecModel::from(left_items)).into());
                ui.set_right_items(Rc::new(slint::VecModel::from(right_items)).into());
            }
        }
        return;
    }

    let roots = match compare_roots.lock() {
        Ok(guard) => guard.clone(),
        Err(_) => None,
    };

    let Some(roots) = roots else {
        ui.set_status_text("Run folder comparison first".into());
        return;
    };

    if roots.left_is_vfs || roots.right_is_vfs {
        ui.set_status_text("Text diff not available for archive comparisons".into());
        return;
    }

    let rel = PathBuf::from(rel_path);
    let left_path = roots.left_root.join(&rel);
    let right_path = roots.right_root.join(&rel);

    let left_ok = left_path.is_file();
    let right_ok = right_path.is_file();

    if left_ok {
        ui.set_left_text_path(left_path.to_string_lossy().to_string().into());
    } else {
        ui.set_left_text_path("".into());
    }

    if right_ok {
        ui.set_right_text_path(right_path.to_string_lossy().to_string().into());
    } else {
        ui.set_right_text_path("".into());
    }

    // Check if files are images
    let left_is_image = left_ok && is_image_file(&left_path);
    let right_is_image = right_ok && is_image_file(&right_path);

    if left_is_image || right_is_image {
        if left_ok && right_ok {
            ui.set_status_text("Comparing images...".into());
            spawn_image_diff(
                ui_weak,
                left_path.to_string_lossy().to_string(),
                right_path.to_string_lossy().to_string(),
            );
        } else {
            ui.set_status_text("Matching image file not found on both sides".into());
        }
        return;
    }

    if left_ok && !is_probably_text_file(&left_path) {
        ui.set_text_lines(Rc::new(slint::VecModel::from(Vec::new())).into());
        ui.set_status_text("Left file does not look like text; diff skipped".into());
        return;
    }

    if right_ok && !is_probably_text_file(&right_path) {
        ui.set_text_lines(Rc::new(slint::VecModel::from(Vec::new())).into());
        ui.set_status_text("Right file does not look like text; diff skipped".into());
        return;
    }

    if left_ok && right_ok {
        spawn_text_diff(
            ui_weak,
            left_path.to_string_lossy().to_string(),
            right_path.to_string_lossy().to_string(),
        );
    } else {
        ui.set_status_text("Matching text file not found on both sides".into());
    }
}

fn build_tree_state(diff_nodes: Vec<DiffNode>) -> TreeState {
    let mut root = TreeNode {
        name: String::new(),
        path: PathBuf::new(),
        left: None,
        right: None,
        status: DiffStatus::Same,
        is_dir: true,
        children: Vec::new(),
    };

    for diff in diff_nodes {
        insert_diff_node(&mut root, diff);
    }

    aggregate_status(&mut root);
    sort_children(&mut root);

    let mut expanded = HashSet::new();
    collect_dir_paths(&root, &mut expanded);

    TreeState { root, expanded }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gui_smoke_test() {
        if std::env::var_os("RCOMPARE_GUI_SMOKE_TEST").is_none() {
            eprintln!("Skipping GUI smoke test: set RCOMPARE_GUI_SMOKE_TEST=1 to enable");
            return;
        }

        if let Err(err) = MainWindow::new() {
            panic!("Failed to create MainWindow: {err}");
        }
    }
}

fn build_tree_state_from_three_way(diff_nodes: Vec<ThreeWayDiffNode>) -> TreeState {
    let mut root = TreeNode {
        name: String::new(),
        path: PathBuf::new(),
        left: None,
        right: None,
        status: DiffStatus::Same,
        is_dir: true,
        children: Vec::new(),
    };

    for diff in diff_nodes {
        insert_three_way_diff_node(&mut root, diff);
    }

    aggregate_status(&mut root);
    sort_children(&mut root);

    let mut expanded = HashSet::new();
    collect_dir_paths(&root, &mut expanded);

    TreeState { root, expanded }
}

fn insert_three_way_diff_node(root: &mut TreeNode, diff: ThreeWayDiffNode) {
    let ThreeWayDiffNode {
        relative_path,
        base: _,  // Base is not displayed in current UI
        left,
        right,
        status,
    } = diff;

    // Map three-way status to two-way status for display
    let display_status = match status {
        ThreeWayDiffStatus::AllSame => DiffStatus::Same,
        ThreeWayDiffStatus::LeftChanged => DiffStatus::Different,
        ThreeWayDiffStatus::RightChanged => DiffStatus::Different,
        ThreeWayDiffStatus::BothChanged => DiffStatus::Different,
        ThreeWayDiffStatus::BaseOnly => DiffStatus::Unchecked,
        ThreeWayDiffStatus::LeftOnly => DiffStatus::OrphanLeft,
        ThreeWayDiffStatus::RightOnly => DiffStatus::OrphanRight,
        ThreeWayDiffStatus::BothAdded => DiffStatus::Different,
        ThreeWayDiffStatus::BaseAndLeft => DiffStatus::OrphanLeft,
        ThreeWayDiffStatus::BaseAndRight => DiffStatus::OrphanRight,
    };

    let components: Vec<String> = relative_path
        .iter()
        .map(|part| part.to_string_lossy().to_string())
        .collect();

    if components.is_empty() {
        return;
    }

    let mut left_entry = left;
    let mut right_entry = right;

    insert_components(root, &components, &mut left_entry, &mut right_entry, display_status);
}

fn insert_diff_node(root: &mut TreeNode, diff: DiffNode) {
    let DiffNode {
        relative_path,
        left,
        right,
        status,
    } = diff;

    let components: Vec<String> = relative_path
        .iter()
        .map(|part| part.to_string_lossy().to_string())
        .collect();

    if components.is_empty() {
        return;
    }

    let mut left_entry = left;
    let mut right_entry = right;

    insert_components(root, &components, &mut left_entry, &mut right_entry, status);
}

fn insert_components(
    node: &mut TreeNode,
    components: &[String],
    left: &mut Option<FileEntry>,
    right: &mut Option<FileEntry>,
    status: DiffStatus,
) {
    let name = &components[0];
    let child = get_or_create_child(node, name);

    if components.len() == 1 {
        child.left = left.take();
        child.right = right.take();
        child.status = status;
        child.is_dir = child.left.as_ref().map(|e| e.is_dir).unwrap_or(false)
            || child.right.as_ref().map(|e| e.is_dir).unwrap_or(false);
    } else {
        insert_components(child, &components[1..], left, right, status);
    }
}

fn get_or_create_child<'a>(node: &'a mut TreeNode, name: &str) -> &'a mut TreeNode {
    if let Some(index) = node.children.iter().position(|child| child.name == name) {
        return &mut node.children[index];
    }

    let path = node.path.join(name);
    node.children.push(TreeNode {
        name: name.to_string(),
        path,
        left: None,
        right: None,
        status: DiffStatus::Same,
        is_dir: true,
        children: Vec::new(),
    });

    let last = node.children.len() - 1;
    &mut node.children[last]
}

fn aggregate_status(node: &mut TreeNode) -> DiffStatus {
    let mut has_diff = false;
    let mut has_unchecked = false;

    for child in node.children.iter_mut() {
        let status = aggregate_status(child);
        match status {
            DiffStatus::Different | DiffStatus::OrphanLeft | DiffStatus::OrphanRight => {
                has_diff = true;
            }
            DiffStatus::Unchecked => {
                has_unchecked = true;
            }
            DiffStatus::Same => {}
        }
    }

    if node.is_dir {
        node.status = match node.status {
            DiffStatus::OrphanLeft | DiffStatus::OrphanRight | DiffStatus::Different => node.status,
            DiffStatus::Same | DiffStatus::Unchecked => {
                if has_diff {
                    DiffStatus::Different
                } else if has_unchecked {
                    DiffStatus::Unchecked
                } else {
                    DiffStatus::Same
                }
            }
        };
    }

    node.status
}

fn sort_children(node: &mut TreeNode) {
    node.children.sort_by(|a, b| {
        match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    for child in node.children.iter_mut() {
        sort_children(child);
    }
}

fn collect_dir_paths(node: &TreeNode, expanded: &mut HashSet<PathBuf>) {
    if node.is_dir && !node.path.as_os_str().is_empty() {
        expanded.insert(node.path.clone());
    }

    for child in &node.children {
        collect_dir_paths(child, expanded);
    }
}

fn expand_all_dirs(node: &TreeNode, expanded: &mut HashSet<PathBuf>) {
    if node.is_dir && !node.path.as_os_str().is_empty() {
        expanded.insert(node.path.clone());
    }

    for child in &node.children {
        if child.is_dir {
            expand_all_dirs(child, expanded);
        }
    }
}

fn flatten_tree(root: &TreeNode, expanded: &HashSet<PathBuf>) -> (Vec<FileItem>, Vec<FileItem>) {
    let default_filter = FilterFlags {
        show_identical: true,
        show_different: true,
        show_left_only: true,
        show_right_only: true,
        search_text: String::new(),
    };
    flatten_tree_filtered(root, expanded, &default_filter)
}

fn flatten_tree_filtered(
    root: &TreeNode,
    expanded: &HashSet<PathBuf>,
    filters: &FilterFlags,
) -> (Vec<FileItem>, Vec<FileItem>) {
    let mut left_items = Vec::new();
    let mut right_items = Vec::new();

    for child in &root.children {
        flatten_node_filtered(child, 0, expanded, filters, &mut left_items, &mut right_items);
    }

    (left_items, right_items)
}

fn flatten_node_filtered(
    node: &TreeNode,
    depth: i32,
    expanded: &HashSet<PathBuf>,
    filters: &FilterFlags,
    left_items: &mut Vec<FileItem>,
    right_items: &mut Vec<FileItem>,
) {
    // For directories, check if any visible children exist
    let should_show = if node.is_dir {
        // Always show directories if they have visible children or match search
        has_visible_children(node, filters) || filters.search_text.is_empty()
            || node.name.to_lowercase().contains(&filters.search_text)
    } else {
        filters.should_show(node.status, &node.name)
    };

    if !should_show {
        return;
    }

    let path = node.path.to_string_lossy().to_string();
    let is_expanded = node.is_dir && expanded.contains(&node.path);
    left_items.push(build_file_item(
        node,
        node.left.as_ref(),
        depth,
        &path,
        is_expanded,
    ));
    right_items.push(build_file_item(
        node,
        node.right.as_ref(),
        depth,
        &path,
        is_expanded,
    ));

    if node.is_dir && expanded.contains(&node.path) {
        for child in &node.children {
            flatten_node_filtered(child, depth + 1, expanded, filters, left_items, right_items);
        }
    }
}

fn has_visible_children(node: &TreeNode, filters: &FilterFlags) -> bool {
    for child in &node.children {
        if child.is_dir {
            if has_visible_children(child, filters) {
                return true;
            }
        } else if filters.should_show(child.status, &child.name) {
            return true;
        }
    }
    false
}

fn copy_directory_recursive(
    ops: &FileOperations,
    source: &std::path::Path,
    dest: &std::path::Path,
) -> Result<u64, rcompare_common::RCompareError> {
    use std::fs;

    let mut total_bytes = 0u64;

    // Create destination directory
    fs::create_dir_all(dest)?;

    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dest.join(entry.file_name());

        if file_type.is_dir() {
            total_bytes += copy_directory_recursive(ops, &src_path, &dst_path)?;
        } else if file_type.is_file() {
            let result = ops.copy_file(&src_path, &dst_path)?;
            total_bytes += result.bytes_processed;
        }
    }

    Ok(total_bytes)
}

fn build_file_item(
    node: &TreeNode,
    entry: Option<&FileEntry>,
    depth: i32,
    path: &str,
    expanded: bool,
) -> FileItem {
    let (name, size, date) = if let Some(entry) = entry {
        let size = if entry.is_dir {
            String::new()
        } else {
            format_size(entry.size)
        };
        let date = format_time(&entry.modified);
        (node.name.clone(), size, date)
    } else {
        (node.name.clone(), String::new(), String::new())
    };

    FileItem {
        name: name.into(),
        path: path.into(),
        status_code: status_code(node.status),
        size: size.into(),
        date: date.into(),
        status: status_label(node.status).into(),
        color: status_color(node.status),
        depth,
        is_dir: node.is_dir,
        expanded,
    }
}

fn status_code(status: DiffStatus) -> i32 {
    match status {
        DiffStatus::Same => 0,
        DiffStatus::Different => 1,
        DiffStatus::OrphanLeft => 2,
        DiffStatus::OrphanRight => 3,
        DiffStatus::Unchecked => 4,
    }
}

fn status_label(status: DiffStatus) -> &'static str {
    match status {
        DiffStatus::Same => "Same",
        DiffStatus::Different => "Diff",
        DiffStatus::OrphanLeft => "Left",
        DiffStatus::OrphanRight => "Right",
        DiffStatus::Unchecked => "Unk",
    }
}

fn status_color(status: DiffStatus) -> slint::Color {
    match status {
        DiffStatus::Same => slint::Color::from_rgb_u8(191, 200, 211),
        DiffStatus::Different => slint::Color::from_rgb_u8(224, 90, 90),
        DiffStatus::OrphanLeft => slint::Color::from_rgb_u8(240, 181, 77),
        DiffStatus::OrphanRight => slint::Color::from_rgb_u8(91, 133, 221),
        DiffStatus::Unchecked => slint::Color::from_rgb_u8(152, 163, 175),
    }
}


fn is_probably_text_file(path: &std::path::Path) -> bool {
    let mut file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(_) => return false,
    };

    let mut buffer = [0u8; 8192];
    let read = match file.read(&mut buffer) {
        Ok(read) => read,
        Err(_) => return false,
    };

    let slice = &buffer[..read];
    if slice.contains(&0) {
        return false;
    }

    std::str::from_utf8(slice).is_ok()
}

fn build_raw_text_lines(lines: Vec<DiffLine>) -> Vec<RawTextDiffLine> {
    lines
        .into_iter()
        .map(|line| {
            let change = change_code(line.change_type);
            let left_line = line.line_number_left.map(|n| n.to_string()).unwrap_or_default();
            let right_line = line.line_number_right.map(|n| n.to_string()).unwrap_or_default();
            let segments = build_raw_segments(line.highlighted_segments);

            RawTextDiffLine {
                line_left: left_line,
                line_right: right_line,
                change,
                segments,
            }
        })
        .collect()
}

fn build_raw_segments(segments: Vec<HighlightedSegment>) -> Vec<RawTextSegment> {
    let mut out = Vec::new();

    for segment in segments {
        let cleaned = sanitize_segment_text(&segment.text);
        if cleaned.is_empty() {
            continue;
        }

        out.push(RawTextSegment {
            text: cleaned,
            color: segment.style.foreground,
            bold: segment.style.bold,
            italic: segment.style.italic,
        });
    }

    if out.is_empty() {
        out.push(RawTextSegment {
            text: "".to_string(),
            color: (200, 200, 200),
            bold: false,
            italic: false,
        });
    }

    out
}

fn to_ui_text_lines(lines: Vec<RawTextDiffLine>) -> Vec<TextDiffLine> {
    lines
        .into_iter()
        .map(|line| {
            let segments = line
                .segments
                .into_iter()
                .map(|segment| TextSegment {
                    text: segment.text.into(),
                    color: slint::Color::from_rgb_u8(
                        segment.color.0,
                        segment.color.1,
                        segment.color.2,
                    ),
                    bold: segment.bold,
                    italic: segment.italic,
                })
                .collect::<Vec<_>>();

            TextDiffLine {
                line_left: line.line_left.into(),
                line_right: line.line_right.into(),
                change: line.change,
                segments: slint::ModelRc::new(slint::VecModel::from(segments)),
            }
        })
        .collect()
}

fn sanitize_segment_text(text: &str) -> String {
    text.replace('\n', "").replace('\r', "")
}

fn change_code(change: DiffChangeType) -> i32 {
    match change {
        DiffChangeType::Equal => CHANGE_EQUAL,
        DiffChangeType::Insert => CHANGE_INSERT,
        DiffChangeType::Delete => CHANGE_DELETE,
    }
}

fn execute_sync_operation(
    roots: &CompareRoots,
    tree: &TreeNode,
    sync_mode: i32,
    dry_run: bool,
    use_trash: bool,
) -> Result<String, String> {
    use rcompare_common::DiffStatus;

    let ops = FileOperations::new(dry_run, use_trash);
    let mut copied = 0;
    let mut errors = 0;

    // Collect files to sync based on mode
    fn collect_files(
        node: &TreeNode,
        left_root: &PathBuf,
        right_root: &PathBuf,
        sync_mode: i32,
        ops: &FileOperations,
        copied: &mut usize,
        errors: &mut usize,
    ) {
        if !node.is_dir {
            match (sync_mode, node.status) {
                // Left to Right: copy left orphans and different files (prefer left)
                (0, DiffStatus::OrphanLeft) | (0, DiffStatus::Different) => {
                    if let Some(ref left) = node.left {
                        let src = left_root.join(&left.path);
                        let dest = right_root.join(&left.path);
                        if ops.copy_file(&src, &dest).is_ok() {
                            *copied += 1;
                        } else {
                            *errors += 1;
                        }
                    }
                }
                // Right to Left: copy right orphans and different files (prefer right)
                (1, DiffStatus::OrphanRight) | (1, DiffStatus::Different) => {
                    if let Some(ref right) = node.right {
                        let src = right_root.join(&right.path);
                        let dest = left_root.join(&right.path);
                        if ops.copy_file(&src, &dest).is_ok() {
                            *copied += 1;
                        } else {
                            *errors += 1;
                        }
                    }
                }
                // Bidirectional: newer wins
                (2, DiffStatus::OrphanLeft) => {
                    if let Some(ref left) = node.left {
                        let src = left_root.join(&left.path);
                        let dest = right_root.join(&left.path);
                        if ops.copy_file(&src, &dest).is_ok() {
                            *copied += 1;
                        } else {
                            *errors += 1;
                        }
                    }
                }
                (2, DiffStatus::OrphanRight) => {
                    if let Some(ref right) = node.right {
                        let src = right_root.join(&right.path);
                        let dest = left_root.join(&right.path);
                        if ops.copy_file(&src, &dest).is_ok() {
                            *copied += 1;
                        } else {
                            *errors += 1;
                        }
                    }
                }
                (2, DiffStatus::Different) => {
                    // Compare timestamps and copy newer
                    if let (Some(ref left), Some(ref right)) = (&node.left, &node.right) {
                        if left.modified > right.modified {
                            let src = left_root.join(&left.path);
                            let dest = right_root.join(&left.path);
                            if ops.copy_file(&src, &dest).is_ok() {
                                *copied += 1;
                            } else {
                                *errors += 1;
                            }
                        } else if right.modified > left.modified {
                            let src = right_root.join(&right.path);
                            let dest = left_root.join(&right.path);
                            if ops.copy_file(&src, &dest).is_ok() {
                                *copied += 1;
                            } else {
                                *errors += 1;
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        // Recurse into children
        for child in &node.children {
            collect_files(child, left_root, right_root, sync_mode, ops, copied, errors);
        }
    }

    collect_files(
        tree,
        &roots.left_root,
        &roots.right_root,
        sync_mode,
        &ops,
        &mut copied,
        &mut errors,
    );

    let mode_str = match sync_mode {
        0 => "Left → Right",
        1 => "Right → Left",
        _ => "Bidirectional",
    };

    if dry_run {
        Ok(format!("Sync preview ({}): {} files would be copied, {} errors", mode_str, copied, errors))
    } else {
        Ok(format!("Sync complete ({}): {} files copied, {} errors", mode_str, copied, errors))
    }
}

fn profiles_to_ui_items(profiles: &[SessionProfile]) -> Vec<ProfileItem> {
    profiles.iter().map(|p| {
        let last_used = if p.last_used > 0 {
            let dt = chrono::DateTime::<chrono::Utc>::from_timestamp(p.last_used as i64, 0);
            dt.map(|d| d.format("%Y-%m-%d %H:%M").to_string())
                .unwrap_or_else(|| "Unknown".to_string())
        } else {
            "Never".to_string()
        };

        ProfileItem {
            name: p.name.clone().into(),
            left_path: p.left_path.to_string_lossy().to_string().into(),
            right_path: p.right_path.to_string_lossy().to_string().into(),
            last_used: last_used.into(),
        }
    }).collect()
}

fn format_size(size: u64) -> String {
    const KB: u64 = 1024;
    const MB: u64 = KB * 1024;
    const GB: u64 = MB * 1024;

    if size >= GB {
        format!("{:.2} GB", size as f64 / GB as f64)
    } else if size >= MB {
        format!("{:.2} MB", size as f64 / MB as f64)
    } else if size >= KB {
        format!("{:.2} KB", size as f64 / KB as f64)
    } else {
        format!("{} B", size)
    }
}

fn format_time(time: &std::time::SystemTime) -> String {
    use std::time::UNIX_EPOCH;

    match time.duration_since(UNIX_EPOCH) {
        Ok(duration) => {
            let secs = duration.as_secs();
            let dt = chrono::DateTime::<chrono::Utc>::from_timestamp(secs as i64, 0);
            if let Some(dt) = dt {
                dt.format("%Y-%m-%d %H:%M:%S").to_string()
            } else {
                "Unknown".to_string()
            }
        }
        Err(_) => "Unknown".to_string(),
    }
}

fn select_folder() -> Option<std::path::PathBuf> {
    native_dialog::FileDialog::new()
        .show_open_single_dir()
        .unwrap_or(None)
}

fn select_archive() -> Option<std::path::PathBuf> {
    native_dialog::FileDialog::new()
        .add_filter("Archives", &["zip", "tar", "tar.gz", "tgz", "7z"])
        .show_open_single_file()
        .unwrap_or(None)
}

fn select_text_file() -> Option<std::path::PathBuf> {
    native_dialog::FileDialog::new()
        .show_open_single_file()
        .unwrap_or(None)
}

fn scan_source(
    scanner: &FolderScanner,
    source: &ScanSource,
    cancel: Option<&AtomicBool>,
) -> Result<Vec<rcompare_common::FileEntry>, rcompare_common::RCompareError> {
    match source {
        ScanSource::Local { root } => scanner.scan_with_cancel(root, cancel),
        ScanSource::Vfs { vfs, root } => scanner.scan_vfs_with_cancel(vfs.as_ref(), root, cancel),
    }
}

fn build_scan_source(path: &std::path::Path) -> Result<ScanSource, AnyError> {
    if path.is_dir() {
        return Ok(ScanSource::Local {
            root: path.to_path_buf(),
        });
    }

    if path.is_file() {
        return match detect_archive_kind(path) {
            Some(ArchiveKind::Zip) => Ok(ScanSource::Vfs {
                vfs: Box::new(ZipVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::Tar) => Ok(ScanSource::Vfs {
                vfs: Box::new(TarVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::SevenZ) => Ok(ScanSource::Vfs {
                vfs: Box::new(SevenZVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            None => Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!(
                    "Path is not a directory or supported archive (.zip, .tar, .tar.gz, .tgz, .7z): {}",
                    path.display()
                ),
            ).into()),
        };
    }

    Err(std::io::Error::new(
        std::io::ErrorKind::NotFound,
        format!("Path does not exist: {}", path.display()),
    ).into())
}

fn detect_archive_kind(path: &std::path::Path) -> Option<ArchiveKind> {
    let name = path.file_name()?.to_string_lossy().to_lowercase();
    if name.ends_with(".zip") {
        Some(ArchiveKind::Zip)
    } else if name.ends_with(".tar") || name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        Some(ArchiveKind::Tar)
    } else if name.ends_with(".7z") {
        Some(ArchiveKind::SevenZ)
    } else {
        None
    }
}
