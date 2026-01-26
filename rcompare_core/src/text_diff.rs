use rcompare_common::RCompareError;
use regex::Regex;
use similar::{ChangeTag, TextDiff};
use std::fs;
use std::path::Path;
use syntect::easy::HighlightLines;
use syntect::highlighting::ThemeSet;
use syntect::parsing::SyntaxSet;
use syntect::util::LinesWithEndings;

/// Represents a line in a text diff
#[derive(Debug, Clone)]
pub struct DiffLine {
    pub line_number_left: Option<usize>,
    pub line_number_right: Option<usize>,
    pub content: String,
    pub change_type: DiffChangeType,
    pub highlighted_segments: Vec<HighlightedSegment>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiffChangeType {
    Equal,
    Insert,
    Delete,
}

#[derive(Debug, Clone)]
pub struct HighlightedSegment {
    pub text: String,
    pub style: HighlightStyle,
}

#[derive(Debug, Clone)]
pub struct HighlightStyle {
    pub foreground: (u8, u8, u8),
    pub background: Option<(u8, u8, u8)>,
    pub bold: bool,
    pub italic: bool,
}

/// Whitespace handling options for text comparison
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum WhitespaceMode {
    /// Compare whitespace exactly
    #[default]
    Exact,
    /// Ignore all whitespace changes
    IgnoreAll,
    /// Ignore leading whitespace
    IgnoreLeading,
    /// Ignore trailing whitespace
    IgnoreTrailing,
    /// Ignore changes in amount of whitespace
    IgnoreChanges,
}

/// Regular expression rule for filtering or transforming lines before comparison
#[derive(Debug, Clone)]
pub struct RegexRule {
    pub pattern: Regex,
    pub replacement: String,
    pub description: String,
}

/// Configuration for text comparison
#[derive(Debug, Clone, Default)]
pub struct TextDiffConfig {
    /// Ignore case when comparing
    pub ignore_case: bool,
    /// Whitespace handling mode
    pub whitespace_mode: WhitespaceMode,
    /// Regular expression rules to apply before comparison
    pub regex_rules: Vec<RegexRule>,
    /// Normalize line endings (CRLF vs LF)
    pub normalize_line_endings: bool,
    /// Tab width for expanding tabs to spaces
    pub tab_width: usize,
}

impl TextDiffConfig {
    pub fn new() -> Self {
        Self {
            ignore_case: false,
            whitespace_mode: WhitespaceMode::Exact,
            regex_rules: Vec::new(),
            normalize_line_endings: true,
            tab_width: 4,
        }
    }

    pub fn ignore_all_whitespace() -> Self {
        Self {
            whitespace_mode: WhitespaceMode::IgnoreAll,
            ..Default::default()
        }
    }

    pub fn ignore_case() -> Self {
        Self {
            ignore_case: true,
            ..Default::default()
        }
    }
}

/// Text diff engine with syntax highlighting support
pub struct TextDiffEngine {
    syntax_set: SyntaxSet,
    theme_set: ThemeSet,
    config: TextDiffConfig,
}

impl TextDiffEngine {
    pub fn new() -> Self {
        Self {
            syntax_set: SyntaxSet::load_defaults_newlines(),
            theme_set: ThemeSet::load_defaults(),
            config: TextDiffConfig::new(),
        }
    }

    pub fn with_config(config: TextDiffConfig) -> Self {
        Self {
            syntax_set: SyntaxSet::load_defaults_newlines(),
            theme_set: ThemeSet::load_defaults(),
            config,
        }
    }

    pub fn set_config(&mut self, config: TextDiffConfig) {
        self.config = config;
    }

    pub fn config(&self) -> &TextDiffConfig {
        &self.config
    }

    /// Preprocess text according to configuration options
    fn preprocess_text(&self, text: &str) -> String {
        let mut result = text.to_string();

        // Normalize line endings if requested
        if self.config.normalize_line_endings {
            result = result.replace("\r\n", "\n").replace('\r', "\n");
        }

        // Apply case folding if requested
        if self.config.ignore_case {
            result = result.to_lowercase();
        }

        // Apply regex rules
        for rule in &self.config.regex_rules {
            result = rule
                .pattern
                .replace_all(&result, &rule.replacement)
                .to_string();
        }

        // Apply whitespace handling
        match self.config.whitespace_mode {
            WhitespaceMode::Exact => result,
            WhitespaceMode::IgnoreAll => result
                .lines()
                .map(|line| {
                    line.chars()
                        .filter(|c| !c.is_whitespace())
                        .collect::<String>()
                })
                .collect::<Vec<_>>()
                .join("\n"),
            WhitespaceMode::IgnoreLeading => result
                .lines()
                .map(|line| line.trim_start())
                .collect::<Vec<_>>()
                .join("\n"),
            WhitespaceMode::IgnoreTrailing => result
                .lines()
                .map(|line| line.trim_end())
                .collect::<Vec<_>>()
                .join("\n"),
            WhitespaceMode::IgnoreChanges => result
                .lines()
                .map(|line| line.split_whitespace().collect::<Vec<_>>().join(" "))
                .collect::<Vec<_>>()
                .join("\n"),
        }
    }

    /// Compare two text files and generate a diff
    pub fn compare_files(
        &self,
        left_path: &Path,
        right_path: &Path,
    ) -> Result<Vec<DiffLine>, RCompareError> {
        let left_content = fs::read_to_string(left_path)?;
        let right_content = fs::read_to_string(right_path)?;

        self.compare_text(&left_content, &right_content, left_path)
    }

    /// Compare two text strings with Myers algorithm
    pub fn compare_text(
        &self,
        left: &str,
        right: &str,
        file_path: &Path,
    ) -> Result<Vec<DiffLine>, RCompareError> {
        // Preprocess text according to configuration
        let left_processed = self.preprocess_text(left);
        let right_processed = self.preprocess_text(right);

        let diff = TextDiff::from_lines(&left_processed, &right_processed);
        let mut result = Vec::new();

        let mut left_line_num = 1;
        let mut right_line_num = 1;

        // Detect syntax for highlighting
        let syntax = self
            .syntax_set
            .find_syntax_for_file(file_path)
            .ok()
            .flatten()
            .or_else(|| Some(self.syntax_set.find_syntax_plain_text()));

        for change in diff.iter_all_changes() {
            let change_type = match change.tag() {
                ChangeTag::Equal => DiffChangeType::Equal,
                ChangeTag::Insert => DiffChangeType::Insert,
                ChangeTag::Delete => DiffChangeType::Delete,
            };

            let (line_left, line_right) = match change_type {
                DiffChangeType::Equal => {
                    let l = Some(left_line_num);
                    let r = Some(right_line_num);
                    left_line_num += 1;
                    right_line_num += 1;
                    (l, r)
                }
                DiffChangeType::Insert => {
                    let r = Some(right_line_num);
                    right_line_num += 1;
                    (None, r)
                }
                DiffChangeType::Delete => {
                    let l = Some(left_line_num);
                    left_line_num += 1;
                    (l, None)
                }
            };

            let content = change.to_string();
            let highlighted = self.highlight_line(&content, syntax);

            result.push(DiffLine {
                line_number_left: line_left,
                line_number_right: line_right,
                content,
                change_type,
                highlighted_segments: highlighted,
            });
        }

        Ok(result)
    }

    /// Compare with Patience algorithm (better for code)
    pub fn compare_text_patience(
        &self,
        left: &str,
        right: &str,
        file_path: &Path,
    ) -> Result<Vec<DiffLine>, RCompareError> {
        // Use patience algorithm from similar crate
        let diff = TextDiff::configure()
            .algorithm(similar::Algorithm::Patience)
            .diff_lines(left, right);

        let mut result = Vec::new();
        let mut left_line_num = 1;
        let mut right_line_num = 1;

        let syntax = self
            .syntax_set
            .find_syntax_for_file(file_path)
            .ok()
            .flatten()
            .or_else(|| Some(self.syntax_set.find_syntax_plain_text()));

        for change in diff.iter_all_changes() {
            let change_type = match change.tag() {
                ChangeTag::Equal => DiffChangeType::Equal,
                ChangeTag::Insert => DiffChangeType::Insert,
                ChangeTag::Delete => DiffChangeType::Delete,
            };

            let (line_left, line_right) = match change_type {
                DiffChangeType::Equal => {
                    let l = Some(left_line_num);
                    let r = Some(right_line_num);
                    left_line_num += 1;
                    right_line_num += 1;
                    (l, r)
                }
                DiffChangeType::Insert => {
                    let r = Some(right_line_num);
                    right_line_num += 1;
                    (None, r)
                }
                DiffChangeType::Delete => {
                    let l = Some(left_line_num);
                    left_line_num += 1;
                    (l, None)
                }
            };

            let content = change.to_string();
            let highlighted = self.highlight_line(&content, syntax);

            result.push(DiffLine {
                line_number_left: line_left,
                line_number_right: line_right,
                content,
                change_type,
                highlighted_segments: highlighted,
            });
        }

        Ok(result)
    }

    /// Perform intra-line character diff
    pub fn intra_line_diff(&self, left_line: &str, right_line: &str) -> Vec<(String, bool)> {
        let diff = TextDiff::from_chars(left_line, right_line);
        let mut result = Vec::new();

        for change in diff.iter_all_changes() {
            let is_changed = change.tag() != ChangeTag::Equal;
            result.push((change.to_string(), is_changed));
        }

        result
    }

    fn highlight_line(
        &self,
        line: &str,
        syntax: Option<&syntect::parsing::SyntaxReference>,
    ) -> Vec<HighlightedSegment> {
        let syntax = match syntax {
            Some(s) => s,
            None => {
                return vec![HighlightedSegment {
                    text: line.to_string(),
                    style: HighlightStyle {
                        foreground: (200, 200, 200),
                        background: None,
                        bold: false,
                        italic: false,
                    },
                }]
            }
        };

        let theme = &self.theme_set.themes["base16-ocean.dark"];
        let mut highlighter = HighlightLines::new(syntax, theme);

        let mut segments = Vec::new();
        for line in LinesWithEndings::from(line) {
            if let Ok(ranges) = highlighter.highlight_line(line, &self.syntax_set) {
                for (style, text) in ranges {
                    segments.push(HighlightedSegment {
                        text: text.to_string(),
                        style: HighlightStyle {
                            foreground: (
                                style.foreground.r,
                                style.foreground.g,
                                style.foreground.b,
                            ),
                            background: None,
                            bold: style
                                .font_style
                                .contains(syntect::highlighting::FontStyle::BOLD),
                            italic: style
                                .font_style
                                .contains(syntect::highlighting::FontStyle::ITALIC),
                        },
                    });
                }
            }
        }

        if segments.is_empty() {
            segments.push(HighlightedSegment {
                text: line.to_string(),
                style: HighlightStyle {
                    foreground: (200, 200, 200),
                    background: None,
                    bold: false,
                    italic: false,
                },
            });
        }

        segments
    }
}

impl Default for TextDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_text_diff_basic() {
        let engine = TextDiffEngine::new();
        let left = "line1\nline2\nline3\n";
        let right = "line1\nline2_modified\nline3\n";

        let diff = engine
            .compare_text(left, right, Path::new("test.txt"))
            .unwrap();
        assert!(!diff.is_empty());
    }

    #[test]
    fn test_intra_line_diff() {
        let engine = TextDiffEngine::new();
        let left = "Hello World";
        let right = "Hello Rust";

        let diff = engine.intra_line_diff(left, right);
        assert!(diff.iter().any(|(_, changed)| *changed));
    }

    #[test]
    fn test_patience_algorithm() {
        let engine = TextDiffEngine::new();
        let left = "fn main() {\n    println!(\"Hello\");\n}\n";
        let right = "fn main() {\n    println!(\"World\");\n}\n";

        let diff = engine
            .compare_text_patience(left, right, Path::new("test.rs"))
            .unwrap();
        assert!(!diff.is_empty());
    }
}
