use rcompare_common::{
    DifferenceType, FilePatch, Hunk, PatchDifference, RCompareError,
};
use regex::Regex;
use std::sync::LazyLock;

static HEADER1: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^--- ([^\t]+)(?:\t([^\t]+)(?:\t(.*))?)?$").unwrap()
});

static HEADER2: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\+\+\+ ([^\t]+)(?:\t([^\t]+)(?:\t(.*))?)?$").unwrap()
});

static HUNK_HEADER: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$").unwrap()
});

/// Parse unified diff format into a list of FilePatches.
/// Returns one FilePatch per file pair found in the input.
pub fn parse_unified(lines: &[&str]) -> Result<Vec<FilePatch>, RCompareError> {
    let mut file_patches = Vec::new();
    let mut i = 0;

    while i < lines.len() {
        // Look for --- header
        if let Some(cap1) = HEADER1.captures(lines[i]) {
            // Next line should be +++ header
            if i + 1 >= lines.len() {
                i += 1;
                continue;
            }
            if let Some(cap2) = HEADER2.captures(lines[i + 1]) {
                let mut fp = FilePatch::new();
                fp.source = cap1.get(1).map_or("", |m| m.as_str()).to_string();
                fp.source_timestamp = cap1.get(2).map_or("", |m| m.as_str()).to_string();
                fp.source_revision = cap1.get(3).map_or("", |m| m.as_str()).to_string();
                fp.destination = cap2.get(1).map_or("", |m| m.as_str()).to_string();
                fp.dest_timestamp = cap2.get(2).map_or("", |m| m.as_str()).to_string();
                fp.dest_revision = cap2.get(3).map_or("", |m| m.as_str()).to_string();

                i += 2;

                // Parse hunks
                while i < lines.len() {
                    if let Some(hunk_cap) = HUNK_HEADER.captures(lines[i]) {
                        let src_start: usize = hunk_cap[1].parse().unwrap_or(0);
                        let src_count: usize = hunk_cap
                            .get(2)
                            .map_or(1, |m| m.as_str().parse().unwrap_or(1));
                        let dst_start: usize = hunk_cap[3].parse().unwrap_or(0);
                        let dst_count: usize = hunk_cap
                            .get(4)
                            .map_or(1, |m| m.as_str().parse().unwrap_or(1));
                        let func_name = hunk_cap
                            .get(5)
                            .map(|m| m.as_str().trim())
                            .filter(|s| !s.is_empty())
                            .map(|s| s.to_string());

                        let mut hunk = Hunk::new(src_start, dst_start);
                        hunk.source_count = src_count;
                        hunk.dest_count = dst_count;
                        hunk.function_name = func_name;

                        i += 1;

                        // Parse hunk body
                        let mut src_line = src_start;
                        let mut dst_line = dst_start;
                        // Accumulate consecutive same-type lines into one PatchDifference
                        let mut current_diff: Option<PatchDifference> = None;
                        let mut current_type: Option<char> = None;

                        while i < lines.len() {
                            let line = lines[i];
                            if line.is_empty() {
                                // Treat empty line as context (space prefix)
                                // but only if we're still within expected counts
                                break;
                            }
                            // Check if this line starts a new file header or hunk
                            if HEADER1.is_match(line) || HUNK_HEADER.is_match(line) {
                                break;
                            }
                            let first = line.as_bytes()[0];
                            match first {
                                b' ' => {
                                    // Context line - flush any pending diff
                                    if let Some(diff) = current_diff.take() {
                                        hunk.differences.push(diff);
                                        current_type = None;
                                    }
                                    // Start or continue Unchanged block
                                    if current_type != Some(' ') {
                                        current_diff = Some(PatchDifference::new(
                                            DifferenceType::Unchanged,
                                            src_line,
                                            dst_line,
                                        ));
                                        current_type = Some(' ');
                                    }
                                    let content = &line[1..];
                                    if let Some(ref mut d) = current_diff {
                                        d.source_lines.push(format!("{content}\n"));
                                        d.dest_lines.push(format!("{content}\n"));
                                    }
                                    src_line += 1;
                                    dst_line += 1;
                                    i += 1;
                                }
                                b'-' => {
                                    // Removed line
                                    // If we were accumulating '+' lines, this is a Change block
                                    // If we were accumulating '-' lines, continue
                                    // Otherwise start new delete block
                                    if current_type == Some(' ') || current_type == Some('+') {
                                        if let Some(diff) = current_diff.take() {
                                            hunk.differences.push(diff);
                                        }
                                        current_type = None;
                                    }
                                    if current_type != Some('-') {
                                        current_diff = Some(PatchDifference::new(
                                            DifferenceType::Delete,
                                            src_line,
                                            dst_line,
                                        ));
                                        current_type = Some('-');
                                    }
                                    let content = &line[1..];
                                    if let Some(ref mut d) = current_diff {
                                        d.source_lines.push(format!("{content}\n"));
                                    }
                                    src_line += 1;
                                    i += 1;
                                }
                                b'+' => {
                                    // Added line
                                    if current_type == Some(' ') {
                                        if let Some(diff) = current_diff.take() {
                                            hunk.differences.push(diff);
                                        }
                                        current_type = None;
                                    }
                                    if current_type == Some('-') {
                                        // Switch from Delete to Change
                                        if let Some(ref mut d) = current_diff {
                                            d.diff_type = DifferenceType::Change;
                                        }
                                        current_type = Some('+');
                                    } else if current_type != Some('+') {
                                        current_diff = Some(PatchDifference::new(
                                            DifferenceType::Insert,
                                            src_line,
                                            dst_line,
                                        ));
                                        current_type = Some('+');
                                    }
                                    let content = &line[1..];
                                    if let Some(ref mut d) = current_diff {
                                        d.dest_lines.push(format!("{content}\n"));
                                    }
                                    dst_line += 1;
                                    i += 1;
                                }
                                _ => {
                                    // Not a hunk body line, stop
                                    break;
                                }
                            }
                        }

                        // Flush remaining diff
                        if let Some(diff) = current_diff.take() {
                            hunk.differences.push(diff);
                        }

                        fp.hunks.push(hunk);
                    } else if HEADER1.is_match(lines[i]) {
                        // Next file pair starts
                        break;
                    } else {
                        // Skip non-hunk lines (e.g., "diff --git" headers)
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_unified() {
        let input = "\
--- a/file.txt\t2024-01-01 00:00:00
+++ b/file.txt\t2024-01-02 00:00:00
@@ -1,3 +1,3 @@
 line1
-line2
+line2_modified
 line3";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();

        assert_eq!(result.len(), 1);
        let fp = &result[0];
        assert_eq!(fp.source, "a/file.txt");
        assert_eq!(fp.destination, "b/file.txt");
        assert_eq!(fp.source_timestamp, "2024-01-01 00:00:00");
        assert_eq!(fp.hunks.len(), 1);

        let hunk = &fp.hunks[0];
        assert_eq!(hunk.source_start, 1);
        assert_eq!(hunk.source_count, 3);
        assert_eq!(hunk.dest_start, 1);
        assert_eq!(hunk.dest_count, 3);
        // Should have: Unchanged(line1), Change(line2->line2_modified), Unchanged(line3)
        assert_eq!(hunk.differences.len(), 3);
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Unchanged);
        assert_eq!(hunk.differences[1].diff_type, DifferenceType::Change);
        assert_eq!(hunk.differences[1].source_lines.len(), 1);
        assert_eq!(hunk.differences[1].dest_lines.len(), 1);
        assert_eq!(hunk.differences[2].diff_type, DifferenceType::Unchanged);
    }

    #[test]
    fn test_parse_insert_only() {
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,2 +1,4 @@
 line1
+added1
+added2
 line2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        // Unchanged(line1), Insert(added1, added2), Unchanged(line2)
        assert_eq!(hunk.differences.len(), 3);
        assert_eq!(hunk.differences[1].diff_type, DifferenceType::Insert);
        assert_eq!(hunk.differences[1].dest_lines.len(), 2);
    }

    #[test]
    fn test_parse_delete_only() {
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,4 +1,2 @@
 line1
-removed1
-removed2
 line2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences.len(), 3);
        assert_eq!(hunk.differences[1].diff_type, DifferenceType::Delete);
        assert_eq!(hunk.differences[1].source_lines.len(), 2);
    }

    #[test]
    fn test_parse_multiple_hunks() {
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,3 +1,3 @@
 line1
-old1
+new1
 line3
@@ -10,3 +10,3 @@
 line10
-old10
+new10
 line12";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        assert_eq!(result[0].hunks.len(), 2);
        assert_eq!(result[0].hunks[0].source_start, 1);
        assert_eq!(result[0].hunks[1].source_start, 10);
    }

    #[test]
    fn test_parse_multiple_files() {
        let input = "\
--- a/first.txt\t2024-01-01
+++ b/first.txt\t2024-01-02
@@ -1,2 +1,2 @@
-old
+new
 ctx
--- a/second.txt\t2024-01-01
+++ b/second.txt\t2024-01-02
@@ -1,2 +1,2 @@
 ctx
-old2
+new2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].source, "a/first.txt");
        assert_eq!(result[1].source, "a/second.txt");
    }

    #[test]
    fn test_parse_with_function_name() {
        let input = "\
--- a/file.c\t2024-01-01
+++ b/file.c\t2024-01-02
@@ -10,3 +10,3 @@ int main()
 line10
-old
+new
 line12";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        assert_eq!(
            result[0].hunks[0].function_name.as_deref(),
            Some("int main()")
        );
    }

    #[test]
    fn test_parse_with_revision() {
        let input = "\
--- a/file.txt\t2024-01-01\t1.1
+++ b/file.txt\t2024-01-02\t1.2
@@ -1,1 +1,1 @@
-old
+new";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_unified(&lines).unwrap();
        assert_eq!(result[0].source_revision, "1.1");
        assert_eq!(result[0].dest_revision, "1.2");
    }
}
