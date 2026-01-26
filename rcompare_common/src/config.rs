use crate::{AppConfig, RCompareError};
use directories::ProjectDirs;
use std::fs;
use std::path::{Path, PathBuf};

const CONFIG_FILE_NAME: &str = "rcompare.toml";

#[derive(Debug, Clone)]
pub struct LoadedConfig {
    pub config: AppConfig,
    pub path: PathBuf,
    pub exists: bool,
    pub portable: bool,
}

pub fn load_config(prefer_portable: bool) -> Result<LoadedConfig, RCompareError> {
    let (path, portable) = resolve_config_path(prefer_portable)?;
    let exists = path.exists();

    let mut config = if exists {
        let data = fs::read_to_string(&path)?;
        toml::from_str(&data).map_err(|e| RCompareError::Serialization(e.to_string()))?
    } else {
        AppConfig::default()
    };

    config.portable_mode = portable;

    Ok(LoadedConfig {
        config,
        path,
        exists,
        portable,
    })
}

pub fn ensure_config(prefer_portable: bool) -> Result<LoadedConfig, RCompareError> {
    let loaded = load_config(prefer_portable)?;
    if !loaded.exists {
        save_config(&loaded.path, &loaded.config)?;
    }
    Ok(loaded)
}

pub fn save_config(path: &Path, config: &AppConfig) -> Result<(), RCompareError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let data = toml::to_string_pretty(config)
        .map_err(|e| RCompareError::Serialization(e.to_string()))?;
    fs::write(path, data)?;
    Ok(())
}

pub fn default_cache_dir(portable: bool, config_path: &Path) -> Result<PathBuf, RCompareError> {
    if portable {
        let base = config_path
            .parent()
            .map(|path| path.to_path_buf())
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
        return Ok(base.join("rcompare_cache"));
    }

    let dirs = ProjectDirs::from("", "aecs4u", "rcompare")
        .ok_or_else(|| RCompareError::Config("Unable to determine config directory".to_string()))?;
    Ok(dirs.cache_dir().to_path_buf())
}

fn resolve_config_path(prefer_portable: bool) -> Result<(PathBuf, bool), RCompareError> {
    if let Some(portable_path) = portable_config_path() {
        if prefer_portable || portable_path.exists() {
            return Ok((portable_path, true));
        }
    }

    let dirs = ProjectDirs::from("", "aecs4u", "rcompare")
        .ok_or_else(|| RCompareError::Config("Unable to determine config directory".to_string()))?;
    Ok((dirs.config_dir().join(CONFIG_FILE_NAME), false))
}

fn portable_config_path() -> Option<PathBuf> {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|dir| dir.join(CONFIG_FILE_NAME)))
}
