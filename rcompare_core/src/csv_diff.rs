use csv::{Reader, StringRecord};
use rcompare_common::RCompareError;
use serde::Serialize;
use std::collections::HashMap;
use std::path::Path;

/// Result of a CSV comparison
#[derive(Debug, Clone, Serialize)]
pub struct CsvDiffResult {
    /// Total number of rows (excluding header)
    pub total_rows: usize,
    /// Number of rows that differ
    pub different_rows: usize,
    /// Number of rows only in left
    pub left_only_rows: usize,
    /// Number of rows only in right
    pub right_only_rows: usize,
    /// Number of identical rows
    pub identical_rows: usize,
    /// Headers match
    pub headers_match: bool,
    /// Left headers
    pub left_headers: Vec<String>,
    /// Right headers
    pub right_headers: Vec<String>,
    /// Detailed row differences (limited to first 100)
    pub row_diffs: Vec<RowDiff>,
}

/// Represents a difference in a specific row
#[derive(Debug, Clone, Serialize)]
pub struct RowDiff {
    /// Row number (1-indexed, excluding header)
    pub row_num: usize,
    /// Type of difference
    pub diff_type: RowDiffType,
    /// Column differences (only for Modified rows)
    pub column_diffs: Vec<ColumnDiff>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum RowDiffType {
    /// Row exists in both but values differ
    Modified,
    /// Row only exists in left
    LeftOnly,
    /// Row only exists in right
    RightOnly,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnDiff {
    /// Column name
    pub column: String,
    /// Column index
    pub index: usize,
    /// Left value
    pub left_value: String,
    /// Right value
    pub right_value: String,
}

/// Comparison mode for CSV files
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize)]
pub enum CsvCompareMode {
    /// Compare row by row in order
    #[default]
    RowByRow,
    /// Compare by key column(s) - rows can be in different order
    ByKey,
}

/// Engine for comparing CSV files
pub struct CsvDiffEngine {
    mode: CsvCompareMode,
    key_columns: Vec<String>,
    max_row_diffs: usize,
}

impl CsvDiffEngine {
    pub fn new() -> Self {
        Self {
            mode: CsvCompareMode::default(),
            key_columns: vec![],
            max_row_diffs: 100,
        }
    }

    pub fn with_mode(mut self, mode: CsvCompareMode) -> Self {
        self.mode = mode;
        self
    }

    pub fn with_key_columns(mut self, columns: Vec<String>) -> Self {
        self.key_columns = columns;
        if !self.key_columns.is_empty() {
            self.mode = CsvCompareMode::ByKey;
        }
        self
    }

    pub fn with_max_row_diffs(mut self, max: usize) -> Self {
        self.max_row_diffs = max;
        self
    }

    /// Compare two CSV files
    pub fn compare_files(&self, left: &Path, right: &Path) -> Result<CsvDiffResult, RCompareError> {
        let mut left_reader = Reader::from_path(left).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open left CSV file: {}", e),
            ))
        })?;

        let mut right_reader = Reader::from_path(right).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open right CSV file: {}", e),
            ))
        })?;

        let left_headers = left_reader
            .headers()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read left CSV headers: {}", e),
                ))
            })?
            .iter()
            .map(|s| s.to_string())
            .collect::<Vec<_>>();

        let right_headers = right_reader
            .headers()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read right CSV headers: {}", e),
                ))
            })?
            .iter()
            .map(|s| s.to_string())
            .collect::<Vec<_>>();

        let headers_match = left_headers == right_headers;

        match self.mode {
            CsvCompareMode::RowByRow => self.compare_row_by_row(
                &left_headers,
                &right_headers,
                left_reader,
                right_reader,
                headers_match,
            ),
            CsvCompareMode::ByKey => self.compare_by_key(
                &left_headers,
                &right_headers,
                left_reader,
                right_reader,
                headers_match,
            ),
        }
    }

    fn compare_row_by_row(
        &self,
        left_headers: &[String],
        right_headers: &[String],
        mut left_reader: Reader<std::fs::File>,
        mut right_reader: Reader<std::fs::File>,
        headers_match: bool,
    ) -> Result<CsvDiffResult, RCompareError> {
        let mut different_rows = 0;
        let mut left_only_rows = 0;
        let mut right_only_rows = 0;
        let mut identical_rows = 0;
        let mut row_diffs = Vec::new();

        let left_records: Vec<StringRecord> = left_reader
            .records()
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read left CSV records: {}", e),
                ))
            })?;

        let right_records: Vec<StringRecord> = right_reader
            .records()
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read right CSV records: {}", e),
                ))
            })?;

        let max_rows = left_records.len().max(right_records.len());
        let total_rows = max_rows;

        for i in 0..max_rows {
            let row_num = i + 1;
            let left_row = left_records.get(i);
            let right_row = right_records.get(i);

            match (left_row, right_row) {
                (Some(left), Some(right)) => {
                    if left == right {
                        identical_rows += 1;
                    } else {
                        different_rows += 1;
                        if row_diffs.len() < self.max_row_diffs {
                            let column_diffs = self.find_column_diffs(left_headers, left, right);
                            row_diffs.push(RowDiff {
                                row_num,
                                diff_type: RowDiffType::Modified,
                                column_diffs,
                            });
                        }
                    }
                }
                (Some(_), None) => {
                    left_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            row_num,
                            diff_type: RowDiffType::LeftOnly,
                            column_diffs: vec![],
                        });
                    }
                }
                (None, Some(_)) => {
                    right_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            row_num,
                            diff_type: RowDiffType::RightOnly,
                            column_diffs: vec![],
                        });
                    }
                }
                (None, None) => unreachable!(),
            }
        }

        Ok(CsvDiffResult {
            total_rows,
            different_rows,
            left_only_rows,
            right_only_rows,
            identical_rows,
            headers_match,
            left_headers: left_headers.to_vec(),
            right_headers: right_headers.to_vec(),
            row_diffs,
        })
    }

    fn compare_by_key(
        &self,
        left_headers: &[String],
        right_headers: &[String],
        mut left_reader: Reader<std::fs::File>,
        mut right_reader: Reader<std::fs::File>,
        headers_match: bool,
    ) -> Result<CsvDiffResult, RCompareError> {
        // Get key column indices
        let key_indices: Vec<usize> = self
            .key_columns
            .iter()
            .filter_map(|col| left_headers.iter().position(|h| h == col))
            .collect();

        if key_indices.is_empty() {
            return Err(RCompareError::Comparison(
                "No valid key columns found in CSV headers".to_string(),
            ));
        }

        // Build hash maps keyed by the key column(s)
        let mut left_map: HashMap<String, StringRecord> = HashMap::new();
        for result in left_reader.records() {
            let record = result.map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read left CSV record: {}", e),
                ))
            })?;
            let key = self.build_key(&record, &key_indices);
            left_map.insert(key, record);
        }

        let mut right_map: HashMap<String, StringRecord> = HashMap::new();
        for result in right_reader.records() {
            let record = result.map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read right CSV record: {}", e),
                ))
            })?;
            let key = self.build_key(&record, &key_indices);
            right_map.insert(key, record);
        }

        let total_rows = left_map.len().max(right_map.len());
        let mut different_rows = 0;
        let mut left_only_rows = 0;
        let mut right_only_rows = 0;
        let mut identical_rows = 0;
        let mut row_diffs = Vec::new();

        // Collect all unique keys
        let mut all_keys: Vec<String> = left_map.keys().chain(right_map.keys()).cloned().collect();
        all_keys.sort();
        all_keys.dedup();

        for (idx, key) in all_keys.iter().enumerate() {
            let row_num = idx + 1;
            let left_row = left_map.get(key);
            let right_row = right_map.get(key);

            match (left_row, right_row) {
                (Some(left), Some(right)) => {
                    if left == right {
                        identical_rows += 1;
                    } else {
                        different_rows += 1;
                        if row_diffs.len() < self.max_row_diffs {
                            let column_diffs = self.find_column_diffs(left_headers, left, right);
                            row_diffs.push(RowDiff {
                                row_num,
                                diff_type: RowDiffType::Modified,
                                column_diffs,
                            });
                        }
                    }
                }
                (Some(_), None) => {
                    left_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            row_num,
                            diff_type: RowDiffType::LeftOnly,
                            column_diffs: vec![],
                        });
                    }
                }
                (None, Some(_)) => {
                    right_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            row_num,
                            diff_type: RowDiffType::RightOnly,
                            column_diffs: vec![],
                        });
                    }
                }
                (None, None) => unreachable!(),
            }
        }

        Ok(CsvDiffResult {
            total_rows,
            different_rows,
            left_only_rows,
            right_only_rows,
            identical_rows,
            headers_match,
            left_headers: left_headers.to_vec(),
            right_headers: right_headers.to_vec(),
            row_diffs,
        })
    }

    fn build_key(&self, record: &StringRecord, key_indices: &[usize]) -> String {
        key_indices
            .iter()
            .filter_map(|&idx| record.get(idx))
            .collect::<Vec<_>>()
            .join("|")
    }

    fn find_column_diffs(
        &self,
        headers: &[String],
        left: &StringRecord,
        right: &StringRecord,
    ) -> Vec<ColumnDiff> {
        let mut diffs = Vec::new();

        for (idx, header) in headers.iter().enumerate() {
            let left_val = left.get(idx).unwrap_or("");
            let right_val = right.get(idx).unwrap_or("");

            if left_val != right_val {
                diffs.push(ColumnDiff {
                    column: header.clone(),
                    index: idx,
                    left_value: left_val.to_string(),
                    right_value: right_val.to_string(),
                });
            }
        }

        diffs
    }
}

impl Default for CsvDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a file path appears to be a CSV based on extension
pub fn is_csv_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(ext.as_str(), "csv" | "tsv")
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn create_temp_csv(content: &str) -> NamedTempFile {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all(content.as_bytes()).unwrap();
        file.flush().unwrap();
        file
    }

    #[test]
    fn test_identical_csvs() {
        let content = "name,age,city\nAlice,30,NYC\nBob,25,LA\n";
        let left = create_temp_csv(content);
        let right = create_temp_csv(content);

        let engine = CsvDiffEngine::new();
        let result = engine.compare_files(left.path(), right.path()).unwrap();

        assert_eq!(result.total_rows, 2);
        assert_eq!(result.identical_rows, 2);
        assert_eq!(result.different_rows, 0);
        assert!(result.headers_match);
    }

    #[test]
    fn test_different_values() {
        let left = create_temp_csv("name,age,city\nAlice,30,NYC\nBob,25,LA\n");
        let right = create_temp_csv("name,age,city\nAlice,31,NYC\nBob,25,SF\n");

        let engine = CsvDiffEngine::new();
        let result = engine.compare_files(left.path(), right.path()).unwrap();

        assert_eq!(result.total_rows, 2);
        assert_eq!(result.identical_rows, 0);
        assert_eq!(result.different_rows, 2);
        assert_eq!(result.row_diffs.len(), 2);
    }

    #[test]
    fn test_different_row_counts() {
        let left = create_temp_csv("name,age\nAlice,30\nBob,25\nCharlie,35\n");
        let right = create_temp_csv("name,age\nAlice,30\n");

        let engine = CsvDiffEngine::new();
        let result = engine.compare_files(left.path(), right.path()).unwrap();

        assert_eq!(result.total_rows, 3);
        assert_eq!(result.identical_rows, 1);
        assert_eq!(result.left_only_rows, 2);
        assert_eq!(result.right_only_rows, 0);
    }

    #[test]
    fn test_is_csv_file() {
        assert!(is_csv_file(Path::new("data.csv")));
        assert!(is_csv_file(Path::new("data.CSV")));
        assert!(is_csv_file(Path::new("data.tsv")));
        assert!(!is_csv_file(Path::new("data.txt")));
        assert!(!is_csv_file(Path::new("data.xlsx")));
    }
}
