use std::path::PathBuf;

#[test]
fn ui_compiles() {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let input = manifest_dir.join("ui").join("main.slint");
    let temp_dir = tempfile::TempDir::new().expect("temp dir");
    let output = temp_dir.path().join("slint_ui.rs");

    let config = slint_build::CompilerConfiguration::new();
    slint_build::compile_with_output_path(&input, &output, config)
        .expect("compile slint ui");

    let metadata = std::fs::metadata(&output).expect("output missing");
    assert!(metadata.len() > 0);
}
