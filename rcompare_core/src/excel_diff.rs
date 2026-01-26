use calamine::{open_workbook_auto, Data, DataType, Range, Reader};
use rcompare_common::RCompareError;
use std::collections::HashMap;
use std::path::Path;

/// Result of an Excel workbook comparison
#[derive(Debug, Clone)]
pub struct ExcelDiffResult {
    /// Total number of sheets
    pub total_sheets: usize,
    /// Number of sheets that differ
    pub different_sheets: usize,
    /// Number of sheets only in left
    pub left_only_sheets: usize,
    /// Number of sheets only in right
    pub right_only_sheets: usize,
    /// Number of identical sheets
    pub identical_sheets: usize,
    /// Sheet names match
    pub sheet_names_match: bool,
    /// Left sheet names
    pub left_sheet_names: Vec<String>,
    /// Right sheet names
    pub right_sheet_names: Vec<String>,
    /// Detailed sheet differences (limited)
    pub sheet_diffs: Vec<SheetDiff>,
}

/// Represents a difference in a specific sheet
#[derive(Debug, Clone)]
pub struct SheetDiff {
    /// Sheet name
    pub sheet_name: String,
    /// Type of difference
    pub diff_type: SheetDiffType,
    /// Total rows in the sheet
    pub total_rows: usize,
    /// Total columns in the sheet
    pub total_cols: usize,
    /// Number of different cells
    pub different_cells: usize,
    /// Cell differences (limited to first 20)
    pub cell_diffs: Vec<CellDiff>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SheetDiffType {
    /// Sheet exists in both but data differs
    Modified,
    /// Sheet only exists in left
    LeftOnly,
    /// Sheet only exists in right
    RightOnly,
}

#[derive(Debug, Clone)]
pub struct CellDiff {
    /// Row index (0-indexed)
    pub row: usize,
    /// Column index (0-indexed)
    pub col: usize,
    /// Left value
    pub left_value: String,
    /// Right value
    pub right_value: String,
}

/// Engine for comparing Excel files
pub struct ExcelDiffEngine {
    max_sheet_diffs: usize,
    max_cell_diffs_per_sheet: usize,
}

impl ExcelDiffEngine {
    pub fn new() -> Self {
        Self {
            max_sheet_diffs: 10,
            max_cell_diffs_per_sheet: 20,
        }
    }

    pub fn with_max_sheet_diffs(mut self, max: usize) -> Self {
        self.max_sheet_diffs = max;
        self
    }

    pub fn with_max_cell_diffs_per_sheet(mut self, max: usize) -> Self {
        self.max_cell_diffs_per_sheet = max;
        self
    }

    /// Compare two Excel files
    pub fn compare_files(
        &self,
        left: &Path,
        right: &Path,
    ) -> Result<ExcelDiffResult, RCompareError> {
        // Open both workbooks
        let mut left_workbook = open_workbook_auto(left).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open left Excel file: {}", e),
            ))
        })?;

        let mut right_workbook = open_workbook_auto(right).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open right Excel file: {}", e),
            ))
        })?;

        // Get sheet names
        let left_sheet_names = left_workbook.sheet_names().to_vec();
        let right_sheet_names = right_workbook.sheet_names().to_vec();

        let sheet_names_match = left_sheet_names == right_sheet_names;

        // Build maps of sheet data
        let mut left_sheets: HashMap<String, Range<Data>> = HashMap::new();
        for sheet_name in &left_sheet_names {
            if let Ok(range) = left_workbook.worksheet_range(sheet_name) {
                left_sheets.insert(sheet_name.clone(), range);
            }
        }

        let mut right_sheets: HashMap<String, Range<Data>> = HashMap::new();
        for sheet_name in &right_sheet_names {
            if let Ok(range) = right_workbook.worksheet_range(sheet_name) {
                right_sheets.insert(sheet_name.clone(), range);
            }
        }

        // Collect all unique sheet names
        let mut all_sheet_names: Vec<String> = left_sheets
            .keys()
            .chain(right_sheets.keys())
            .cloned()
            .collect();
        all_sheet_names.sort();
        all_sheet_names.dedup();

        let total_sheets = all_sheet_names.len();
        let mut different_sheets = 0;
        let mut left_only_sheets = 0;
        let mut right_only_sheets = 0;
        let mut identical_sheets = 0;
        let mut sheet_diffs = Vec::new();

        for sheet_name in &all_sheet_names {
            let left_range = left_sheets.get(sheet_name);
            let right_range = right_sheets.get(sheet_name);

            match (left_range, right_range) {
                (Some(left), Some(right)) => {
                    if self.ranges_equal(left, right) {
                        identical_sheets += 1;
                    } else {
                        different_sheets += 1;
                        if sheet_diffs.len() < self.max_sheet_diffs {
                            let diff = self.compare_ranges(sheet_name, left, right);
                            sheet_diffs.push(diff);
                        }
                    }
                }
                (Some(_), None) => {
                    left_only_sheets += 1;
                    if sheet_diffs.len() < self.max_sheet_diffs {
                        sheet_diffs.push(SheetDiff {
                            sheet_name: sheet_name.clone(),
                            diff_type: SheetDiffType::LeftOnly,
                            total_rows: 0,
                            total_cols: 0,
                            different_cells: 0,
                            cell_diffs: vec![],
                        });
                    }
                }
                (None, Some(_)) => {
                    right_only_sheets += 1;
                    if sheet_diffs.len() < self.max_sheet_diffs {
                        sheet_diffs.push(SheetDiff {
                            sheet_name: sheet_name.clone(),
                            diff_type: SheetDiffType::RightOnly,
                            total_rows: 0,
                            total_cols: 0,
                            different_cells: 0,
                            cell_diffs: vec![],
                        });
                    }
                }
                (None, None) => unreachable!(),
            }
        }

        Ok(ExcelDiffResult {
            total_sheets,
            different_sheets,
            left_only_sheets,
            right_only_sheets,
            identical_sheets,
            sheet_names_match,
            left_sheet_names,
            right_sheet_names,
            sheet_diffs,
        })
    }

    fn ranges_equal(&self, left: &Range<Data>, right: &Range<Data>) -> bool {
        if left.get_size() != right.get_size() {
            return false;
        }

        let (rows, cols) = left.get_size();
        for row in 0..rows {
            for col in 0..cols {
                let left_cell = left.get_value((row as u32, col as u32));
                let right_cell = right.get_value((row as u32, col as u32));
                if left_cell != right_cell {
                    return false;
                }
            }
        }

        true
    }

    fn compare_ranges(
        &self,
        sheet_name: &str,
        left: &Range<Data>,
        right: &Range<Data>,
    ) -> SheetDiff {
        let left_size = left.get_size();
        let right_size = right.get_size();

        let total_rows = left_size.0.max(right_size.0);
        let total_cols = left_size.1.max(right_size.1);

        let mut different_cells = 0;
        let mut cell_diffs = Vec::new();

        for row in 0..total_rows {
            for col in 0..total_cols {
                let left_cell = if row < left_size.0 && col < left_size.1 {
                    left.get_value((row as u32, col as u32))
                } else {
                    None
                };

                let right_cell = if row < right_size.0 && col < right_size.1 {
                    right.get_value((row as u32, col as u32))
                } else {
                    None
                };

                if left_cell != right_cell {
                    different_cells += 1;
                    if cell_diffs.len() < self.max_cell_diffs_per_sheet {
                        cell_diffs.push(CellDiff {
                            row,
                            col,
                            left_value: self.format_cell(left_cell),
                            right_value: self.format_cell(right_cell),
                        });
                    }
                }
            }
        }

        SheetDiff {
            sheet_name: sheet_name.to_string(),
            diff_type: SheetDiffType::Modified,
            total_rows,
            total_cols,
            different_cells,
            cell_diffs,
        }
    }

    fn format_cell(&self, cell: Option<&Data>) -> String {
        match cell {
            Some(data) => {
                // Use the available methods from the Data trait
                if data.is_empty() {
                    String::new()
                } else if let Some(s) = data.as_string() {
                    s.to_string()
                } else if let Some(f) = data.as_f64() {
                    f.to_string()
                } else if let Some(i) = data.as_i64() {
                    i.to_string()
                } else if data.is_bool() {
                    // is_bool returns true if it's a bool, but doesn't give us the value
                    // so we use Debug formatting
                    format!("{:?}", data)
                } else {
                    // For other types (datetime, duration, error), use Debug formatting
                    format!("{:?}", data)
                }
            }
            None => String::new(),
        }
    }
}

impl Default for ExcelDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a file path appears to be an Excel file based on extension
pub fn is_excel_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(ext.as_str(), "xlsx" | "xls" | "xlsm" | "xlsb")
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_excel_file() {
        assert!(is_excel_file(Path::new("data.xlsx")));
        assert!(is_excel_file(Path::new("data.XLSX")));
        assert!(is_excel_file(Path::new("data.xls")));
        assert!(is_excel_file(Path::new("data.xlsm")));
        assert!(is_excel_file(Path::new("data.xlsb")));
        assert!(!is_excel_file(Path::new("data.txt")));
        assert!(!is_excel_file(Path::new("data.csv")));
    }
}
