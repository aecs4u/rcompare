# Module: rcompare_cli

Last verified against source: 2026-07-25 (`rcompare_cli/src/commands/*` read
directly).

Command-line interface wrapping `rcompare_core` ([docs/modules/rcompare_core.md](rcompare_core.md)).
`main.rs` + `src/commands/{scan,sync,copy,diff_file,read,capabilities,support}.rs`
(~3,900 lines in `commands/`). Also the backend `teczka` shells out to for every
comparison — see [docs/modules/teczka.md](teczka.md).

## Commands

| Command | Size | Maturity |
|---|---|---|
| `scan` | 2256 lines | Most mature. Text/image/CSV/Excel/JSON/Parquet specialized diffs, column selection, glob + `.gitignore` filters, JSON output, human progress bar (`show_progress` gated on `!json && stderr.is_terminal()`), gitignore-aware, hash cache, read-only ZIP/TAR/7Z archive support. |
| `sync` | 363 lines | Dry-run planning, delete-mode (`trash`/`permanent`), conflict policy (`newest`/`left`/`right`/`skip`/`error`), JSON report. Does **not** use the `ResumableCopy` engine (see [docs/modules/rcompare_core.md](rcompare_core.md)) — an interrupted sync can't resume. |
| `copy` | 189 lines | Path-list based copy (`--path`/`--paths-file`) between two roots. Same resumability gap as `sync`. |
| `diff-file` | 348 lines | Single-file diff by mode (text/binary/specialized), regex rules, image tolerance/EXIF. |
| `read` | 46 lines | Export one file (by side + path) to stdout or `--out`. Smallest command. |
| `capabilities` | 184 lines | Self-describing JSON/text capability dump — `schema_version` currently `"1.0.0"`; `scan`'s own JSON schema is versioned separately (`scan_json_schema_versions: ["1.1.0"]`). |

## JSON output

`scan` has its own schema (`v1.1.0`); `sync`/`copy`/`diff-file`/`capabilities`
report `schema_version: "1.0.0"`. There is **no unified v2 schema** across
commands yet.

## Confirmed missing / not wired

- **Structured progress streaming** — no `--progress-json` or `--ndjson` flag
  anywhere in `commands/`; progress is a terminal-only human bar
  (`scan.rs:178`, gated on `is_terminal()`).
- **JSON schema v2** — not started; each command's schema is independently
  versioned at `1.x`.
- **Resumable sync/copy** — the engine exists in `rcompare_core` but isn't
  called from `sync.rs`/`copy.rs`. See [docs/PLAN.md](../PLAN.md).
- **Report export formats** — only JSON + human text. No HTML/Markdown/JUnit
  XML anywhere in `rcompare_cli` or `rcompare_core`. (teczka's GUI-side export
  dialog does support CSV — see [docs/modules/teczka.md](teczka.md) — but
  there's no CLI equivalent.)
- **Cancellation** is scan-level only: `main.rs` wires a `ctrlc` handler to an
  `AtomicBool` consumed by `scan_vfs_with_cancel`, so Ctrl+C aborts a running
  scan cleanly — but there's no resumable transaction log for interrupted
  sync/copy operations.
- Archive write (ZIP/TAR/7Z) and cloud VFS (S3/SFTP/WebDAV) are not reachable
  from any CLI command — the core APIs exist but nothing in `rcompare_cli`
  constructs a writable-archive or cloud `Vfs` instance. See
  [docs/modules/rcompare_core.md](rcompare_core.md).
