use rcompare_common::{
    DifferenceType, FilePatch, Hunk, PatchDifference, RCompareError,
};
use regex::Regex;
use std::sync::LazyLock;

// Context diff file headers: *** source_file\ttimestamp and --- dest_file\ttimestamp
static FILE_HEADER_SRC: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\*\*\* ([^\t]+)(?:\t(.*))?$").unwrap()
});

static FILE_HEADER_DST: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^--- ([^\t]+)(?:\t(.*))?$").unwrap()
});

// Hunk separator: 15 asterisks, optionally followed by function name
static HUNK_SEPARATOR: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\*{15}\s?(.*)$").unwrap()
});

// Source range: *** start,end ***
static SRC_RANGE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\*\*\* (\d+)(?:,(\d+))? \*\*\*\*?$").unwrap()
});

// Dest range: --- start,end ----
static DST_RANGE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^--- (\d+)(?:,(\d+))? ----?$").unwrap()
});

/// Parse context diff format into a list of FilePatches.
pub fn parse_context(lines: &[&str]) -> Result<Vec<FilePatch>, RCompareError> {
    let mut file_patches = Vec::new();
    let mut i = 0;

    while i < lines.len() {
        // Look for *** source file header
        if let Some(src_cap) = FILE_HEADER_SRC.captures(lines[i]) {
            if i + 1 >= lines.len() {
                i += 1;
                continue;
            }
            if let Some(dst_cap) = FILE_HEADER_DST.captures(lines[i + 1]) {
                let mut fp = FilePatch::new();
                fp.source = src_cap.get(1).map_or("", |m| m.as_str()).to_string();
                fp.source_timestamp = src_cap.get(2).map_or("", |m| m.as_str()).to_string();
                fp.destination = dst_cap.get(1).map_or("", |m| m.as_str()).to_string();
                fp.dest_timestamp = dst_cap.get(2).map_or("", |m| m.as_str()).to_string();

                i += 2;

                // Parse hunks (each starts with ***************)
                while i < lines.len() {
                    if let Some(sep_cap) = HUNK_SEPARATOR.captures(lines[i]) {
                        let func = sep_cap
                            .get(1)
                            .map(|m| m.as_str().trim())
                            .filter(|s| !s.is_empty())
                            .map(|s| s.to_string());

                        i += 1;

                        // Parse source section: *** start,end ***
                        let (src_start, src_end, src_lines) = if i < lines.len() {
                            if let Some(src_range) = SRC_RANGE.captures(lines[i]) {
                                let start: usize = src_range[1].parse().unwrap_or(0);
                                let end: usize = src_range
                                    .get(2)
                                    .map_or(start, |m| m.as_str().parse().unwrap_or(start));
                                i += 1;
                                let src_body = collect_context_body(lines, &mut i);
                                (start, end, src_body)
                            } else {
                                (0, 0, Vec::new())
                            }
                        } else {
                            (0, 0, Vec::new())
                        };

                        // Parse dest section: --- start,end ----
                        let (dst_start, dst_end, dst_lines) = if i < lines.len() {
                            if let Some(dst_range) = DST_RANGE.captures(lines[i]) {
                                let start: usize = dst_range[1].parse().unwrap_or(0);
                                let end: usize = dst_range
                                    .get(2)
                                    .map_or(start, |m| m.as_str().parse().unwrap_or(start));
                                i += 1;
                                let dst_body = collect_context_body(lines, &mut i);
                                (start, end, dst_body)
                            } else {
                                (0, 0, Vec::new())
                            }
                        } else {
                            (0, 0, Vec::new())
                        };

                        let src_count = if src_end >= src_start {
                            src_end - src_start + 1
                        } else {
                            0
                        };
                        let dst_count = if dst_end >= dst_start {
                            dst_end - dst_start + 1
                        } else {
                            0
                        };

                        let mut hunk = Hunk::new(src_start, dst_start);
                        hunk.source_count = src_count;
                        hunk.dest_count = dst_count;
                        hunk.function_name = func;

                        // Merge source and destination lines into differences
                        merge_context_diffs(
                            &mut hunk,
                            &src_lines,
                            &dst_lines,
                            src_start,
                            dst_start,
                        );

                        fp.hunks.push(hunk);
                    } else if FILE_HEADER_SRC.is_match(lines[i]) {
                        // Next file starts
                        break;
                    } else {
                        i += 1;
                    }
                }

                file_patches.push(fp);
            } else {
                i += 1;
            }
        } else {
            i += 1;
        }
    }

    Ok(file_patches)
}

/// A tagged line from context diff body
#[derive(Debug, Clone)]
enum ContextLine {
    /// Context line (space prefix)
    Context(String),
    /// Added line (+ prefix)
    Added(String),
    /// Removed line (- prefix)
    Removed(String),
    /// Changed line (! prefix)
    Changed(String),
}

fn collect_context_body(lines: &[&str], i: &mut usize) -> Vec<ContextLine> {
    let mut body = Vec::new();
    while *i < lines.len() {
        let line = lines[*i];
        if line.len() >= 2 {
            match &line[..2] {
                "  " => {
                    body.push(ContextLine::Context(line[2..].to_string()));
                    *i += 1;
                }
                "- " => {
                    body.push(ContextLine::Removed(line[2..].to_string()));
                    *i += 1;
                }
                "+ " => {
                    body.push(ContextLine::Added(line[2..].to_string()));
                    *i += 1;
                }
                "! " => {
                    body.push(ContextLine::Changed(line[2..].to_string()));
                    *i += 1;
                }
                _ => break,
            }
        } else {
            break;
        }
    }
    body
}

fn merge_context_diffs(
    hunk: &mut Hunk,
    src_lines: &[ContextLine],
    dst_lines: &[ContextLine],
    src_start: usize,
    dst_start: usize,
) {
    let mut si = 0;
    let mut di = 0;
    let mut src_line_no = src_start;
    let mut dst_line_no = dst_start;

    while si < src_lines.len() || di < dst_lines.len() {
        // Context lines from source side
        if si < src_lines.len() {
            if let ContextLine::Context(ref text) = src_lines[si] {
                let mut diff =
                    PatchDifference::new(DifferenceType::Unchanged, src_line_no, dst_line_no);
                diff.source_lines.push(format!("{text}\n"));
                diff.dest_lines.push(format!("{text}\n"));
                hunk.differences.push(diff);
                si += 1;
                // Advance dest past matching context
                if di < dst_lines.len() {
                    if let ContextLine::Context(_) = dst_lines[di] {
                        di += 1;
                    }
                }
                src_line_no += 1;
                dst_line_no += 1;
                continue;
            }
        }

        // Removed lines (source only)
        if si < src_lines.len() {
            if let ContextLine::Removed(ref _text) = src_lines[si] {
                let mut diff =
                    PatchDifference::new(DifferenceType::Delete, src_line_no, dst_line_no);
                while si < src_lines.len() {
                    if let ContextLine::Removed(ref text) = src_lines[si] {
                        diff.source_lines.push(format!("{text}\n"));
                        si += 1;
                        src_line_no += 1;
                    } else {
                        break;
                    }
                }
                hunk.differences.push(diff);
                continue;
            }
        }

        // Added lines (dest only)
        if di < dst_lines.len() {
            if let ContextLine::Added(ref _text) = dst_lines[di] {
                let mut diff =
                    PatchDifference::new(DifferenceType::Insert, src_line_no, dst_line_no);
                while di < dst_lines.len() {
                    if let ContextLine::Added(ref text) = dst_lines[di] {
                        diff.dest_lines.push(format!("{text}\n"));
                        di += 1;
                        dst_line_no += 1;
                    } else {
                        break;
                    }
                }
                hunk.differences.push(diff);
                continue;
            }
        }

        // Changed lines (! in both source and dest)
        if si < src_lines.len() {
            if let ContextLine::Changed(ref _text) = src_lines[si] {
                let mut diff =
                    PatchDifference::new(DifferenceType::Change, src_line_no, dst_line_no);
                while si < src_lines.len() {
                    if let ContextLine::Changed(ref text) = src_lines[si] {
                        diff.source_lines.push(format!("{text}\n"));
                        si += 1;
                        src_line_no += 1;
                    } else {
                        break;
                    }
                }
                while di < dst_lines.len() {
                    if let ContextLine::Changed(ref text) = dst_lines[di] {
                        diff.dest_lines.push(format!("{text}\n"));
                        di += 1;
                        dst_line_no += 1;
                    } else {
                        break;
                    }
                }
                hunk.differences.push(diff);
                continue;
            }
        }

        // Skip context on dest side if source is exhausted
        if di < dst_lines.len() {
            if let ContextLine::Context(ref text) = dst_lines[di] {
                let mut diff =
                    PatchDifference::new(DifferenceType::Unchanged, src_line_no, dst_line_no);
                diff.source_lines.push(format!("{text}\n"));
                diff.dest_lines.push(format!("{text}\n"));
                hunk.differences.push(diff);
                di += 1;
                src_line_no += 1;
                dst_line_no += 1;
                continue;
            }
        }

        // Safety: advance to avoid infinite loop
        if si < src_lines.len() {
            si += 1;
        }
        if di < dst_lines.len() {
            di += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_context_diff() {
        let input = "\
*** a/file.txt\t2024-01-01
--- b/file.txt\t2024-01-02
***************
*** 1,3 ****
  line1
! old_line
  line3
--- 1,3 ----
  line1
! new_line
  line3";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_context(&lines).unwrap();

        assert_eq!(result.len(), 1);
        let fp = &result[0];
        assert_eq!(fp.source, "a/file.txt");
        assert_eq!(fp.destination, "b/file.txt");
        assert_eq!(fp.hunks.len(), 1);

        let hunk = &fp.hunks[0];
        // Should have Unchanged, Change, Unchanged
        assert!(hunk.differences.len() >= 2);
        let change = hunk
            .differences
            .iter()
            .find(|d| d.diff_type == DifferenceType::Change);
        assert!(change.is_some());
        let change = change.unwrap();
        assert_eq!(change.source_lines.len(), 1);
        assert_eq!(change.dest_lines.len(), 1);
    }

    #[test]
    fn test_parse_context_delete() {
        let input = "\
*** a/file.txt\t2024-01-01
--- b/file.txt\t2024-01-02
***************
*** 1,3 ****
  line1
- removed
  line3
--- 1,2 ----
  line1
  line3";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_context(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        let delete = hunk
            .differences
            .iter()
            .find(|d| d.diff_type == DifferenceType::Delete);
        assert!(delete.is_some());
    }

    #[test]
    fn test_parse_context_insert() {
        let input = "\
*** a/file.txt\t2024-01-01
--- b/file.txt\t2024-01-02
***************
*** 1,2 ****
  line1
  line2
--- 1,3 ----
  line1
+ added
  line2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_context(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        let insert = hunk
            .differences
            .iter()
            .find(|d| d.diff_type == DifferenceType::Insert);
        assert!(insert.is_some());
    }
}
