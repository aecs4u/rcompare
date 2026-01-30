# RCompare FFI - C/C++ API

This crate provides a C-compatible Foreign Function Interface (FFI) for the RCompare patch parsing and manipulation library. It is designed to be compatible with libkomparediff2 workflows and can be used in C/C++ applications, including KDE applications.

## Features

- **Parse multiple diff formats**: Unified, context, normal, RCS, ed
- **Auto-detect generators**: CVS, Perforce, Subversion, plain diff
- **Patch manipulation**: Apply/unapply individual or all differences
- **File blending**: Merge original file content with patch hunks
- **Serialization**: Convert patch model back to unified diff format
- **Memory safe**: Opaque handle pattern with proper lifetime management

## Building

### Prerequisites

- Rust toolchain (1.70+)
- CMake (3.15+) for building C/C++ examples
- C99 or C++11 compiler

### Build the Rust Library

```bash
# From the rcompare_ffi directory
cargo build --release

# The static library will be at:
# ../target/release/librcompare_ffi.a (Linux/macOS)
# ..\target\release\rcompare_ffi.lib (Windows)
```

### Build C/C++ Examples with CMake

```bash
# From the rcompare_ffi directory
mkdir build && cd build
cmake ..
cmake --build .

# Run examples
./examples/simple_parse
./examples/patch_apply
```

## Usage

### Basic Parsing Example

```c
#include "rcompare.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    const char* diff_text =
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n";

    // Parse diff
    PatchSetHandle* handle = NULL;
    int result = rcompare_parse_diff(
        (const uint8_t*)diff_text,
        strlen(diff_text),
        &handle
    );

    if (result != 0) {
        fprintf(stderr, "Parse failed\n");
        return 1;
    }

    // Access metadata
    size_t file_count = rcompare_patchset_file_count(handle);
    printf("Files: %zu\n", file_count);

    // Get file information
    const char* source = rcompare_filepatch_source(handle, 0);
    printf("Source: %s\n", source);

    // Iterate hunks and differences
    size_t hunk_count = rcompare_filepatch_hunk_count(handle, 0);
    for (size_t hi = 0; hi < hunk_count; hi++) {
        size_t diff_count = rcompare_hunk_diff_count(handle, 0, hi);
        printf("Hunk %zu has %zu differences\n", hi, diff_count);
    }

    // Serialize back to diff
    char* serialized = rcompare_serialize_diff(handle);
    if (serialized) {
        printf("%s", serialized);
        rcompare_free_string(serialized);
    }

    // Cleanup
    rcompare_free_patchset(handle);
    return 0;
}
```

### Advanced: Blending and Patch Application

```c
#include "rcompare.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    // Parse patch
    PatchSetHandle* handle = NULL;
    const char* diff = /* ... */;
    rcompare_parse_diff((const uint8_t*)diff, strlen(diff), &handle);

    // Blend with original file
    const char* original = "line1\nline2\nline3\n";
    rcompare_blend_file(handle, 0, (const uint8_t*)original, strlen(original));

    // Apply individual difference (flat index 0 = first non-context change)
    rcompare_apply_difference(handle, 0, 0);

    // Or apply all at once
    rcompare_apply_all(handle, 0);

    // Unapply specific difference
    rcompare_unapply_difference(handle, 0, 0);

    // Unapply all
    rcompare_unapply_all(handle, 0);

    rcompare_free_patchset(handle);
    return 0;
}
```

## CMake Integration

To integrate RCompare FFI into your CMake project:

```cmake
# Add RCompare FFI subdirectory
add_subdirectory(path/to/rcompare/rcompare_ffi)

# Link to your target
target_link_libraries(your_target PRIVATE rcompare)
```

Or manually:

```cmake
# Find the library
find_library(RCOMPARE_LIB
    NAMES rcompare_ffi
    PATHS /path/to/rcompare/target/release
)

# Create imported target
add_library(rcompare STATIC IMPORTED)
set_target_properties(rcompare PROPERTIES
    IMPORTED_LOCATION ${RCOMPARE_LIB}
    INTERFACE_INCLUDE_DIRECTORIES /path/to/rcompare/rcompare_ffi/include
)

# Link system libraries (Linux)
target_link_libraries(rcompare INTERFACE pthread dl m)

# Link to your target
target_link_libraries(your_target PRIVATE rcompare)
```

## API Reference

See [include/rcompare.h](include/rcompare.h) for complete API documentation with detailed function descriptions.

### Key Types

- `PatchSetHandle`: Opaque handle to a parsed patch set
- `RCompareDiffFormat`: Diff format enum (Unified, Context, Normal, etc.)
- `RCompareDiffGenerator`: Generator tool enum (diff, CVS, Perforce, etc.)
- `RCompareDifferenceType`: Change type enum (Unchanged, Change, Insert, Delete)
- `RCompareHunkType`: Hunk type enum (Normal, AddedByBlend)

### Main Functions

#### Lifecycle
- `rcompare_parse_diff()` - Parse diff text into PatchSet
- `rcompare_free_patchset()` - Free PatchSet and all associated memory
- `rcompare_free_string()` - Free string from serialization

#### Accessors
- `rcompare_patchset_*()` - Access patch set metadata
- `rcompare_filepatch_*()` - Access file patch properties
- `rcompare_hunk_*()` - Access hunk properties
- `rcompare_diff_*()` - Access individual difference properties

#### Patch Engine
- `rcompare_blend_file()` - Blend original file content
- `rcompare_apply_difference()` - Apply single difference
- `rcompare_unapply_difference()` - Unapply single difference
- `rcompare_apply_all()` - Apply all differences
- `rcompare_unapply_all()` - Unapply all differences

#### Serialization
- `rcompare_serialize_diff()` - Convert PatchSet to unified diff text

## Memory Management

### String Lifetime

Strings returned by accessor functions (e.g., `rcompare_filepatch_source()`) use **arena allocation**:
- Strings are valid until `rcompare_free_patchset()` is called
- Do not call `free()` on these strings
- Multiple calls to the same accessor may return different pointers

Strings returned by `rcompare_serialize_diff()`:
- Must be freed with `rcompare_free_string()`
- Caller owns the memory

### Handle Lifetime

```c
PatchSetHandle* handle = NULL;

// Create
rcompare_parse_diff(data, len, &handle);

// Use (strings valid here)
const char* source = rcompare_filepatch_source(handle, 0);
printf("%s\n", source);

// Destroy (all accessor strings become invalid)
rcompare_free_patchset(handle);

// source is now invalid - do not use!
```

## Error Handling

Functions return:
- `0` on success, `-1` on error (for functions returning `int`)
- `NULL` on error (for functions returning pointers)
- `0` or default values for invalid indices (for accessor functions)

Always check return values:

```c
if (rcompare_parse_diff(data, len, &handle) != 0) {
    fprintf(stderr, "Parse failed\n");
    return 1;
}

char* serialized = rcompare_serialize_diff(handle);
if (!serialized) {
    fprintf(stderr, "Serialization failed\n");
    // handle error
}
```

## Thread Safety

- `PatchSetHandle` is **not thread-safe**
- Do not share handles between threads without external synchronization
- Creating separate handles per thread is safe

## Examples

See the [examples/](examples/) directory for complete working examples:

- [`simple_parse.c`](examples/simple_parse.c) - Basic parsing and inspection
- [`patch_apply.c`](examples/patch_apply.c) - Advanced blending and application

## Testing

The FFI layer has comprehensive tests covering all operations:

```bash
# Run Rust tests
cargo test

# Expected output: 37 tests passed
```

## Platform Support

- **Linux**: Full support (tested on Ubuntu, Fedora, Arch)
- **macOS**: Full support (tested on macOS 12+)
- **Windows**: Full support (MSVC and GNU toolchains)

### Platform-Specific Linking

**Linux:**
```cmake
target_link_libraries(your_target PRIVATE rcompare pthread dl m)
```

**macOS:**
```cmake
target_link_libraries(your_target PRIVATE rcompare
    "-framework Security" "-framework CoreFoundation" pthread dl m)
```

**Windows:**
```cmake
target_link_libraries(your_target PRIVATE rcompare
    ws2_32 userenv bcrypt ntdll)
```

## License

This crate is licensed under the same terms as the parent RCompare project: MIT OR Apache-2.0.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) in the repository root for contribution guidelines.

## Compatibility

This FFI layer is designed to be compatible with libkomparediff2 workflows, making it suitable as a drop-in replacement for applications using libkomparediff2 for patch parsing and manipulation.

### Key Differences from libkomparediff2

1. **Opaque handles**: Uses opaque `PatchSetHandle` instead of exposing C++ classes
2. **Flat indexing**: Differences use flat indices for apply/unapply operations
3. **Arena allocation**: String lifetime tied to handle lifetime for simplicity
4. **No Qt dependency**: Pure C API with no Qt/KDE framework dependencies

### Migration Tips

If migrating from libkomparediff2:

1. Replace `Diff2::KompareModelList` with `PatchSetHandle`
2. Replace parser initialization with `rcompare_parse_diff()`
3. Replace accessor methods with `rcompare_*` functions
4. Update apply/unapply logic to use flat indices
5. Add proper `rcompare_free_patchset()` cleanup

## Support

For issues, questions, or contributions, please visit:
https://github.com/aecs4u/rcompare
