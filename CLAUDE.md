# RCompare - Claude Code Instructions

This file contains project-specific instructions for Claude Code when working on the RCompare project.

## Project Context

RCompare is a high-performance file and directory comparison utility written in Rust, inspired by Beyond Compare and following the architectural patterns of Czkawka.

## Development Guidelines

- Follow the architecture defined in [ARCHITECTURE.md](ARCHITECTURE.md)
- Maintain strict separation between `rcompare_core` (business logic) and UI layers
- Write safe Rust code; minimize use of `unsafe` blocks
- Ensure all changes maintain cross-platform compatibility (Linux, Windows, macOS)
