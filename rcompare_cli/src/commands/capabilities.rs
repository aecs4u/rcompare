//! `capabilities` command: describe supported commands, flags, and schemas.
use super::support::json_v2_envelope;
#[cfg(feature = "cloud")]
use super::support::REMOTE_SOURCE_SCHEMES;
use clap::CommandFactory;
use serde::Serialize;
use serde_json::json;

#[derive(Serialize)]
pub(crate) struct CommandCapability {
    pub(crate) name: String,
    pub(crate) description: String,
    pub(crate) supports_json: bool,
    pub(crate) supports_progress: bool,
    /// Machine-readable and terminal progress encodings available to a GUI.
    pub(crate) progress_formats: Vec<String>,
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
    /// URL schemes accepted as remote scan/read/diff-file sources in this build.
    pub(crate) source_schemes: Vec<String>,
    pub(crate) commands: Vec<CommandCapability>,
    pub(crate) exit_codes: Vec<ExitCodeCapability>,
    pub(crate) notes: Vec<String>,
}

fn source_schemes() -> Vec<String> {
    #[cfg(feature = "cloud")]
    {
        REMOTE_SOURCE_SCHEMES
            .iter()
            .map(|scheme| (*scheme).to_string())
            .collect()
    }

    #[cfg(not(feature = "cloud"))]
    {
        Vec::new()
    }
}

fn flags_for_command(name: &str) -> Vec<String> {
    let mut root = crate::Cli::command();
    let command = root
        .find_subcommand_mut(name)
        .unwrap_or_else(|| panic!("capabilities references unknown command: {name}"));
    let mut flags: Vec<String> = command
        .get_arguments()
        .filter_map(|argument| argument.get_long().map(|long| format!("--{long}")))
        .collect();
    // Clap keeps root-level global arguments on the root command rather than
    // exposing them through each subcommand's local argument iterator.
    if !flags.iter().any(|flag| flag == "--schema-version") {
        flags.push("--schema-version".to_string());
    }
    flags.sort();
    flags
}

fn supports(flags: &[String], flag: &str) -> bool {
    flags.iter().any(|candidate| candidate == flag)
}

pub(crate) fn build_capabilities_report() -> CapabilitiesReport {
    // Derive options from Clap's parser so `capabilities --json` cannot drift
    // away from the flags accepted by the executable.
    let scan_flags = flags_for_command("scan");
    let sync_flags = flags_for_command("sync");
    let sync_checkpoints_flags = flags_for_command("sync-checkpoints");
    let sync_discard_flags = flags_for_command("sync-discard");
    let copy_flags = flags_for_command("copy");
    let diff_file_flags = flags_for_command("diff-file");
    let read_flags = flags_for_command("read");
    let capabilities_flags = flags_for_command("capabilities");
    let scan_progress_formats = if supports(&scan_flags, "--progress") {
        vec![
            "terminal-spinner".to_string(),
            "json-stderr-lines".to_string(),
        ]
    } else {
        Vec::new()
    };
    CapabilitiesReport {
        schema_version: "1.2.0".to_string(),
        cli_version: env!("CARGO_PKG_VERSION").to_string(),
        scan_json_schema_versions: vec!["1.1.0".to_string()],
        source_schemes: source_schemes(),
        commands: vec![
            CommandCapability {
                name: "scan".to_string(),
                description: "Scan and compare two directories or supported archives".to_string(),
                supports_json: supports(&scan_flags, "--json"),
                supports_progress: !scan_progress_formats.is_empty(),
                progress_formats: scan_progress_formats,
                flags: scan_flags,
            },
            CommandCapability {
                name: "sync".to_string(),
                description: "Synchronize two directories using comparison results".to_string(),
                supports_json: supports(&sync_flags, "--json"),
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: sync_flags,
            },
            CommandCapability {
                name: "sync-checkpoints".to_string(),
                description: "List saved sync checkpoints".to_string(),
                supports_json: true,
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: sync_checkpoints_flags,
            },
            CommandCapability {
                name: "sync-discard".to_string(),
                description: "Discard a saved sync checkpoint".to_string(),
                supports_json: true,
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: sync_discard_flags,
            },
            CommandCapability {
                name: "copy".to_string(),
                description: "Copy selected relative paths between left and right directories"
                    .to_string(),
                supports_json: supports(&copy_flags, "--json"),
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: copy_flags,
            },
            CommandCapability {
                name: "diff-file".to_string(),
                description: "Compute one file-level diff by mode (text/binary/image/etc)"
                    .to_string(),
                supports_json: supports(&diff_file_flags, "--json"),
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: diff_file_flags,
            },
            CommandCapability {
                name: "read".to_string(),
                description: "Read one file from a side and export to stdout or --out".to_string(),
                supports_json: supports(&read_flags, "--json"),
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: read_flags,
            },
            CommandCapability {
                name: "capabilities".to_string(),
                description: "Print supported commands, flags, schemas, and exit codes".to_string(),
                supports_json: supports(&capabilities_flags, "--json"),
                supports_progress: false,
                progress_formats: Vec::new(),
                flags: capabilities_flags,
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
            ExitCodeCapability {
                code: 130,
                meaning: "Cancelled by the user".to_string(),
            },
        ],
        notes: vec![
            "With --progress auto, scan JSON output emits PROGRESS:<JSON> lines on stderr; human output uses a terminal spinner when stderr is a terminal."
                .to_string(),
            "Use --progress json to force structured stderr events or --progress never to suppress progress."
                .to_string(),
            "Machine-readable commands default to JSON schema v2; --schema-version 1 selects the legacy command-specific reports."
                .to_string(),
            "Scan JSON schema versions are listed in scan_json_schema_versions.".to_string(),
            "source_schemes lists remote schemes available for scan, read, and diff-file in this build."
                .to_string(),
        ],
    }
}

pub(crate) fn run_capabilities(
    json_output: bool,
    schema_version: u8,
) -> Result<(), Box<dyn std::error::Error>> {
    let report = build_capabilities_report();

    if json_output {
        let report_json = serde_json::to_value(&report)?;
        let output = if schema_version == 1 {
            report_json
        } else {
            let mut data = report_json;
            if let Some(fields) = data.as_object_mut() {
                fields.insert("supported_json_schema_versions".to_string(), json!([1, 2]));
                fields.insert("default_json_schema_version".to_string(), json!(2));
            }
            json_v2_envelope(
                "capabilities",
                "completed",
                json!({ "command_count": report.commands.len() }),
                data,
                Vec::new(),
            )
        };
        println!("{}", serde_json::to_string_pretty(&output)?);
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
        println!("  - {}: {}", cmd.name, cmd.description);
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
