use rcompare_common::error::RCompareError;
use rcompare_common::types::{
    ConflictType, FileEntry, MergeConflict, MergeResolution, MergeResult, MergeSource,
};
use std::collections::HashMap;
use std::path::PathBuf;

/// Engine for three-way merge operations
pub struct MergeEngine {
    /// Whether to automatically resolve trivial conflicts
    auto_resolve: bool,
}

impl MergeEngine {
    /// Create a new merge engine with default settings
    pub fn new() -> Self {
        Self {
            auto_resolve: true,
        }
    }

    /// Create a merge engine with auto-resolution disabled
    pub fn without_auto_resolve() -> Self {
        Self {
            auto_resolve: false,
        }
    }

    /// Perform a three-way merge between base, left, and right file trees
    ///
    /// # Arguments
    /// * `base` - Map of file paths to base entries
    /// * `left` - Map of file paths to left entries
    /// * `right` - Map of file paths to right entries
    ///
    /// # Returns
    /// Vector of merge results for all files
    pub fn merge(
        &self,
        base: &HashMap<PathBuf, FileEntry>,
        left: &HashMap<PathBuf, FileEntry>,
        right: &HashMap<PathBuf, FileEntry>,
    ) -> Result<Vec<MergeResult>, RCompareError> {
        let mut results = Vec::new();

        // Collect all unique paths from all three sides
        let mut all_paths = std::collections::HashSet::new();
        all_paths.extend(base.keys().cloned());
        all_paths.extend(left.keys().cloned());
        all_paths.extend(right.keys().cloned());

        // Process each path
        for path in all_paths {
            let base_entry = base.get(&path).cloned();
            let left_entry = left.get(&path).cloned();
            let right_entry = right.get(&path).cloned();

            let result = self.merge_entry(&path, base_entry, left_entry, right_entry)?;
            results.push(result);
        }

        Ok(results)
    }

    /// Merge a single file entry from the three sides
    fn merge_entry(
        &self,
        path: &PathBuf,
        base: Option<FileEntry>,
        left: Option<FileEntry>,
        right: Option<FileEntry>,
    ) -> Result<MergeResult, RCompareError> {
        match (base.as_ref(), left.as_ref(), right.as_ref()) {
            // All three exist - check for modifications
            (Some(b), Some(l), Some(r)) => self.merge_all_exist(path, b, l, r),

            // Only left and right exist (both added)
            (None, Some(l), Some(r)) => self.merge_both_added(path, l, r),

            // Base and left exist, right deleted
            (Some(b), Some(l), None) => self.merge_modify_delete(path, b, l, true),

            // Base and right exist, left deleted
            (Some(b), None, Some(r)) => self.merge_modify_delete(path, b, r, false),

            // Only base exists (both deleted)
            (Some(_), None, None) => Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::UseBase,
                conflict: None,
                resolved_source: Some(MergeSource::Base),
            }),

            // Only left exists (added on left)
            (None, Some(_), None) => Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::UseLeft,
                conflict: None,
                resolved_source: Some(MergeSource::Left),
            }),

            // Only right exists (added on right)
            (None, None, Some(_)) => Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::UseRight,
                conflict: None,
                resolved_source: Some(MergeSource::Right),
            }),

            // None exist (shouldn't happen)
            (None, None, None) => Err(RCompareError::Path(format!(
                "No entries found for path: {}",
                path.display()
            ))),
        }
    }

    /// Merge when all three versions exist
    fn merge_all_exist(
        &self,
        path: &PathBuf,
        base: &FileEntry,
        left: &FileEntry,
        right: &FileEntry,
    ) -> Result<MergeResult, RCompareError> {
        // Check for type conflicts (directory vs file)
        if base.is_dir != left.is_dir || base.is_dir != right.is_dir {
            return Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::ManualRequired,
                conflict: Some(MergeConflict {
                    path: path.clone(),
                    conflict_type: ConflictType::TypeConflict,
                    base: Some(base.clone()),
                    left: Some(left.clone()),
                    right: Some(right.clone()),
                }),
                resolved_source: None,
            });
        }

        // If it's a directory, no content conflict
        if base.is_dir {
            return Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::AutoMerged,
                conflict: None,
                resolved_source: Some(MergeSource::Merged),
            });
        }

        // Compare modifications
        let left_modified = self.is_modified(base, left);
        let right_modified = self.is_modified(base, right);

        match (left_modified, right_modified) {
            // No changes on either side
            (false, false) => Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::UseBase,
                conflict: None,
                resolved_source: Some(MergeSource::Base),
            }),

            // Only left modified
            (true, false) => Ok(MergeResult {
                path: path.clone(),
                resolution: if self.auto_resolve {
                    MergeResolution::UseLeft
                } else {
                    MergeResolution::AutoMerged
                },
                conflict: None,
                resolved_source: Some(MergeSource::Left),
            }),

            // Only right modified
            (false, true) => Ok(MergeResult {
                path: path.clone(),
                resolution: if self.auto_resolve {
                    MergeResolution::UseRight
                } else {
                    MergeResolution::AutoMerged
                },
                conflict: None,
                resolved_source: Some(MergeSource::Right),
            }),

            // Both modified
            (true, true) => {
                // Check if they're modified to the same content
                if self.is_same_content(left, right) {
                    Ok(MergeResult {
                        path: path.clone(),
                        resolution: MergeResolution::AutoMerged,
                        conflict: None,
                        resolved_source: Some(MergeSource::Left), // Either works
                    })
                } else {
                    // Conflict: both sides modified differently
                    Ok(MergeResult {
                        path: path.clone(),
                        resolution: MergeResolution::ManualRequired,
                        conflict: Some(MergeConflict {
                            path: path.clone(),
                            conflict_type: ConflictType::BothModified,
                            base: Some(base.clone()),
                            left: Some(left.clone()),
                            right: Some(right.clone()),
                        }),
                        resolved_source: None,
                    })
                }
            }
        }
    }

    /// Merge when both sides added the same file
    fn merge_both_added(
        &self,
        path: &PathBuf,
        left: &FileEntry,
        right: &FileEntry,
    ) -> Result<MergeResult, RCompareError> {
        // Check for type conflicts
        if left.is_dir != right.is_dir {
            return Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::ManualRequired,
                conflict: Some(MergeConflict {
                    path: path.clone(),
                    conflict_type: ConflictType::TypeConflict,
                    base: None,
                    left: Some(left.clone()),
                    right: Some(right.clone()),
                }),
                resolved_source: None,
            });
        }

        // If both added the same content, auto-merge
        if self.is_same_content(left, right) {
            Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::AutoMerged,
                conflict: None,
                resolved_source: Some(MergeSource::Left), // Either works
            })
        } else {
            // Conflict: both added with different content
            Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::ManualRequired,
                conflict: Some(MergeConflict {
                    path: path.clone(),
                    conflict_type: ConflictType::BothAdded,
                    base: None,
                    left: Some(left.clone()),
                    right: Some(right.clone()),
                }),
                resolved_source: None,
            })
        }
    }

    /// Merge modify-delete conflicts
    ///
    /// # Arguments
    /// * `is_left_modified` - true if left was modified and right deleted, false for opposite
    fn merge_modify_delete(
        &self,
        path: &PathBuf,
        base: &FileEntry,
        modified: &FileEntry,
        is_left_modified: bool,
    ) -> Result<MergeResult, RCompareError> {
        // Check if the "modified" side actually changed
        let was_modified = self.is_modified(base, modified);

        if !was_modified {
            // File wasn't actually modified, just use the deletion
            Ok(MergeResult {
                path: path.clone(),
                resolution: if self.auto_resolve {
                    if is_left_modified {
                        MergeResolution::UseRight
                    } else {
                        MergeResolution::UseLeft
                    }
                } else {
                    MergeResolution::AutoMerged
                },
                conflict: None,
                resolved_source: Some(MergeSource::Base), // Base (deleted)
            })
        } else {
            // Conflict: modified on one side, deleted on other
            Ok(MergeResult {
                path: path.clone(),
                resolution: MergeResolution::ManualRequired,
                conflict: Some(MergeConflict {
                    path: path.clone(),
                    conflict_type: ConflictType::ModifyDelete,
                    base: Some(base.clone()),
                    left: if is_left_modified {
                        Some(modified.clone())
                    } else {
                        None
                    },
                    right: if is_left_modified {
                        None
                    } else {
                        Some(modified.clone())
                    },
                }),
                resolved_source: None,
            })
        }
    }

    /// Check if an entry was modified compared to base
    fn is_modified(&self, base: &FileEntry, other: &FileEntry) -> bool {
        // Compare size first (quick check)
        if base.size != other.size {
            return true;
        }

        // Compare modification time
        if base.modified != other.modified {
            return true;
        }

        // If same size and mtime, assume not modified
        false
    }

    /// Check if two entries have the same content
    fn is_same_content(&self, left: &FileEntry, right: &FileEntry) -> bool {
        // Size must match
        if left.size != right.size {
            return false;
        }

        // If same size and mtime, assume same content
        left.modified == right.modified
    }
}

impl Default for MergeEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, SystemTime};

    fn create_file_entry(size: u64, modified: SystemTime) -> FileEntry {
        FileEntry {
            path: PathBuf::new(),
            size,
            modified,
            is_dir: false,
        }
    }

    fn create_dir_entry() -> FileEntry {
        FileEntry {
            path: PathBuf::new(),
            size: 0,
            modified: SystemTime::now(),
            is_dir: true,
        }
    }

    #[test]
    fn test_no_changes() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let entry = create_file_entry(100, SystemTime::now());

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), entry.clone());
        left.insert(path.clone(), entry.clone());
        right.insert(path.clone(), entry.clone());

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseBase);
        assert!(results[0].conflict.is_none());
    }

    #[test]
    fn test_left_only_modified() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later = now + Duration::from_secs(60);

        let base_entry = create_file_entry(100, now);
        let left_entry = create_file_entry(200, later); // Different size
        let right_entry = base_entry.clone();

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), left_entry);
        right.insert(path.clone(), right_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseLeft);
        assert!(results[0].conflict.is_none());
        assert_eq!(results[0].resolved_source, Some(MergeSource::Left));
    }

    #[test]
    fn test_right_only_modified() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later = now + Duration::from_secs(60);

        let base_entry = create_file_entry(100, now);
        let left_entry = base_entry.clone();
        let right_entry = create_file_entry(200, later); // Different size

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), left_entry);
        right.insert(path.clone(), right_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseRight);
        assert!(results[0].conflict.is_none());
        assert_eq!(results[0].resolved_source, Some(MergeSource::Right));
    }

    #[test]
    fn test_both_modified_same_content() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later = now + Duration::from_secs(60);

        let base_entry = create_file_entry(100, now);
        let modified_entry = create_file_entry(200, later); // Same modifications

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), modified_entry.clone());
        right.insert(path.clone(), modified_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::AutoMerged);
        assert!(results[0].conflict.is_none());
    }

    #[test]
    fn test_both_modified_different_content() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later1 = now + Duration::from_secs(60);
        let later2 = now + Duration::from_secs(120);

        let base_entry = create_file_entry(100, now);
        let left_entry = create_file_entry(200, later1); // Different modifications
        let right_entry = create_file_entry(300, later2); // Different modifications

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), left_entry);
        right.insert(path.clone(), right_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::ManualRequired);
        assert!(results[0].conflict.is_some());
        assert_eq!(
            results[0].conflict.as_ref().unwrap().conflict_type,
            ConflictType::BothModified
        );
    }

    #[test]
    fn test_both_added_same_content() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let entry = create_file_entry(100, SystemTime::now());

        let base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        left.insert(path.clone(), entry.clone());
        right.insert(path.clone(), entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::AutoMerged);
        assert!(results[0].conflict.is_none());
    }

    #[test]
    fn test_both_added_different_content() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later = now + Duration::from_secs(60);

        let left_entry = create_file_entry(100, now);
        let right_entry = create_file_entry(200, later); // Different content

        let base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        left.insert(path.clone(), left_entry);
        right.insert(path.clone(), right_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::ManualRequired);
        assert!(results[0].conflict.is_some());
        assert_eq!(
            results[0].conflict.as_ref().unwrap().conflict_type,
            ConflictType::BothAdded
        );
    }

    #[test]
    fn test_modify_delete_conflict() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let now = SystemTime::now();
        let later = now + Duration::from_secs(60);

        let base_entry = create_file_entry(100, now);
        let left_entry = create_file_entry(200, later); // Modified

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), left_entry);
        // right doesn't have the file (deleted)

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::ManualRequired);
        assert!(results[0].conflict.is_some());
        assert_eq!(
            results[0].conflict.as_ref().unwrap().conflict_type,
            ConflictType::ModifyDelete
        );
    }

    #[test]
    fn test_type_conflict() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let base_entry = create_file_entry(100, SystemTime::now());
        let left_entry = create_dir_entry(); // Changed to directory
        let right_entry = base_entry.clone();

        let mut base = HashMap::new();
        let mut left = HashMap::new();
        let mut right = HashMap::new();

        base.insert(path.clone(), base_entry);
        left.insert(path.clone(), left_entry);
        right.insert(path.clone(), right_entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::ManualRequired);
        assert!(results[0].conflict.is_some());
        assert_eq!(
            results[0].conflict.as_ref().unwrap().conflict_type,
            ConflictType::TypeConflict
        );
    }

    #[test]
    fn test_added_on_left_only() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let entry = create_file_entry(100, SystemTime::now());

        let base = HashMap::new();
        let mut left = HashMap::new();
        let right = HashMap::new();

        left.insert(path.clone(), entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseLeft);
        assert!(results[0].conflict.is_none());
        assert_eq!(results[0].resolved_source, Some(MergeSource::Left));
    }

    #[test]
    fn test_added_on_right_only() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let entry = create_file_entry(100, SystemTime::now());

        let base = HashMap::new();
        let left = HashMap::new();
        let mut right = HashMap::new();

        right.insert(path.clone(), entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseRight);
        assert!(results[0].conflict.is_none());
        assert_eq!(results[0].resolved_source, Some(MergeSource::Right));
    }

    #[test]
    fn test_both_deleted() {
        let engine = MergeEngine::new();
        let path = PathBuf::from("file.txt");

        let entry = create_file_entry(100, SystemTime::now());

        let mut base = HashMap::new();
        let left = HashMap::new();
        let right = HashMap::new();

        base.insert(path.clone(), entry);

        let results = engine.merge(&base, &left, &right).unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].resolution, MergeResolution::UseBase);
        assert!(results[0].conflict.is_none());
    }
}
