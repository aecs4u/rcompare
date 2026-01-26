use rcompare_common::RCompareError;
use std::path::Path;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};

/// Represents a chunk of binary data for hex viewing
#[derive(Debug, Clone)]
pub struct HexChunk {
    pub offset: u64,
    pub left_data: Vec<u8>,
    pub right_data: Vec<u8>,
    pub differences: Vec<usize>, // Indices where bytes differ
}

/// Binary comparison engine
pub struct BinaryDiffEngine {
    chunk_size: usize,
}

impl BinaryDiffEngine {
    pub fn new(chunk_size: usize) -> Self {
        Self { chunk_size }
    }

    /// Compare two binary files and identify differences
    pub fn compare_files(&self, left_path: &Path, right_path: &Path) -> Result<Vec<HexChunk>, RCompareError> {
        let mut left_file = File::open(left_path)?;
        let mut right_file = File::open(right_path)?;

        let left_len = left_file.metadata()?.len();
        let right_len = right_file.metadata()?.len();
        let max_len = left_len.max(right_len);

        let mut chunks = Vec::new();
        let mut offset = 0u64;

        while offset < max_len {
            let chunk = self.read_chunk(&mut left_file, &mut right_file, offset)?;
            chunks.push(chunk);
            offset += self.chunk_size as u64;
        }

        Ok(chunks)
    }

    /// Read a chunk at a specific offset with lazy loading
    pub fn read_chunk_at_offset(
        &self,
        left_path: &Path,
        right_path: &Path,
        offset: u64,
    ) -> Result<HexChunk, RCompareError> {
        let mut left_file = File::open(left_path)?;
        let mut right_file = File::open(right_path)?;

        left_file.seek(SeekFrom::Start(offset))?;
        right_file.seek(SeekFrom::Start(offset))?;

        self.read_chunk(&mut left_file, &mut right_file, offset)
    }

    fn read_chunk(
        &self,
        left_file: &mut File,
        right_file: &mut File,
        offset: u64,
    ) -> Result<HexChunk, RCompareError> {
        let mut left_data = vec![0u8; self.chunk_size];
        let mut right_data = vec![0u8; self.chunk_size];

        let left_read = left_file.read(&mut left_data)?;
        let right_read = right_file.read(&mut right_data)?;

        left_data.truncate(left_read);
        right_data.truncate(right_read);

        let differences = self.find_differences(&left_data, &right_data);

        Ok(HexChunk {
            offset,
            left_data,
            right_data,
            differences,
        })
    }

    fn find_differences(&self, left: &[u8], right: &[u8]) -> Vec<usize> {
        let min_len = left.len().min(right.len());
        let mut diffs = Vec::new();

        for i in 0..min_len {
            if left[i] != right[i] {
                diffs.push(i);
            }
        }

        // If lengths differ, mark all extra bytes as different
        if left.len() != right.len() {
            for i in min_len..left.len().max(right.len()) {
                diffs.push(i);
            }
        }

        diffs
    }

    /// Format a hex chunk for display
    pub fn format_hex_line(&self, offset: u64, data: &[u8]) -> String {
        let mut result = format!("{:08X}  ", offset);

        // Hex representation
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

        result.push_str(" |");

        // ASCII representation
        for byte in data {
            let ch = if byte.is_ascii_graphic() || *byte == b' ' {
                *byte as char
            } else {
                '.'
            };
            result.push(ch);
        }

        result.push('|');
        result
    }

    /// Quick binary comparison (checks if files are identical)
    pub fn are_files_identical(&self, left_path: &Path, right_path: &Path) -> Result<bool, RCompareError> {
        let left_meta = std::fs::metadata(left_path)?;
        let right_meta = std::fs::metadata(right_path)?;

        // Quick size check
        if left_meta.len() != right_meta.len() {
            return Ok(false);
        }

        let mut left_file = File::open(left_path)?;
        let mut right_file = File::open(right_path)?;

        let mut left_buf = vec![0u8; 8192];
        let mut right_buf = vec![0u8; 8192];

        loop {
            let left_read = left_file.read(&mut left_buf)?;
            let right_read = right_file.read(&mut right_buf)?;

            if left_read != right_read {
                return Ok(false);
            }

            if left_read == 0 {
                break; // EOF
            }

            if left_buf[..left_read] != right_buf[..right_read] {
                return Ok(false);
            }
        }

        Ok(true)
    }
}

impl Default for BinaryDiffEngine {
    fn default() -> Self {
        Self::new(256) // 256 bytes per chunk (16 rows of 16 bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_identical_files() {
        let mut left = NamedTempFile::new().unwrap();
        let mut right = NamedTempFile::new().unwrap();

        left.write_all(b"Hello World").unwrap();
        right.write_all(b"Hello World").unwrap();

        let engine = BinaryDiffEngine::default();
        assert!(engine.are_files_identical(left.path(), right.path()).unwrap());
    }

    #[test]
    fn test_different_files() {
        let mut left = NamedTempFile::new().unwrap();
        let mut right = NamedTempFile::new().unwrap();

        left.write_all(b"Hello World").unwrap();
        right.write_all(b"Hello Rust!").unwrap();

        let engine = BinaryDiffEngine::default();
        assert!(!engine.are_files_identical(left.path(), right.path()).unwrap());
    }

    #[test]
    fn test_hex_formatting() {
        let engine = BinaryDiffEngine::default();
        let data = b"Hello";
        let formatted = engine.format_hex_line(0, data);

        assert!(formatted.contains("48 65 6C 6C 6F")); // Hex for "Hello"
        assert!(formatted.contains("Hello")); // ASCII representation
    }

    #[test]
    fn test_find_differences() {
        let engine = BinaryDiffEngine::default();
        let left = b"Hello World";
        let right = b"Hello Rust!";

        let diffs = engine.find_differences(left, right);
        assert!(!diffs.is_empty());
        assert!(diffs.contains(&6)); // 'W' vs 'R'
    }
}
