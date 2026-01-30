use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use rcompare_core::{ComparisonEngine, FolderScanner, HashCache};
use rcompare_common::{AppConfig, FileEntry};
use std::fs;
use std::io::Write as IoWrite;
use std::path::{Path, PathBuf};
use std::time::SystemTime;
use tempfile::TempDir;

// Helper to create test directory structure
fn create_test_tree(root: &Path, depth: usize, files_per_dir: usize, file_size: usize) {
    if depth == 0 {
        return;
    }

    for i in 0..files_per_dir {
        let file_path = root.join(format!("file_{}.txt", i));
        let mut file = fs::File::create(&file_path).unwrap();
        let content = vec![b'x'; file_size];
        file.write_all(&content).unwrap();
    }

    if depth > 1 {
        for i in 0..3 {
            let dir_path = root.join(format!("subdir_{}", i));
            fs::create_dir(&dir_path).unwrap();
            create_test_tree(&dir_path, depth - 1, files_per_dir, file_size);
        }
    }
}

// Helper to create file entries for comparison
fn create_file_entries(count: usize) -> Vec<FileEntry> {
    (0..count)
        .map(|i| FileEntry {
            path: PathBuf::from(format!("file_{}.txt", i)),
            size: 1024,
            modified: SystemTime::now(),
            is_dir: false,
        })
        .collect()
}

fn bench_scanner_small(c: &mut Criterion) {
    c.bench_function("scanner_small_tree_10_files", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 1, 10, 1024);
        let scanner = FolderScanner::new(AppConfig::default());

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

fn bench_scanner_medium(c: &mut Criterion) {
    c.bench_function("scanner_medium_tree_100_files", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 2, 10, 1024);
        let scanner = FolderScanner::new(AppConfig::default());

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

fn bench_scanner_with_gitignore(c: &mut Criterion) {
    c.bench_function("scanner_with_gitignore_patterns", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 2, 10, 1024);

        // Add .gitignore
        let gitignore_content = "*.tmp\n*.log\ntarget/\n";
        fs::write(temp.path().join(".gitignore"), gitignore_content).unwrap();

        let mut scanner = FolderScanner::new(AppConfig::default());
        scanner.load_gitignore(temp.path()).unwrap();

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

fn bench_scanner_with_custom_ignore(c: &mut Criterion) {
    c.bench_function("scanner_with_custom_patterns", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 2, 10, 1024);

        let config = AppConfig {
            ignore_patterns: vec!["*.o".to_string(), "*.tmp".to_string(), "build/".to_string()],
            ..Default::default()
        };
        let scanner = FolderScanner::new(config);

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

fn bench_hash_cache_operations(c: &mut Criterion) {
    let temp = TempDir::new().unwrap();
    let cache = HashCache::new(temp.path().to_path_buf()).unwrap();

    let mut group = c.benchmark_group("hash_cache");

    for size in [10, 100, 1000].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let entries = create_file_entries(size);

            b.iter(|| {
                for entry in &entries {
                    let key = rcompare_common::CacheKey {
                        path: entry.path.clone(),
                        size: entry.size,
                        modified: entry.modified,
                    };
                    let _ = cache.get(black_box(&key));
                }
            });
        });
    }

    group.finish();
}

fn bench_comparison_identical_files(c: &mut Criterion) {
    let temp = TempDir::new().unwrap();
    let cache = HashCache::new(temp.path().join("cache")).unwrap();
    let engine = ComparisonEngine::new(cache);

    let mut group = c.benchmark_group("comparison_identical");

    for size in [10, 50, 100].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let entries = create_file_entries(size);

            b.iter(|| {
                let result = engine
                    .compare(
                        black_box(Path::new("/left")),
                        black_box(Path::new("/right")),
                        black_box(entries.clone()),
                        black_box(entries.clone()),
                    )
                    .unwrap();
                black_box(result);
            });
        });
    }

    group.finish();
}

fn bench_comparison_all_different(c: &mut Criterion) {
    let temp = TempDir::new().unwrap();
    let cache = HashCache::new(temp.path().join("cache")).unwrap();
    let engine = ComparisonEngine::new(cache);

    let mut group = c.benchmark_group("comparison_all_different");

    for size in [10, 50, 100].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let left_entries = create_file_entries(size);
            let right_entries: Vec<FileEntry> = (0..size)
                .map(|i| FileEntry {
                    path: PathBuf::from(format!("different_{}.txt", i)),
                    size: 2048,
                    modified: SystemTime::now(),
                    is_dir: false,
                })
                .collect();

            b.iter(|| {
                let result = engine
                    .compare(
                        black_box(Path::new("/left")),
                        black_box(Path::new("/right")),
                        black_box(left_entries.clone()),
                        black_box(right_entries.clone()),
                    )
                    .unwrap();
                black_box(result);
            });
        });
    }

    group.finish();
}

fn bench_full_scan_and_compare(c: &mut Criterion) {
    c.bench_function("full_workflow_scan_and_compare", |b| {
        let temp_root = TempDir::new().unwrap();
        let left = temp_root.path().join("left");
        let right = temp_root.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();

        create_test_tree(&left, 2, 5, 1024);
        create_test_tree(&right, 2, 5, 1024);

        b.iter(|| {
            let scanner = FolderScanner::new(AppConfig::default());
            let cache = HashCache::new(temp_root.path().join("cache")).unwrap();
            let engine = ComparisonEngine::new(cache);

            let left_entries = scanner.scan(black_box(&left)).unwrap();
            let right_entries = scanner.scan(black_box(&right)).unwrap();

            let result = engine
                .compare(
                    black_box(&left),
                    black_box(&right),
                    black_box(left_entries),
                    black_box(right_entries),
                )
                .unwrap();

            black_box(result);
        });
    });
}

criterion_group!(
    scanner_benches,
    bench_scanner_small,
    bench_scanner_medium,
    bench_scanner_with_gitignore,
    bench_scanner_with_custom_ignore
);

criterion_group!(
    cache_benches,
    bench_hash_cache_operations
);

criterion_group!(
    comparison_benches,
    bench_comparison_identical_files,
    bench_comparison_all_different
);

criterion_group!(
    workflow_benches,
    bench_full_scan_and_compare
);

criterion_main!(
    scanner_benches,
    cache_benches,
    comparison_benches,
    workflow_benches
);
