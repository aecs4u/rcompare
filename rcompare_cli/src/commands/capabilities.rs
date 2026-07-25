//! `capabilities` command: describe supported commands, flags, and schemas.
use serde::Serialize;

#[derive(Serialize)]
pub(crate) struct CommandCapability {
    pub(crate) name: String,
    pub(crate) description: String,
    pub(crate) supports_json: bool,
    pub(crate) supports_progress: bool,
    pub(crate) flags: Vec<String>,
}


#[derive(Serialize)]
pub(crate) struct ExitCodeCapability {
    pub(crate) code: i32,
    pub(crate) meaning: String,
}


#[derive(Serialize)]
pub(crate) struct CapabilitiesReport {
    pub(crate) schema_version: String,
    pub(crate) cli_version: String,
    pub(crate) scan_json_schema_versions: Vec<String>,
    pub(crate) commands: Vec<CommandCapability>,
    pub(crate) exit_codes: Vec<ExitCodeCapability>,
    pub(crate) notes: Vec<String>,
}


pub(crate) fn build_capabilities_report() -> CapabilitiesReport {
    CapabilitiesReport {
        schema_version: "1.0.0".to_string(),
        cli_version: env!("CARGO_PKG_VERSION").to_string(),
        scan_json_schema_versions: vec!["1.1.0".to_string()],
        commands: vec![
            CommandCapability {
                name: "scan".to_string(),
                description: "Scan and compare two directories or supported archives".to_string(),
                supports_json: true,
                supports_progress: true,
                flags: vec![
                    "--json".to_string(),
                    "--diff-only".to_string(),
                    "--ignore".to_string(),
                    "--follow-symlinks".to_string(),
                    "--verify-hashes/--no-verify-hashes".to_string(),
                    "--columns".to_string(),
                    "--text-diff".to_string(),
                    "--image-diff".to_string(),
                    "--csv-diff".to_string(),
                    "--excel-diff".to_string(),
                    "--json-diff".to_string(),
                    "--yaml-diff".to_string(),
                    "--parquet-diff".to_string(),
                ],
            },
            CommandCapability {
                name: "sync".to_string(),
                description: "Synchronize two directories using comparison results".to_string(),
                supports_json: true,
                supports_progress: false,
                flags: vec![
                    "--direction".to_string(),
                    "--dry-run".to_string(),
                    "--delete-mode".to_string(),
                    "--conflict".to_string(),
                    "--ignore".to_string(),
                    "--follow-symlinks".to_string(),
                    "--verify-hashes/--no-verify-hashes".to_string(),
                    "--json".to_string(),
                ],
            },
            CommandCapability {
                name: "copy".to_string(),
                description: "Copy selected relative paths between left and right directories"
                    .to_string(),
                supports_json: true,
                supports_progress: false,
                flags: vec![
                    "--direction".to_string(),
                    "--path".to_string(),
                    "--paths-file".to_string(),
                    "--dry-run".to_string(),
                    "--json".to_string(),
                ],
            },
            CommandCapability {
                name: "diff-file".to_string(),
                description: "Compute one file-level diff by mode (text/binary/image/etc)"
                    .to_string(),
                supports_json: true,
                supports_progress: false,
                flags: vec![
                    "--path".to_string(),
                    "--mode".to_string(),
                    "--json".to_string(),
                    "--ignore-whitespace".to_string(),
                    "--ignore-case".to_string(),
                    "--regex-rule".to_string(),
                    "--image-exif".to_string(),
                    "--image-tolerance".to_string(),
                    "--max-binary-ranges".to_string(),
                ],
            },
            CommandCapability {
                name: "read".to_string(),
                description: "Read one file from a side and export to stdout or --out"
                    .to_string(),
                supports_json: false,
                supports_progress: false,
                flags: vec![
                    "--side".to_string(),
                    "--path".to_string(),
                    "--out".to_string(),
                ],
            },
            CommandCapability {
                name: "capabilities".to_string(),
                description: "Print supported commands, flags, schemas, and exit codes".to_string(),
                supports_json: true,
                supports_progress: false,
                flags: vec!["--json".to_string()],
            },
        ],
        exit_codes: vec![
            ExitCodeCapability {
                code: 0,
                meaning: "Success: no differences found, or non-scan command completed".to_string(),
            },
            ExitCodeCapability {
                code: 1,
                meaning: "Failure: invalid input, runtime error, or parse error".to_string(),
            },
            ExitCodeCapability {
                code: 2,
                meaning: "Success with differences found (scan command)".to_string(),
            },
        ],
        notes: vec![
            "Progress indicators are emitted only when output is not JSON and stderr is a terminal."
                .to_string(),
            "Scan JSON schema versions are listed in scan_json_schema_versions.".to_string(),
        ],
    }
}


pub(crate) fn run_capabilities(json: bool) -> Result<(), Box<dyn std::error::Error>> {
    let report = build_capabilities_report();

    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Ok(());
    }

    println!("rcompare_cli capabilities");
    println!("  CLI version: {}", report.cli_version);
    println!("  Capabilities schema: {}", report.schema_version);
    println!(
        "  Scan JSON schemas: {}",
        report.scan_json_schema_versions.join(", ")
    );
    println!("\nCommands:");
    for cmd in &report.commands {
        println!(
            "  - {}: {}",
            cmd.name,
            cmd.description
        );
        println!(
            "    supports_json={}, supports_progress={}",
            cmd.supports_json, cmd.supports_progress
        );
        println!("    flags: {}", cmd.flags.join(", "));
    }
    println!("\nExit codes:");
    for item in &report.exit_codes {
        println!("  {} => {}", item.code, item.meaning);
    }

    Ok(())
}
