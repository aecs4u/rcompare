# RCompare vs File Comparison Tools: Feature Comparison

## Overview

| Tool | License | Language | Platforms | Active Development |
|------|---------|----------|-----------|-------------------|
| **RCompare** | Open Source (MIT/Apache 2.0) | Rust | Linux, Windows, macOS | ✅ Yes |
| **Beyond Compare** | Commercial ($60-$130) | C++ | Linux, Windows, macOS | ✅ Yes |
| **WinMerge** | Open Source (GPL) | C++ | Windows | ✅ Yes |
| **Meld** | Open Source (GPL) | Python/GTK | Linux, Windows, macOS | ✅ Yes |
| **KDiff3** | Open Source (GPL) | C++/Qt | Linux, Windows, macOS | ✅ Yes |
| **P4Merge** | Freeware | Proprietary | Linux, Windows, macOS | ✅ Yes |
| **DiffMerge** | Freeware | Proprietary | Linux, Windows, macOS | ⚠️ Limited |
| **Araxis Merge** | Commercial ($129+) | Proprietary | Windows, macOS | ✅ Yes |
| **Kompare** | Open Source (GPL) | C++/KDE | Linux | ⚠️ Maintenance only |
| **ExamDiff Pro** | Commercial ($35) | Proprietary | Windows | ✅ Yes |
| **Guiffy** | Commercial ($37.50+) | Java | Linux, Windows, macOS | ✅ Yes |
| **DeltaWalker** | Commercial ($49.95+) | Java | Linux, Windows, macOS | ✅ Yes |
| **Code Compare** | Freemium | Proprietary | Windows | ✅ Yes |

### Key Differentiators

| Aspect | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 |
|--------|----------|----------------|----------|------|--------|
| **Privacy** | Zero telemetry | Unknown | Zero telemetry | Zero telemetry | Zero telemetry |
| **Memory Safety** | Guaranteed (Rust) | Manual (C++) | Manual (C++) | Python GC | Manual (C++) |
| **Architecture** | Modular (Core+CLI+GUI) | Monolithic | Monolithic | Monolithic | Monolithic |
| **JSON CLI Output** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **SFTP Support** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |

---

## Core Comparison Features

### Folder Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Side-by-side directory trees | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Recursive scanning | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Timestamp comparison | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Size comparison | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Hash verification | ✅ BLAKE3 | ✅ CRC/MD5/SHA | ✅ SHA-1 | ❌ No | ❌ No | ❌ No |
| Partial hash (fast pre-check) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Orphan file detection | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Glob pattern filtering | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| .gitignore support | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| Session profiles | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Expand/Collapse all | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |

**Notes:**
- RCompare uses BLAKE3 hashing which is faster than MD5/SHA1
- P4Merge focuses on file comparison only, not folder comparison
- WinMerge uses 7-Zip for archive integration

### Text Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Line-by-line diff | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Myers diff algorithm | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| Patience diff algorithm | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| Syntax highlighting | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| Intra-line character diff | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Configurable colors | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Line numbers | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Difference overview map | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| Editable comparison | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| 3-way merge | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Conflict resolution UI | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Ignore whitespace | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Ignore case | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Regular expression rules | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Grammar-aware comparison | ⏳ Planned | ✅ Yes (Pro) | ❌ No | ❌ No | ❌ No | ❌ No |

**Notes:**
- RCompare's Patience diff algorithm produces better diffs for code with moved blocks
- WinMerge uses Prediffer plugins for advanced text processing
- KDiff3 uses its own diff algorithm optimized for three-way merge

### Binary/Hex Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Hex viewer | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Offset/Hex/ASCII layout | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Lazy loading (large files) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Random access seeking | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Difference highlighting | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Editable hex mode | ⏳ Future | ✅ Yes | ⏳ Limited | ❌ No | ❌ No | ❌ No |
| Structure viewer | ❌ No | ✅ Yes (Pro) | ❌ No | ❌ No | ❌ No | ❌ No |

**Notes:**
- Most open-source tools focus on text comparison; binary support varies
- Beyond Compare Pro has advanced structure parsing for EXE, ZIP headers

### Image Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Side-by-side view | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| Fade overlay mode | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| Difference map | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| Swipe comparison | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Perceptual hashing | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| Pixel-level diff | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| EXIF metadata compare | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Tolerance adjustment | ✅ Yes | ✅ Yes | ⏳ Limited | ❌ No | ❌ No | ❌ No |

**Notes:**
- P4Merge is known for its strong image comparison capabilities
- RCompare uses perceptual hashing (pHash) for intelligent image similarity detection

---

## Synchronization & File Operations

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Copy files (Left ↔ Right) | ✅ Yes | ✅ Yes | |
| Move files | ✅ Yes | ✅ Yes | |
| Delete files | ✅ Yes (trash support) | ✅ Yes | RCompare uses `trash` crate for safety |
| Bi-directional sync | ✅ Yes | ✅ Yes | |
| Dry run preview | ✅ Yes | ✅ Yes | |
| Touch (timestamp sync) | ✅ Yes | ✅ Yes | RCompare explicit feature |
| Checksum verification after copy | ⏳ Future | ✅ Yes | |
| Multi-threaded copying | ✅ Yes | ✅ Yes | |
| Resume interrupted copies | ❌ No | ✅ Yes | |
| Filters for sync | ✅ Yes | ✅ Yes | |
| Sync rules (newer, older, size) | ✅ Yes | ✅ Yes | |
| Reflink support (Btrfs/XFS) | ⏳ Planned | ❌ No | RCompare will optimize for modern filesystems |

---

## Archive & Virtual Filesystems

> **See [ROADMAP_VFS.md](ROADMAP_VFS.md) for detailed implementation plans.**

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 |
|---------|----------|----------------|----------|------|--------|
| ZIP archive support | ✅ Read/Write | ✅ Yes | ✅ Via 7-Zip | ❌ No | ❌ No |
| TAR/GZ support | ✅ Read/Write | ✅ Yes | ✅ Via 7-Zip | ❌ No | ❌ No |
| 7Z support | ✅ Read/Write | ✅ Yes | ✅ Native | ❌ No | ❌ No |
| RAR support | ✅ Read-only | ✅ Yes | ✅ Via 7-Zip | ❌ No | ❌ No |
| ISO support | ⏳ Planned | ✅ Yes | ✅ Via 7-Zip | ❌ No | ❌ No |
| Compressed files (.gz, .bz2, .xz) | ✅ Read/Write | ✅ Yes | ✅ Via 7-Zip | ❌ No | ❌ No |
| FTP/SFTP | ✅ SFTP | ✅ Both | ❌ No | ❌ No | ❌ No |
| Cloud storage (S3, etc.) | ✅ Yes | ✅ Yes (Pro) | ❌ No | ❌ No | ❌ No |
| WebDAV | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Version control (Git, SVN) | ⏳ v2.x | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| Virtual folders (FilteredVfs) | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Union/Overlay VFS | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Snapshot VFS | ⏳ v1.3 | ❌ No | ❌ No | ❌ No | ❌ No |

---

## Specialized Comparison Types

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| **Table/CSV comparison** | ❌ No | ✅ Yes | BC advantage for data files |
| **MP3 tag comparison** | ❌ No | ✅ Yes | BC niche feature |
| **Registry comparison** (Windows) | ❌ No | ✅ Yes | BC Windows-specific |
| **Version comparison** (DLL, EXE) | ❌ No | ✅ Yes | BC Windows-specific |
| **PDF comparison** | ❌ No | ⏳ Plugin | BC has better doc support |

---

## Automation & Scripting

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Command-line interface | ✅ Yes (robust) | ✅ Yes | |
| Scriptable operations | ✅ Yes (via CLI) | ✅ Yes | |
| JSON output | ✅ Yes | ❌ No (XML/HTML) | RCompare advantage for modern tools |
| Exit codes for CI/CD | ✅ Yes | ✅ Yes | |
| Batch file support | ✅ Yes | ✅ Yes | |
| Headless mode | ✅ Yes (pure core lib) | ✅ Yes | |
| Scheduled tasks | ❌ No | ⏳ Via OS scheduler | Both rely on external scheduling |

---

## Advanced / Optional Features (Survey)

These are commonly found in other comparison tools and are candidates for future work.

| Feature | RCompare | Notes |
|---------|----------|-------|
| Moved lines detection | ⏳ Future | Detect and track moved blocks across diffs |
| Manual compare alignment | ⏳ Future | User-driven pairing of lines/blocks |
| Structured comparison | ⏳ Future | XML/CSV/JSON/logical-section aware compare |
| Patch creation / apply / preview | ⏳ Future | Unified patch workflow |
| Report export (HTML/XML/CSV/Text/Patch) | ⏳ Future | Currently JSON only |
| Horizontal/vertical layout toggle | ⏳ Future | Side-by-side and stacked views |
| Scripting / macros | ⏳ Future | Repeatable compare/sync sessions |
| FTP/SFTP sources | ✅ SFTP implemented | Full SFTP support via ssh2 crate |
| Version control browsing | ❌ Not planned | VCS-backed VFS if added later |
| Unicode normalization controls | ⏳ Future | Normalize case/width/combining marks |
| CRC/hash compare modes | ⏳ Future | CRC/extra hash options |
| Filedate/DST normalization | ⏳ Future | Timezone/DST compare options |

---

## User Interface

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Native GUI | ✅ Yes (Slint) | ✅ Yes (native) | |
| Dark mode | ✅ Yes | ✅ Yes | |
| Customizable colors | ✅ Yes | ✅ Yes | |
| Toolbar customization | ⏳ Future | ✅ Yes | BC has more UI flexibility |
| Multiple sessions (tabs) | ✅ Yes | ✅ Yes | |
| Keyboard shortcuts | ✅ Yes | ✅ Yes | |
| Context menus | ✅ Yes | ✅ Yes | |
| Drag & drop | ⏳ Future | ✅ Yes | |
| Touch screen support | ⏳ Depends on Slint | ✅ Yes | |
| UI responsiveness | ✅ Excellent (async) | ✅ Good | RCompare uses actor model |

---

## Performance & Scalability

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Memory safety | ✅ Guaranteed (Rust) | ⚠️ C++ (manual) | RCompare advantage |
| Multi-threaded scanning | ✅ Yes (rayon) | ✅ Yes | |
| Parallel hashing | ✅ Yes (BLAKE3 SIMD) | ✅ Yes | BLAKE3 is faster than MD5/SHA1 |
| Persistent cache | ✅ Yes (.bin) | ✅ Yes | |
| Cache invalidation | ✅ Automatic (mtime) | ✅ Automatic | |
| Virtual list rendering | ✅ Yes (flatten) | ✅ Yes | Both optimize for huge trees |
| Memory footprint | ✅ Low (Arc strings) | ✅ Medium | RCompare uses string interning |
| Startup time | ✅ Fast | ✅ Fast | |

---

## Security & Privacy

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Open source | ✅ Yes | ❌ No | Full auditability |
| Zero telemetry | ✅ Guaranteed | ⚠️ Unknown | RCompare privacy-first |
| Air-gap compatible | ✅ Yes | ✅ Yes | |
| No license server | ✅ Yes (free) | ❌ Requires activation | |
| Portable mode | ✅ Yes | ✅ Yes | |
| Offline operation | ✅ 100% | ✅ Yes | |
| CVE tracking | ✅ Public | ❌ Private | Open source advantage |

---

## Configuration & Extensibility

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Settings persistence | ✅ Yes (TOML) | ✅ Yes (Registry/XML) | RCompare uses portable TOML |
| Profile management | ✅ Yes | ✅ Yes | Save/load session profiles |
| Plugin system | ❌ Not planned | ⏳ Limited | Neither has robust plugin API |
| Custom file formats | ⏳ Via VFS trait | ✅ Yes (via plugins) | |
| XDG Base Directory | ✅ Yes (Linux) | ❌ No | RCompare follows standards |

---

## Documentation & Support

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| User manual | ✅ Yes (Markdown/Web) | ✅ Yes (CHM/Web) | |
| Video tutorials | ⏳ Community | ✅ Official | BC has professional docs |
| Community forum | ✅ GitHub Discussions | ✅ Official forum | |
| Commercial support | ❌ No | ✅ Yes (paid) | |
| Response time | ⏳ Community-driven | ✅ Guaranteed (Pro) | |

---

## Summary: Key Differences

### RCompare Unique Advantages ✅
1. **Modern Memory-Safe Language**: Written in Rust for guaranteed memory safety
2. **Privacy-First**: Zero telemetry, no license servers, fully offline
3. **Superior Performance**: BLAKE3 hashing, Patience diff algorithm
4. **Modern CLI**: First-class JSON output for CI/CD automation
5. **.gitignore Support**: Native integration (unique among all tools)
6. **Perceptual Image Hashing**: Intelligent image similarity detection
7. **Virtual VFS Features**: FilteredVfs and UnionVfs for advanced workflows
8. **Full Archive Write Support**: Read/write ZIP, TAR, 7Z with VFS trait

### Beyond Compare Advantages ✅
1. **Mature Product**: 20+ years of development
2. **Specialized Formats**: Table, MP3, Registry, PDF comparison
3. **Cloud Storage**: Native S3, Dropbox, Google Drive support
4. **Advanced Editing**: Structure viewer, regex rules, grammar-aware diff
5. **Commercial Support**: Professional documentation and help

### WinMerge Advantages ✅
1. **Free and Open Source**: GPL-licensed, Windows-focused
2. **7-Zip Integration**: Comprehensive archive support via plugins
3. **Plugin System**: Extensible through Prediffer plugins
4. **Established Community**: Long development history since 1998

### Meld Advantages ✅
1. **Version Control Integration**: Native Git, SVN, Mercurial support
2. **Python/GTK**: Easy to extend and modify
3. **Cross-Platform**: Works on Linux, Windows, macOS
4. **Clean UI**: Modern, intuitive interface

### KDiff3 Advantages ✅
1. **Three-Way Merge Focused**: Optimized for complex merge scenarios
2. **Character-Level Diff**: Detailed inline comparison
3. **Cross-Platform Qt**: Consistent experience everywhere
4. **Lightweight**: Low resource usage

### P4Merge Advantages ✅
1. **Free Commercial Tool**: Professional quality at no cost
2. **Image Comparison**: Strong pixel-level image diffing
3. **Perforce Integration**: Seamless with Helix Core
4. **Clean 4-Pane Merge**: BASE, LOCAL, REMOTE, RESULT view

### Tool Selection Guide

| Use Case | Recommended Tool |
|----------|-----------------|
| **Open source + privacy** | RCompare |
| **Enterprise + cloud storage** | Beyond Compare |
| **Windows-only development** | WinMerge |
| **Version control workflows** | Meld or P4Merge |
| **Complex three-way merges** | KDiff3 |
| **Image comparison** | P4Merge or RCompare |
| **CI/CD automation** | RCompare (JSON output) |
| **Archive manipulation** | RCompare or Beyond Compare |

### Feature Parity (All Major Tools)
All tools compared here offer comparable performance for:
- Basic text diff with line highlighting
- Two-way file comparison
- Basic folder comparison
- Copy/merge operations
- Cross-platform support (varies)

---

## Use Case Recommendations

### Choose RCompare If:
- You need an **open-source** solution
- You prioritize **privacy** (air-gapped environments, security audits)
- You work with **local or SFTP filesystems**
- You need **modern CLI automation** (JSON output, CI/CD integration)
- You want **zero licensing costs**
- You contribute to or prefer **Rust ecosystem** tools
- You need **session profiles** for recurring comparisons

### Choose Beyond Compare If:
- You need **cloud storage support** (S3, Dropbox, Google Drive)
- You work with **specialized formats** (CSV tables, MP3 tags, Windows Registry)
- You require **commercial support** and guaranteed updates
- You need **advanced editing features** (structure viewer, regex rules)
- You have an existing **paid license** or budget for software
- You need **maximum format compatibility** (RAR, ISO, exotic archives)

---

## Roadmap: Closing the Gap

### Recently Implemented ✅
- **Archive write support** (ZIP, TAR, TAR.GZ, 7Z)
- **RAR read support** (requires unrar library)
- **Compressed file support** (.gz, .bz2, .xz)
- **Virtual folders** (FilteredVfs with glob patterns)
- **Union VFS** (combine multiple sources)
- **VFS capabilities API** (read/write/delete/rename/mtime)
- **S3/cloud storage** support (AWS S3, MinIO, DigitalOcean Spaces, Wasabi)
- **WebDAV** support (Nextcloud, ownCloud, Apache mod_dav)

### Planned for v1.x
- **Whitespace/case ignore** options
- **EXIF metadata comparison**
- **Drag & drop** support
- **ISO archive support** (read-only)
- **Snapshot VFS** (point-in-time comparison)

### Planned for v2.0+
- **Git VFS** integration via git2
- **Reflink optimization** for Btrfs/XFS
- **Plugin API** for custom comparisons
- **Google Drive** support
- **Dropbox** support
- **Azure Blob Storage** support

### Out of Scope
- FTP support - use SFTP instead (more secure)
- Table/CSV comparison - use specialized data diff tools
- Media-specific formats (MP3, Registry) - niche use cases
- MTP device support - use file manager instead

---

## Conclusion

**RCompare v1.0** delivers comprehensive file comparison functionality competitive with established tools while offering unique advantages in privacy, performance, and modern architecture.

### How RCompare Compares

| Compared To | RCompare Advantage | Other Tool Advantage |
|-------------|-------------------|---------------------|
| **Beyond Compare** | Open source, privacy, Rust safety, JSON CLI | Cloud storage, specialized formats, maturity |
| **WinMerge** | Cross-platform, SFTP, archive write, privacy | Windows integration, plugin ecosystem |
| **Meld** | Performance, archive support, CLI automation | VCS integration, Python extensibility |
| **KDiff3** | Modern UI, archive support, image comparison | Focused three-way merge, lightweight |
| **P4Merge** | Open source, folder comparison, archives | Free commercial quality, image diffing |

### Target Audience

**Choose RCompare if you:**
- Need an **open-source** solution with full auditability
- Prioritize **privacy** (air-gapped environments, security audits)
- Work with **local, SFTP, or archive filesystems**
- Need **modern CLI automation** (JSON output, CI/CD integration)
- Want **zero licensing costs** with no vendor lock-in
- Value **memory safety** and modern development practices
- Need **session profiles** for recurring comparisons

**Choose another tool if you:**
- Need **cloud storage support** (S3, Dropbox) → Beyond Compare
- Work with **specialized formats** (CSV, MP3, Registry) → Beyond Compare
- Want **deep version control integration** → Meld
- Need **maximum Windows integration** → WinMerge
- Focus primarily on **three-way merges** → KDiff3

---

## Sources and References

- [WinMerge](https://winmerge.org/) - Open Source differencing and merging tool
- [Meld](https://meldmerge.org/) - Visual diff and merge tool
- [KDiff3](https://kdiff3.sourceforge.net/) - Diff and merge program
- [P4Merge](https://www.perforce.com/products/helix-core-apps/merge-diff-tool-p4merge) - Visual diff/merge tool
- [Beyond Compare](https://www.scootersoftware.com/) - Commercial comparison utility
- [Araxis Merge](https://www.araxis.com/merge/) - Professional diff and merge
- [ExamDiff Pro](https://www.prestosoft.com/edp_examdiffpro.asp) - Windows file comparison
- [Guiffy](https://www.guiffy.com/) - Cross-platform diff and merge
- [DeltaWalker](https://www.deltawalker.com/) - File and folder comparison
