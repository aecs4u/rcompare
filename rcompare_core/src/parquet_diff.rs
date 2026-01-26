use polars::prelude::*;
use rcompare_common::RCompareError;
use std::collections::HashMap;
use std::path::Path;

/// Result of a Parquet/DataFrame comparison
#[derive(Debug, Clone)]
pub struct ParquetDiffResult {
    /// Total number of rows compared
    pub total_rows: usize,
    /// Number of rows that differ
    pub different_rows: usize,
    /// Number of rows only in left
    pub left_only_rows: usize,
    /// Number of rows only in right
    pub right_only_rows: usize,
    /// Number of identical rows
    pub identical_rows: usize,
    /// Column names
    pub columns: Vec<String>,
    /// Detailed row differences (limited to first N)
    pub row_diffs: Vec<RowDiff>,
    /// Schema differences
    pub schema_diffs: Vec<SchemaDiff>,
}

/// Represents a difference in a specific row
#[derive(Debug, Clone)]
pub struct RowDiff {
    /// Row number in left (if exists)
    pub left_row: Option<usize>,
    /// Row number in right (if exists)
    pub right_row: Option<usize>,
    /// Type of difference
    pub diff_type: RowDiffType,
    /// Column differences
    pub column_diffs: Vec<ColumnDiff>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RowDiffType {
    /// Row exists in both but differs
    ValueDifferent,
    /// Row only exists in left
    LeftOnly,
    /// Row only exists in right
    RightOnly,
}

/// Represents a difference in a specific column value
#[derive(Debug, Clone)]
pub struct ColumnDiff {
    /// Column name
    pub column: String,
    /// Left value (as string)
    pub left_value: String,
    /// Right value (as string)
    pub right_value: String,
}

/// Represents a schema difference
#[derive(Debug, Clone)]
pub struct SchemaDiff {
    /// Type of schema difference
    pub diff_type: SchemaDiffType,
    /// Column name
    pub column: String,
    /// Left data type (if exists)
    pub left_type: Option<String>,
    /// Right data type (if exists)
    pub right_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SchemaDiffType {
    /// Column only in left
    LeftOnly,
    /// Column only in right
    RightOnly,
    /// Column exists in both but types differ
    TypeDifferent,
}

/// Engine for comparing Parquet files using Polars
pub struct ParquetDiffEngine {
    max_row_diffs: usize,
    /// Columns to use as keys for row matching (if empty, use row index)
    key_columns: Vec<String>,
}

impl ParquetDiffEngine {
    pub fn new() -> Self {
        Self {
            max_row_diffs: 100,
            key_columns: Vec::new(),
        }
    }

    pub fn with_max_row_diffs(mut self, max: usize) -> Self {
        self.max_row_diffs = max;
        self
    }

    pub fn with_key_columns(mut self, columns: Vec<String>) -> Self {
        self.key_columns = columns;
        self
    }

    /// Compare two Parquet files
    pub fn compare_parquet_files(
        &self,
        left: &Path,
        right: &Path,
    ) -> Result<ParquetDiffResult, RCompareError> {
        // Read Parquet files using Polars
        let left_df = LazyFrame::scan_parquet(left, ScanArgsParquet::default())
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read left Parquet file: {}", e),
                ))
            })?
            .collect()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to collect left DataFrame: {}", e),
                ))
            })?;

        let right_df = LazyFrame::scan_parquet(right, ScanArgsParquet::default())
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to read right Parquet file: {}", e),
                ))
            })?
            .collect()
            .map_err(|e| {
                RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("Failed to collect right DataFrame: {}", e),
                ))
            })?;

        self.compare_dataframes(&left_df, &right_df)
    }

    /// Compare two Polars DataFrames
    pub fn compare_dataframes(
        &self,
        left: &DataFrame,
        right: &DataFrame,
    ) -> Result<ParquetDiffResult, RCompareError> {
        // Compare schemas
        let schema_diffs = self.compare_schemas(left.schema(), right.schema());

        let columns: Vec<String> = left
            .get_column_names()
            .iter()
            .map(|s| s.to_string())
            .collect();

        // If key columns are specified, use them for matching
        if !self.key_columns.is_empty() {
            self.compare_with_keys(left, right, columns, schema_diffs)
        } else {
            // Compare row by row using index
            self.compare_by_index(left, right, columns, schema_diffs)
        }
    }

    fn compare_schemas(&self, left: &Schema, right: &Schema) -> Vec<SchemaDiff> {
        let mut diffs = Vec::new();
        let left_fields: HashMap<_, _> = left
            .iter()
            .map(|(name, dtype)| (name.clone(), dtype))
            .collect();
        let right_fields: HashMap<_, _> = right
            .iter()
            .map(|(name, dtype)| (name.clone(), dtype))
            .collect();

        // Check for columns only in left or type differences
        for (name, left_type) in &left_fields {
            if let Some(right_type) = right_fields.get(name) {
                if left_type != right_type {
                    diffs.push(SchemaDiff {
                        diff_type: SchemaDiffType::TypeDifferent,
                        column: name.to_string(),
                        left_type: Some(format!("{:?}", left_type)),
                        right_type: Some(format!("{:?}", right_type)),
                    });
                }
            } else {
                diffs.push(SchemaDiff {
                    diff_type: SchemaDiffType::LeftOnly,
                    column: name.to_string(),
                    left_type: Some(format!("{:?}", left_type)),
                    right_type: None,
                });
            }
        }

        // Check for columns only in right
        for (name, right_type) in &right_fields {
            if !left_fields.contains_key(name) {
                diffs.push(SchemaDiff {
                    diff_type: SchemaDiffType::RightOnly,
                    column: name.to_string(),
                    left_type: None,
                    right_type: Some(format!("{:?}", right_type)),
                });
            }
        }

        diffs
    }

    fn compare_by_index(
        &self,
        left: &DataFrame,
        right: &DataFrame,
        columns: Vec<String>,
        schema_diffs: Vec<SchemaDiff>,
    ) -> Result<ParquetDiffResult, RCompareError> {
        let left_rows = left.height();
        let right_rows = right.height();
        let max_rows = left_rows.max(right_rows);

        let mut identical_rows = 0;
        let mut different_rows = 0;
        let mut left_only_rows = 0;
        let mut right_only_rows = 0;
        let mut row_diffs = Vec::new();

        // Get common columns for comparison
        let common_cols: Vec<_> = columns
            .iter()
            .filter(|col| {
                left.column(col).is_ok() && right.column(col).is_ok()
            })
            .cloned()
            .collect();

        for i in 0..max_rows {
            if i >= left_rows {
                // Row only in right
                right_only_rows += 1;
                if row_diffs.len() < self.max_row_diffs {
                    row_diffs.push(RowDiff {
                        left_row: None,
                        right_row: Some(i),
                        diff_type: RowDiffType::RightOnly,
                        column_diffs: Vec::new(),
                    });
                }
            } else if i >= right_rows {
                // Row only in left
                left_only_rows += 1;
                if row_diffs.len() < self.max_row_diffs {
                    row_diffs.push(RowDiff {
                        left_row: Some(i),
                        right_row: None,
                        diff_type: RowDiffType::LeftOnly,
                        column_diffs: Vec::new(),
                    });
                }
            } else {
                // Compare rows
                let mut col_diffs = Vec::new();
                for col in &common_cols {
                    let left_val = self.get_cell_value(left, col, i)?;
                    let right_val = self.get_cell_value(right, col, i)?;

                    if left_val != right_val {
                        col_diffs.push(ColumnDiff {
                            column: col.clone(),
                            left_value: left_val,
                            right_value: right_val,
                        });
                    }
                }

                if col_diffs.is_empty() {
                    identical_rows += 1;
                } else {
                    different_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            left_row: Some(i),
                            right_row: Some(i),
                            diff_type: RowDiffType::ValueDifferent,
                            column_diffs: col_diffs,
                        });
                    }
                }
            }
        }

        Ok(ParquetDiffResult {
            total_rows: max_rows,
            different_rows,
            left_only_rows,
            right_only_rows,
            identical_rows,
            columns,
            row_diffs,
            schema_diffs,
        })
    }

    fn compare_with_keys(
        &self,
        left: &DataFrame,
        right: &DataFrame,
        columns: Vec<String>,
        schema_diffs: Vec<SchemaDiff>,
    ) -> Result<ParquetDiffResult, RCompareError> {
        // Create key -> row index maps
        let left_keys = self.build_key_map(left)?;
        let right_keys = self.build_key_map(right)?;

        let mut all_keys: Vec<String> = left_keys.keys().chain(right_keys.keys()).cloned().collect();
        all_keys.sort();
        all_keys.dedup();

        let mut identical_rows = 0;
        let mut different_rows = 0;
        let mut left_only_rows = 0;
        let mut right_only_rows = 0;
        let mut row_diffs = Vec::new();

        let common_cols: Vec<_> = columns
            .iter()
            .filter(|col| left.column(col).is_ok() && right.column(col).is_ok())
            .cloned()
            .collect();

        for key in &all_keys {
            let left_idx = left_keys.get(key);
            let right_idx = right_keys.get(key);

            match (left_idx, right_idx) {
                (Some(&li), Some(&ri)) => {
                    // Compare rows
                    let mut col_diffs = Vec::new();
                    for col in &common_cols {
                        let left_val = self.get_cell_value(left, col, li)?;
                        let right_val = self.get_cell_value(right, col, ri)?;

                        if left_val != right_val {
                            col_diffs.push(ColumnDiff {
                                column: col.clone(),
                                left_value: left_val,
                                right_value: right_val,
                            });
                        }
                    }

                    if col_diffs.is_empty() {
                        identical_rows += 1;
                    } else {
                        different_rows += 1;
                        if row_diffs.len() < self.max_row_diffs {
                            row_diffs.push(RowDiff {
                                left_row: Some(li),
                                right_row: Some(ri),
                                diff_type: RowDiffType::ValueDifferent,
                                column_diffs: col_diffs,
                            });
                        }
                    }
                }
                (Some(&li), None) => {
                    left_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            left_row: Some(li),
                            right_row: None,
                            diff_type: RowDiffType::LeftOnly,
                            column_diffs: Vec::new(),
                        });
                    }
                }
                (None, Some(&ri)) => {
                    right_only_rows += 1;
                    if row_diffs.len() < self.max_row_diffs {
                        row_diffs.push(RowDiff {
                            left_row: None,
                            right_row: Some(ri),
                            diff_type: RowDiffType::RightOnly,
                            column_diffs: Vec::new(),
                        });
                    }
                }
                (None, None) => unreachable!(),
            }
        }

        Ok(ParquetDiffResult {
            total_rows: all_keys.len(),
            different_rows,
            left_only_rows,
            right_only_rows,
            identical_rows,
            columns,
            row_diffs,
            schema_diffs,
        })
    }

    fn build_key_map(&self, df: &DataFrame) -> Result<HashMap<String, usize>, RCompareError> {
        let mut map = HashMap::new();

        for i in 0..df.height() {
            let mut key_parts = Vec::new();
            for col in &self.key_columns {
                let val = self.get_cell_value(df, col, i)?;
                key_parts.push(val);
            }
            let key = key_parts.join("|");
            map.insert(key, i);
        }

        Ok(map)
    }

    fn get_cell_value(
        &self,
        df: &DataFrame,
        column: &str,
        row: usize,
    ) -> Result<String, RCompareError> {
        let series = df.column(column).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to get column {}: {}", column, e),
            ))
        })?;

        let val = series.get(row).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to get value at row {}: {}", row, e),
            ))
        })?;

        Ok(format!("{}", val))
    }
}

impl Default for ParquetDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a file path appears to be a Parquet file based on extension
pub fn is_parquet_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(ext.as_str(), "parquet" | "pq")
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::prelude::*;

    fn create_test_dataframe() -> DataFrame {
        df! {
            "id" => &[1, 2, 3],
            "name" => &["Alice", "Bob", "Charlie"],
            "age" => &[30, 25, 35],
        }
        .unwrap()
    }

    #[test]
    fn test_identical_dataframes() {
        let df1 = create_test_dataframe();
        let df2 = create_test_dataframe();

        let engine = ParquetDiffEngine::new();
        let result = engine.compare_dataframes(&df1, &df2).unwrap();

        assert_eq!(result.identical_rows, 3);
        assert_eq!(result.different_rows, 0);
        assert_eq!(result.left_only_rows, 0);
        assert_eq!(result.right_only_rows, 0);
    }

    #[test]
    fn test_different_values() {
        let df1 = df! {
            "id" => &[1, 2, 3],
            "name" => &["Alice", "Bob", "Charlie"],
            "age" => &[30, 25, 35],
        }
        .unwrap();

        let df2 = df! {
            "id" => &[1, 2, 3],
            "name" => &["Alice", "Bob", "Charlie"],
            "age" => &[30, 26, 35], // Bob's age changed
        }
        .unwrap();

        let engine = ParquetDiffEngine::new();
        let result = engine.compare_dataframes(&df1, &df2).unwrap();

        assert_eq!(result.identical_rows, 2);
        assert_eq!(result.different_rows, 1);
        assert_eq!(result.row_diffs.len(), 1);
    }

    #[test]
    fn test_different_row_counts() {
        let df1 = create_test_dataframe();
        let df2 = df! {
            "id" => &[1, 2],
            "name" => &["Alice", "Bob"],
            "age" => &[30, 25],
        }
        .unwrap();

        let engine = ParquetDiffEngine::new();
        let result = engine.compare_dataframes(&df1, &df2).unwrap();

        assert_eq!(result.identical_rows, 2);
        assert_eq!(result.left_only_rows, 1);
    }

    #[test]
    fn test_is_parquet_file() {
        assert!(is_parquet_file(Path::new("data.parquet")));
        assert!(is_parquet_file(Path::new("data.pq")));
        assert!(is_parquet_file(Path::new("DATA.PARQUET")));
        assert!(!is_parquet_file(Path::new("data.csv")));
        assert!(!is_parquet_file(Path::new("data.txt")));
    }
}
