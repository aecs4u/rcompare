#![allow(
    clippy::explicit_iter_loop,
    clippy::uninlined_format_args,
    clippy::unwrap_used
)]
// Benchmark setup should fail fast; formatting style does not affect measurements.

use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use rcompare_common::{AppConfig, FileEntry};
use rcompare_core::{ComparisonEngine, FolderScanner, HashCache};
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

        // Add .gitignore -- discovered incrementally during scan() itself,
        // no separate load_gitignore() pass needed.
        let gitignore_content = "*.tmp\n*.log\ntarget/\n";
        fs::write(temp.path().join(".gitignore"), gitignore_content).unwrap();

        let scanner = FolderScanner::new(AppConfig::default());

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

/// Demonstrates the traversal-pruning win: a large ignored subtree should
/// cost roughly the same as an empty directory, since `process_read_dir`
/// drops matched directories before jwalk ever descends into them, rather
/// than reading every file underneath and filtering afterward.
fn bench_scanner_ignored_subtree_pruning(c: &mut Criterion) {
    let mut group = c.benchmark_group("scanner_ignored_subtree_pruning");

    group.bench_function("large_ignored_subtree", |b| {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("keep.txt"), b"x").unwrap();
        let ignored_dir = temp.path().join("node_modules");
        fs::create_dir(&ignored_dir).unwrap();
        create_test_tree(&ignored_dir, 3, 20, 512); // a sizable ignored subtree

        let config = AppConfig {
            ignore_patterns: vec!["node_modules/".to_string()],
            ..Default::default()
        };
        let scanner = FolderScanner::new(config);

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });

    group.bench_function("equivalent_tree_not_ignored", |b| {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("keep.txt"), b"x").unwrap();
        let dir = temp.path().join("node_modules");
        fs::create_dir(&dir).unwrap();
        create_test_tree(&dir, 3, 20, 512);

        let scanner = FolderScanner::new(AppConfig::default());

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });

    group.finish();
}

fn bench_scanner_large_flat_directory(c: &mut Criterion) {
    c.bench_function("scanner_large_flat_directory_2000_files", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 1, 2000, 256);
        let scanner = FolderScanner::new(AppConfig::default());

        b.iter(|| {
            let entries = scanner.scan(black_box(temp.path())).unwrap();
            black_box(entries);
        });
    });
}

fn bench_scanner_deep_directory_tree(c: &mut Criterion) {
    c.bench_function("scanner_deep_directory_tree_depth_8", |b| {
        let temp = TempDir::new().unwrap();
        create_test_tree(temp.path(), 8, 3, 256); // 3^8 ~ 6.5k dirs, few files each
        let scanner = FolderScanner::new(AppConfig::default());

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

/// Writes `count` same-size file pairs (some identical, some differing only
/// in their last byte) so comparison must fall through to hashing rather
/// than short-circuiting on size.
fn write_verify_candidates(left_dir: &Path, right_dir: &Path, count: usize, file_size: usize) {
    fs::create_dir_all(left_dir).unwrap();
    fs::create_dir_all(right_dir).unwrap();
    for i in 0..count {
        let name = format!("file_{i:05}.bin");
        let left_content = vec![(i % 256) as u8; file_size];
        let mut right_content = left_content.clone();
        if i % 5 == 0 {
            right_content[file_size - 1] ^= 0xFF; // ~20% differ
        }
        fs::write(left_dir.join(&name), &left_content).unwrap();
        fs::write(right_dir.join(&name), &right_content).unwrap();
    }
}

fn make_verify_entries(dir: &Path, count: usize, file_size: usize) -> Vec<FileEntry> {
    (0..count)
        .map(|i| {
            let name = format!("file_{i:05}.bin");
            FileEntry {
                path: PathBuf::from(&name),
                size: file_size as u64,
                modified: fs::metadata(dir.join(&name)).unwrap().modified().unwrap(),
                is_dir: false,
            }
        })
        .collect()
}

/// Compares single-threaded (`with_hash_concurrency(Some(1))`) vs the
/// default rayon pool for a batch of same-size file pairs that all need hash
/// verification -- this is the parallel-verification path added to
/// `compare_with_vfs_and_progress`.
fn bench_parallel_hash_verification(c: &mut Criterion) {
    let mut group = c.benchmark_group("parallel_hash_verification");
    const COUNT: usize = 200;
    const FILE_SIZE: usize = 64 * 1024; // 64KB: big enough that hashing dominates

    let temp = TempDir::new().unwrap();
    let left_dir = temp.path().join("left");
    let right_dir = temp.path().join("right");
    write_verify_candidates(&left_dir, &right_dir, COUNT, FILE_SIZE);
    let left_entries = make_verify_entries(&left_dir, COUNT, FILE_SIZE);
    let right_entries = make_verify_entries(&right_dir, COUNT, FILE_SIZE);

    group.bench_function("single_threaded", |b| {
        let cache = HashCache::disabled(); // force rehashing every iteration
        let engine = ComparisonEngine::new(cache)
            .with_hash_verification(true)
            .with_hash_concurrency(Some(1));

        b.iter(|| {
            let result = engine
                .compare(
                    black_box(&left_dir),
                    black_box(&right_dir),
                    black_box(left_entries.clone()),
                    black_box(right_entries.clone()),
                )
                .unwrap();
            black_box(result);
        });
    });

    group.bench_function("default_thread_pool", |b| {
        let cache = HashCache::disabled();
        let engine = ComparisonEngine::new(cache).with_hash_verification(true);

        b.iter(|| {
            let result = engine
                .compare(
                    black_box(&left_dir),
                    black_box(&right_dir),
                    black_box(left_entries.clone()),
                    black_box(right_entries.clone()),
                )
                .unwrap();
            black_box(result);
        });
    });

    group.finish();
}

/// Cold cache (every file rehashed) vs warm cache (all hashes already
/// recorded from a prior run) for the same verify-hashes workload.
fn bench_cold_vs_warm_hash_cache(c: &mut Criterion) {
    let mut group = c.benchmark_group("cold_vs_warm_hash_cache");
    const COUNT: usize = 100;
    const FILE_SIZE: usize = 32 * 1024;

    let temp = TempDir::new().unwrap();
    let left_dir = temp.path().join("left");
    let right_dir = temp.path().join("right");
    write_verify_candidates(&left_dir, &right_dir, COUNT, FILE_SIZE);
    let left_entries = make_verify_entries(&left_dir, COUNT, FILE_SIZE);
    let right_entries = make_verify_entries(&right_dir, COUNT, FILE_SIZE);

    group.bench_function("cold_cache", |b| {
        b.iter(|| {
            // Fresh disabled cache each iteration: nothing to hit, every
            // file gets hashed from scratch.
            let cache = HashCache::disabled();
            let engine = ComparisonEngine::new(cache).with_hash_verification(true);
            let result = engine
                .compare(
                    black_box(&left_dir),
                    black_box(&right_dir),
                    black_box(left_entries.clone()),
                    black_box(right_entries.clone()),
                )
                .unwrap();
            black_box(result);
        });
    });

    group.bench_function("warm_cache", |b| {
        let cache_dir = temp.path().join("warm_cache");
        // Prime the cache once, outside the timed loop.
        {
            let cache = HashCache::new(cache_dir.clone()).unwrap();
            let engine = ComparisonEngine::new(cache).with_hash_verification(true);
            engine
                .compare(
                    &left_dir,
                    &right_dir,
                    left_entries.clone(),
                    right_entries.clone(),
                )
                .unwrap();
            engine.persist_cache().unwrap();
        }

        b.iter(|| {
            let cache = HashCache::new(cache_dir.clone()).unwrap();
            let engine = ComparisonEngine::new(cache).with_hash_verification(true);
            let result = engine
                .compare(
                    black_box(&left_dir),
                    black_box(&right_dir),
                    black_box(left_entries.clone()),
                    black_box(right_entries.clone()),
                )
                .unwrap();
            black_box(result);
        });
    });

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
    bench_scanner_with_custom_ignore,
    bench_scanner_ignored_subtree_pruning,
    bench_scanner_large_flat_directory,
    bench_scanner_deep_directory_tree
);

criterion_group!(
    cache_benches,
    bench_hash_cache_operations,
    bench_cold_vs_warm_hash_cache
);

criterion_group!(
    comparison_benches,
    bench_comparison_identical_files,
    bench_comparison_all_different,
    bench_parallel_hash_verification
);

criterion_group!(workflow_benches, bench_full_scan_and_compare);

criterion_main!(
    scanner_benches,
    cache_benches,
    comparison_benches,
    workflow_benches
);
