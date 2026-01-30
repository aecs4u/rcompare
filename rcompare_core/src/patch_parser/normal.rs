use rcompare_common::{
    DifferenceType, FilePatch, Hunk, PatchDifference, RCompareError,
};
use regex::Regex;
use std::sync::LazyLock;

// Normal diff header: diff [-options] source destination
static DIFF_HEADER: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"^diff\s+(?:(?:-|--)[a-zA-Z0-9="\ ]+\s+)*(?:--\s+)?(.+)\s+(.+)$"#).unwrap()
});

// Added: NaM or NaM,O
static HUNK_ADDED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(\d+)a(\d+)(?:,(\d+))?$").unwrap()
});

// Removed: N,MdO or NdO
static HUNK_REMOVED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(\d+)(?:,(\d+))?d(\d+)$").unwrap()
});

// Changed: N,McO,P or NcO or NcO,P or N,McO
static HUNK_CHANGED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(\d+)(?:,(\d+))?c(\d+)(?:,(\d+))?$").unwrap()
});

/// Parse normal diff format into a list of FilePatches.
pub fn parse_normal(lines: &[&str]) -> Result<Vec<FilePatch>, RCompareError> {
    let mut file_patches = Vec::new();
    let mut i = 0;
    let mut current_fp: Option<FilePatch> = None;

    while i < lines.len() {
        // Check for diff header
        if let Some(cap) = DIFF_HEADER.captures(lines[i]) {
            if let Some(fp) = current_fp.take() {
                file_patches.push(fp);
            }
            let mut fp = FilePatch::new();
            fp.source = cap[1].to_string();
            fp.destination = cap[2].to_string();
            current_fp = Some(fp);
            i += 1;
            continue;
        }

        // Check for hunk commands
        if let Some(cap) = HUNK_ADDED.captures(lines[i]) {
            let src_line: usize = cap[1].parse().unwrap_or(0);
            let dst_start: usize = cap[2].parse().unwrap_or(0);
            let dst_end: usize = cap
                .get(3)
                .map_or(dst_start, |m| m.as_str().parse().unwrap_or(dst_start));

            i += 1;

            let mut diff =
                PatchDifference::new(DifferenceType::Insert, src_line, dst_start);
            while i < lines.len() && lines[i].starts_with("> ") {
                diff.dest_lines.push(format!("{}\n", &lines[i][2..]));
                i += 1;
            }

            let mut hunk = Hunk::new(src_line, dst_start);
            hunk.source_count = 0;
            hunk.dest_count = dst_end - dst_start + 1;
            hunk.differences.push(diff);

            if let Some(ref mut fp) = current_fp {
                fp.hunks.push(hunk);
            } else {
                let mut fp = FilePatch::new();
                fp.hunks.push(hunk);
                current_fp = Some(fp);
            }
            continue;
        }

        if let Some(cap) = HUNK_REMOVED.captures(lines[i]) {
            let src_start: usize = cap[1].parse().unwrap_or(0);
            let src_end: usize = cap
                .get(2)
                .map_or(src_start, |m| m.as_str().parse().unwrap_or(src_start));
            let dst_line: usize = cap[3].parse().unwrap_or(0);

            i += 1;

            let mut diff =
                PatchDifference::new(DifferenceType::Delete, src_start, dst_line);
            while i < lines.len() && lines[i].starts_with("< ") {
                diff.source_lines.push(format!("{}\n", &lines[i][2..]));
                i += 1;
            }

            let mut hunk = Hunk::new(src_start, dst_line);
            hunk.source_count = src_end - src_start + 1;
            hunk.dest_count = 0;
            hunk.differences.push(diff);

            if let Some(ref mut fp) = current_fp {
                fp.hunks.push(hunk);
            } else {
                let mut fp = FilePatch::new();
                fp.hunks.push(hunk);
                current_fp = Some(fp);
            }
            continue;
        }

        if let Some(cap) = HUNK_CHANGED.captures(lines[i]) {
            let src_start: usize = cap[1].parse().unwrap_or(0);
            let src_end: usize = cap
                .get(2)
                .map_or(src_start, |m| m.as_str().parse().unwrap_or(src_start));
            let dst_start: usize = cap[3].parse().unwrap_or(0);
            let dst_end: usize = cap
                .get(4)
                .map_or(dst_start, |m| m.as_str().parse().unwrap_or(dst_start));

            i += 1;

            let mut diff =
                PatchDifference::new(DifferenceType::Change, src_start, dst_start);

            // Collect source lines (< ...)
            while i < lines.len() && lines[i].starts_with("< ") {
                diff.source_lines.push(format!("{}\n", &lines[i][2..]));
                i += 1;
            }
            // Skip divider (---)
            if i < lines.len() && lines[i] == "---" {
                i += 1;
            }
            // Collect dest lines (> ...)
            while i < lines.len() && lines[i].starts_with("> ") {
                diff.dest_lines.push(format!("{}\n", &lines[i][2..]));
                i += 1;
            }

            let mut hunk = Hunk::new(src_start, dst_start);
            hunk.source_count = src_end - src_start + 1;
            hunk.dest_count = dst_end - dst_start + 1;
            hunk.differences.push(diff);

            if let Some(ref mut fp) = current_fp {
                fp.hunks.push(hunk);
            } else {
                let mut fp = FilePatch::new();
                fp.hunks.push(hunk);
                current_fp = Some(fp);
            }
            continue;
        }

        i += 1;
    }

    if let Some(fp) = current_fp {
        file_patches.push(fp);
    }

    Ok(file_patches)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_normal_change() {
        let input = "\
1,2c1,2
< old1
< old2
---
> new1
> new2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_normal(&lines).unwrap();
        assert_eq!(result.len(), 1);
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Change);
        assert_eq!(hunk.differences[0].source_lines.len(), 2);
        assert_eq!(hunk.differences[0].dest_lines.len(), 2);
    }

    #[test]
    fn test_parse_normal_add() {
        let input = "\
2a3,4
> added1
> added2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_normal(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Insert);
        assert_eq!(hunk.differences[0].dest_lines.len(), 2);
    }

    #[test]
    fn test_parse_normal_delete() {
        let input = "\
3,5d2
< removed1
< removed2
< removed3";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_normal(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Delete);
        assert_eq!(hunk.differences[0].source_lines.len(), 3);
    }

    #[test]
    fn test_parse_normal_with_header() {
        let input = "\
diff source.txt destination.txt
1c1
< old
---
> new";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_normal(&lines).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].source, "source.txt");
        assert_eq!(result[0].destination, "destination.txt");
    }
}
