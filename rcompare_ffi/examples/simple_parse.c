/**
 * @file simple_parse.c
 * @brief Simple example of parsing and inspecting a unified diff
 *
 * Demonstrates:
 * - Parsing diff text
 * - Accessing patch metadata
 * - Iterating through files, hunks, and differences
 * - Serializing back to diff format
 * - Proper memory management
 */

#include "rcompare.h"
#include <stdio.h>
#include <string.h>

// Sample unified diff
static const char* SAMPLE_DIFF =
    "--- a/hello.c\t2024-01-01 10:00:00\n"
    "+++ b/hello.c\t2024-01-02 11:00:00\n"
    "@@ -1,5 +1,6 @@ int main()\n"
    " #include <stdio.h>\n"
    " \n"
    " int main() {\n"
    "-    printf(\"Hello\\n\");\n"
    "+    printf(\"Hello, World!\\n\");\n"
    "+    printf(\"Welcome to RCompare\\n\");\n"
    "     return 0;\n"
    " }\n";

int main(void) {
    printf("RCompare FFI Simple Example\n");
    printf("============================\n\n");

    // Parse the diff
    PatchSetHandle* handle = NULL;
    int result = rcompare_parse_diff(
        (const uint8_t*)SAMPLE_DIFF,
        strlen(SAMPLE_DIFF),
        &handle
    );

    if (result != 0 || handle == NULL) {
        fprintf(stderr, "Error: Failed to parse diff\n");
        return 1;
    }

    printf("✓ Parsed diff successfully\n\n");

    // Get patch metadata
    size_t file_count = rcompare_patchset_file_count(handle);
    uint32_t format = rcompare_patchset_format(handle);
    uint32_t generator = rcompare_patchset_generator(handle);

    printf("Patch Metadata:\n");
    printf("  Files: %zu\n", file_count);
    printf("  Format: %u (%s)\n", format,
           format == RCOMPARE_FORMAT_UNIFIED ? "Unified" :
           format == RCOMPARE_FORMAT_CONTEXT ? "Context" : "Other");
    printf("  Generator: %u (%s)\n\n", generator,
           generator == RCOMPARE_GENERATOR_DIFF ? "diff" :
           generator == RCOMPARE_GENERATOR_CVS ? "CVS" : "Other");

    // Iterate through files
    for (size_t fi = 0; fi < file_count; fi++) {
        printf("File %zu:\n", fi + 1);

        const char* source = rcompare_filepatch_source(handle, fi);
        const char* dest = rcompare_filepatch_destination(handle, fi);
        const char* src_time = rcompare_filepatch_source_timestamp(handle, fi);
        const char* dst_time = rcompare_filepatch_dest_timestamp(handle, fi);

        printf("  Source: %s", source ? source : "(null)");
        if (src_time && strlen(src_time) > 0) {
            printf(" (%s)", src_time);
        }
        printf("\n");

        printf("  Dest:   %s", dest ? dest : "(null)");
        if (dst_time && strlen(dst_time) > 0) {
            printf(" (%s)", dst_time);
        }
        printf("\n");

        // Iterate through hunks
        size_t hunk_count = rcompare_filepatch_hunk_count(handle, fi);
        printf("  Hunks: %zu\n", hunk_count);

        for (size_t hi = 0; hi < hunk_count; hi++) {
            size_t src_start = rcompare_hunk_source_start(handle, fi, hi);
            size_t src_count = rcompare_hunk_source_count(handle, fi, hi);
            size_t dst_start = rcompare_hunk_dest_start(handle, fi, hi);
            size_t dst_count = rcompare_hunk_dest_count(handle, fi, hi);
            const char* func_name = rcompare_hunk_function_name(handle, fi, hi);

            printf("\n  Hunk %zu: @@ -%zu,%zu +%zu,%zu @@",
                   hi + 1, src_start, src_count, dst_start, dst_count);
            if (func_name && strlen(func_name) > 0) {
                printf(" %s", func_name);
            }
            printf("\n");

            // Iterate through differences
            size_t diff_count = rcompare_hunk_diff_count(handle, fi, hi);

            size_t unchanged = 0, changes = 0, inserts = 0, deletes = 0;
            for (size_t di = 0; di < diff_count; di++) {
                uint32_t diff_type = rcompare_diff_type(handle, fi, hi, di);

                switch (diff_type) {
                    case RCOMPARE_DIFF_UNCHANGED:
                        unchanged++;
                        break;
                    case RCOMPARE_DIFF_CHANGE:
                        changes++;
                        break;
                    case RCOMPARE_DIFF_INSERT:
                        inserts++;
                        break;
                    case RCOMPARE_DIFF_DELETE:
                        deletes++;
                        break;
                }
            }

            printf("    Differences: %zu total\n", diff_count);
            printf("      - Unchanged: %zu\n", unchanged);
            printf("      - Changes:   %zu\n", changes);
            printf("      - Inserts:   %zu\n", inserts);
            printf("      - Deletes:   %zu\n", deletes);
        }
    }

    // Serialize back to diff format
    printf("\n\nSerialized Output:\n");
    printf("==================\n");
    char* serialized = rcompare_serialize_diff(handle);
    if (serialized) {
        printf("%s", serialized);
        rcompare_free_string(serialized);
    } else {
        fprintf(stderr, "Error: Failed to serialize diff\n");
    }

    // Cleanup
    rcompare_free_patchset(handle);
    printf("\n✓ Cleanup complete\n");

    return 0;
}
