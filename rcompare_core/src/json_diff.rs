use rcompare_common::RCompareError;
use serde::Serialize;
use serde_json::Value as JsonValue;
use serde_yml::Value as YamlValue;
use std::collections::HashMap;
use std::path::Path;

/// Result of a JSON/YAML comparison
#[derive(Debug, Clone, Serialize)]
pub struct JsonDiffResult {
    /// Total number of keys/paths compared
    pub total_paths: usize,
    /// Number of paths that differ
    pub different_paths: usize,
    /// Number of paths only in left
    pub left_only_paths: usize,
    /// Number of paths only in right
    pub right_only_paths: usize,
    /// Number of identical paths
    pub identical_paths: usize,
    /// Detailed path differences (limited to first 100)
    pub path_diffs: Vec<PathDiff>,
}

/// Represents a difference in a specific path
#[derive(Debug, Clone, Serialize)]
pub struct PathDiff {
    /// JSON path (e.g., "root.users[0].name")
    pub path: String,
    /// Type of difference
    pub diff_type: PathDiffType,
    /// Left value (as string)
    pub left_value: String,
    /// Right value (as string)
    pub right_value: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum PathDiffType {
    /// Value exists in both but differs
    ValueDifferent,
    /// Type differs (e.g., string vs number)
    TypeDifferent,
    /// Path only exists in left
    LeftOnly,
    /// Path only exists in right
    RightOnly,
}

/// Engine for comparing JSON/YAML files
pub struct JsonDiffEngine {
    max_path_diffs: usize,
}

impl JsonDiffEngine {
    pub fn new() -> Self {
        Self {
            max_path_diffs: 100,
        }
    }

    pub fn with_max_path_diffs(mut self, max: usize) -> Self {
        self.max_path_diffs = max;
        self
    }

    /// Compare two JSON files
    pub fn compare_json_files(
        &self,
        left: &Path,
        right: &Path,
    ) -> Result<JsonDiffResult, RCompareError> {
        let left_content = std::fs::read_to_string(left).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to read left JSON file: {}", e),
            ))
        })?;

        let right_content = std::fs::read_to_string(right).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to read right JSON file: {}", e),
            ))
        })?;

        let left_json: JsonValue = serde_json::from_str(&left_content).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse left JSON: {}", e),
            ))
        })?;

        let right_json: JsonValue = serde_json::from_str(&right_content).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse right JSON: {}", e),
            ))
        })?;

        self.compare_json_values(&left_json, &right_json)
    }

    /// Compare two YAML files
    pub fn compare_yaml_files(
        &self,
        left: &Path,
        right: &Path,
    ) -> Result<JsonDiffResult, RCompareError> {
        let left_content = std::fs::read_to_string(left).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to read left YAML file: {}", e),
            ))
        })?;

        let right_content = std::fs::read_to_string(right).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to read right YAML file: {}", e),
            ))
        })?;

        let left_yaml: YamlValue = serde_yml::from_str(&left_content).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse left YAML: {}", e),
            ))
        })?;

        let right_yaml: YamlValue = serde_yml::from_str(&right_content).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse right YAML: {}", e),
            ))
        })?;

        // Convert YAML values to JSON for unified comparison
        let left_json = yaml_to_json(left_yaml);
        let right_json = yaml_to_json(right_yaml);

        self.compare_json_values(&left_json, &right_json)
    }

    /// Compare two JSON values
    fn compare_json_values(
        &self,
        left: &JsonValue,
        right: &JsonValue,
    ) -> Result<JsonDiffResult, RCompareError> {
        let mut left_paths = HashMap::new();
        let mut right_paths = HashMap::new();

        // Flatten both JSON structures into path -> value maps
        flatten_json("root", left, &mut left_paths);
        flatten_json("root", right, &mut right_paths);

        // Collect all unique paths
        let mut all_paths: Vec<String> = left_paths
            .keys()
            .chain(right_paths.keys())
            .cloned()
            .collect();
        all_paths.sort();
        all_paths.dedup();

        let total_paths = all_paths.len();
        let mut different_paths = 0;
        let mut left_only_paths = 0;
        let mut right_only_paths = 0;
        let mut identical_paths = 0;
        let mut path_diffs = Vec::new();

        for path in &all_paths {
            let left_val = left_paths.get(path);
            let right_val = right_paths.get(path);

            match (left_val, right_val) {
                (Some(left), Some(right)) => {
                    if values_equal(left, right) {
                        identical_paths += 1;
                    } else {
                        different_paths += 1;
                        if path_diffs.len() < self.max_path_diffs {
                            let diff_type =
                                if std::mem::discriminant(left) != std::mem::discriminant(right) {
                                    PathDiffType::TypeDifferent
                                } else {
                                    PathDiffType::ValueDifferent
                                };

                            path_diffs.push(PathDiff {
                                path: path.clone(),
                                diff_type,
                                left_value: format_json_value(left),
                                right_value: format_json_value(right),
                            });
                        }
                    }
                }
                (Some(left), None) => {
                    left_only_paths += 1;
                    if path_diffs.len() < self.max_path_diffs {
                        path_diffs.push(PathDiff {
                            path: path.clone(),
                            diff_type: PathDiffType::LeftOnly,
                            left_value: format_json_value(left),
                            right_value: String::from("(missing)"),
                        });
                    }
                }
                (None, Some(right)) => {
                    right_only_paths += 1;
                    if path_diffs.len() < self.max_path_diffs {
                        path_diffs.push(PathDiff {
                            path: path.clone(),
                            diff_type: PathDiffType::RightOnly,
                            left_value: String::from("(missing)"),
                            right_value: format_json_value(right),
                        });
                    }
                }
                (None, None) => unreachable!(),
            }
        }

        Ok(JsonDiffResult {
            total_paths,
            different_paths,
            left_only_paths,
            right_only_paths,
            identical_paths,
            path_diffs,
        })
    }
}

impl Default for JsonDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Flatten a JSON value into a map of paths to values
fn flatten_json(prefix: &str, value: &JsonValue, output: &mut HashMap<String, JsonValue>) {
    match value {
        JsonValue::Object(map) => {
            for (key, val) in map {
                let path = format!("{}.{}", prefix, key);
                flatten_json(&path, val, output);
            }
        }
        JsonValue::Array(arr) => {
            for (i, val) in arr.iter().enumerate() {
                let path = format!("{}[{}]", prefix, i);
                flatten_json(&path, val, output);
            }
        }
        _ => {
            output.insert(prefix.to_string(), value.clone());
        }
    }
}

/// Check if two JSON values are equal
fn values_equal(left: &JsonValue, right: &JsonValue) -> bool {
    match (left, right) {
        (JsonValue::Null, JsonValue::Null) => true,
        (JsonValue::Bool(a), JsonValue::Bool(b)) => a == b,
        (JsonValue::Number(a), JsonValue::Number(b)) => {
            // Compare numbers with some tolerance for floating point
            if let (Some(a_f), Some(b_f)) = (a.as_f64(), b.as_f64()) {
                (a_f - b_f).abs() < f64::EPSILON
            } else if let (Some(a_i), Some(b_i)) = (a.as_i64(), b.as_i64()) {
                a_i == b_i
            } else if let (Some(a_u), Some(b_u)) = (a.as_u64(), b.as_u64()) {
                a_u == b_u
            } else {
                false
            }
        }
        (JsonValue::String(a), JsonValue::String(b)) => a == b,
        _ => false,
    }
}

/// Format a JSON value as a string for display
fn format_json_value(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => String::from("null"),
        JsonValue::Bool(b) => b.to_string(),
        JsonValue::Number(n) => n.to_string(),
        JsonValue::String(s) => format!("\"{}\"", s),
        JsonValue::Array(_) => String::from("[array]"),
        JsonValue::Object(_) => String::from("{object}"),
    }
}

/// Convert YAML value to JSON value
fn yaml_to_json(yaml: YamlValue) -> JsonValue {
    match yaml {
        YamlValue::Null => JsonValue::Null,
        YamlValue::Bool(b) => JsonValue::Bool(b),
        YamlValue::Number(n) => {
            if let Some(i) = n.as_i64() {
                JsonValue::Number(serde_json::Number::from(i))
            } else if let Some(u) = n.as_u64() {
                JsonValue::Number(serde_json::Number::from(u))
            } else if let Some(f) = n.as_f64() {
                JsonValue::Number(
                    serde_json::Number::from_f64(f).unwrap_or(serde_json::Number::from(0)),
                )
            } else {
                JsonValue::Null
            }
        }
        YamlValue::String(s) => JsonValue::String(s),
        YamlValue::Sequence(seq) => JsonValue::Array(seq.into_iter().map(yaml_to_json).collect()),
        YamlValue::Mapping(map) => {
            let mut obj = serde_json::Map::new();
            for (k, v) in map {
                if let YamlValue::String(key) = k {
                    obj.insert(key, yaml_to_json(v));
                } else {
                    // Convert non-string keys to strings
                    let key = format!("{:?}", k);
                    obj.insert(key, yaml_to_json(v));
                }
            }
            JsonValue::Object(obj)
        }
        YamlValue::Tagged(tagged) => yaml_to_json(tagged.value),
    }
}

/// Check if a file path appears to be JSON based on extension
pub fn is_json_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(ext.as_str(), "json" | "jsonc" | "json5")
    } else {
        false
    }
}

/// Check if a file path appears to be YAML based on extension
pub fn is_yaml_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(ext.as_str(), "yaml" | "yml")
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn create_temp_json(content: &str) -> NamedTempFile {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all(content.as_bytes()).unwrap();
        file.flush().unwrap();
        file
    }

    #[test]
    fn test_identical_json() {
        let content = r#"{"name": "test", "count": 42, "active": true}"#;
        let left = create_temp_json(content);
        let right = create_temp_json(content);

        let engine = JsonDiffEngine::new();
        let result = engine
            .compare_json_files(left.path(), right.path())
            .unwrap();

        assert_eq!(result.identical_paths, 3);
        assert_eq!(result.different_paths, 0);
        assert_eq!(result.left_only_paths, 0);
        assert_eq!(result.right_only_paths, 0);
    }

    #[test]
    fn test_different_values() {
        let left = create_temp_json(r#"{"name": "test", "count": 42}"#);
        let right = create_temp_json(r#"{"name": "test", "count": 100}"#);

        let engine = JsonDiffEngine::new();
        let result = engine
            .compare_json_files(left.path(), right.path())
            .unwrap();

        assert_eq!(result.identical_paths, 1); // name
        assert_eq!(result.different_paths, 1); // count
        assert_eq!(result.path_diffs.len(), 1);
    }

    #[test]
    fn test_missing_keys() {
        let left = create_temp_json(r#"{"name": "test", "count": 42, "extra": "left"}"#);
        let right = create_temp_json(r#"{"name": "test", "count": 42, "new": "right"}"#);

        let engine = JsonDiffEngine::new();
        let result = engine
            .compare_json_files(left.path(), right.path())
            .unwrap();

        assert_eq!(result.identical_paths, 2); // name, count
        assert_eq!(result.left_only_paths, 1); // extra
        assert_eq!(result.right_only_paths, 1); // new
    }

    #[test]
    fn test_nested_json() {
        let left = create_temp_json(r#"{"user": {"name": "alice", "age": 30}}"#);
        let right = create_temp_json(r#"{"user": {"name": "alice", "age": 31}}"#);

        let engine = JsonDiffEngine::new();
        let result = engine
            .compare_json_files(left.path(), right.path())
            .unwrap();

        assert_eq!(result.identical_paths, 1); // user.name
        assert_eq!(result.different_paths, 1); // user.age
    }

    #[test]
    fn test_is_json_file() {
        assert!(is_json_file(Path::new("data.json")));
        assert!(is_json_file(Path::new("data.JSON")));
        assert!(is_json_file(Path::new("config.jsonc")));
        assert!(!is_json_file(Path::new("data.txt")));
    }

    #[test]
    fn test_is_yaml_file() {
        assert!(is_yaml_file(Path::new("config.yaml")));
        assert!(is_yaml_file(Path::new("config.yml")));
        assert!(is_yaml_file(Path::new("data.YAML")));
        assert!(!is_yaml_file(Path::new("data.txt")));
    }
}
