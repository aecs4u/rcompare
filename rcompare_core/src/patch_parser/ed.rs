use rcompare_common::{
    DifferenceType, FilePatch, Hunk, PatchDifference, RCompareError,
};
use regex::Regex;
use std::sync::LazyLock;

// Ed command: N[,M]a or N[,M]c or N[,M]d
static ED_COMMAND: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(\d+)(?:,(\d+))?([acd])$").unwrap()
});

/// Parse ed diff format into a list of FilePatches.
///
/// Ed format uses commands like:
/// - `Na` — append after line N
/// - `N,Md` — delete lines N through M
/// - `N,Mc` — change lines N through M
///
/// Content lines follow the command, terminated by a lone `.`
pub fn parse_ed(lines: &[&str]) -> Result<Vec<FilePatch>, RCompareError> {
    let mut fp = FilePatch::new();
    let mut i = 0;

    while i < lines.len() {
        if let Some(cap) = ED_COMMAND.captures(lines[i]) {
            let start: usize = cap[1].parse().unwrap_or(0);
            let end: usize = cap
                .get(2)
                .map_or(start, |m| m.as_str().parse().unwrap_or(start));
            let cmd = &cap[3];

            i += 1;

            // Collect content lines until "."
            let mut content_lines = Vec::new();
            while i < lines.len() && lines[i] != "." {
                content_lines.push(format!("{}\n", lines[i]));
                i += 1;
            }
            // Skip the terminating "."
            if i < lines.len() && lines[i] == "." {
                i += 1;
            }

            let line_count = end - start + 1;

            match cmd {
                "a" => {
                    // Append after line `start`
                    let mut diff =
                        PatchDifference::new(DifferenceType::Insert, start, start + 1);
                    diff.dest_lines = content_lines;
                    let mut hunk = Hunk::new(start, start + 1);
                    hunk.source_count = 0;
                    hunk.dest_count = diff.dest_lines.len();
                    hunk.differences.push(diff);
                    fp.hunks.push(hunk);
                }
                "d" => {
                    // Delete lines start through end
                    let mut diff =
                        PatchDifference::new(DifferenceType::Delete, start, start);
                    // Ed delete doesn't include content; we create empty source placeholders
                    for _ in 0..line_count {
                        diff.source_lines.push(String::new());
                    }
                    let mut hunk = Hunk::new(start, start);
                    hunk.source_count = line_count;
                    hunk.dest_count = 0;
                    hunk.differences.push(diff);
                    fp.hunks.push(hunk);
                }
                "c" => {
                    // Change lines start through end
                    let mut diff =
                        PatchDifference::new(DifferenceType::Change, start, start);
                    for _ in 0..line_count {
                        diff.source_lines.push(String::new());
                    }
                    diff.dest_lines = content_lines;
                    let mut hunk = Hunk::new(start, start);
                    hunk.source_count = line_count;
                    hunk.dest_count = diff.dest_lines.len();
                    hunk.differences.push(diff);
                    fp.hunks.push(hunk);
                }
                _ => {}
            }
        } else {
            i += 1;
        }
    }

    if fp.hunks.is_empty() {
        Ok(Vec::new())
    } else {
        Ok(vec![fp])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_ed_append() {
        let input = "\
2a
added line 1
added line 2
.";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_ed(&lines).unwrap();
        assert_eq!(result.len(), 1);
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Insert);
        assert_eq!(hunk.differences[0].dest_lines.len(), 2);
    }

    #[test]
    fn test_parse_ed_delete() {
        let input = "\
3,5d";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_ed(&lines).unwrap();
        assert_eq!(result.len(), 1);
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Delete);
        assert_eq!(hunk.source_count, 3);
    }

    #[test]
    fn test_parse_ed_change() {
        let input = "\
1,2c
new line 1
new line 2
new line 3
.";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_ed(&lines).unwrap();
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Change);
        assert_eq!(hunk.differences[0].source_lines.len(), 2); // old lines 1-2
        assert_eq!(hunk.differences[0].dest_lines.len(), 3); // new replacement
    }

    #[test]
    fn test_parse_ed_multiple_commands() {
        let input = "\
1c
replacement
.
5a
appended
.";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_ed(&lines).unwrap();
        assert_eq!(result[0].hunks.len(), 2);
    }
}
