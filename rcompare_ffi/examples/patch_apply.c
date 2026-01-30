/**
 * @file patch_apply.c
 * @brief Advanced example demonstrating patch blending and application
 *
 * Demonstrates:
 * - Blending original file content with patch
 * - Applying and unapplying individual differences
 * - Applying all differences at once
 * - Inspecting applied state
 */

#include "rcompare.h"
#include <stdio.h>
#include <string.h>

static const char* SAMPLE_DIFF =
    "--- a/config.txt\n"
    "+++ b/config.txt\n"
    "@@ -3,3 +3,3 @@\n"
    " setting2=value2\n"
    "-setting3=old_value\n"
    "+setting3=new_value\n"
    " setting4=value4\n";

static const char* ORIGINAL_FILE =
    "setting1=value1\n"
    "setting2=value2\n"
    "setting3=old_value\n"
    "setting4=value4\n"
    "setting5=value5\n";

static void print_difference(PatchSetHandle* handle, size_t fi, size_t hi, size_t di) {
    uint32_t diff_type = rcompare_diff_type(handle, fi, hi, di);
    size_t src_line_no = rcompare_diff_source_line_no(handle, fi, hi, di);
    size_t dst_line_no = rcompare_diff_dest_line_no(handle, fi, hi, di);
    size_t src_count = rcompare_diff_source_line_count(handle, fi, hi, di);
    size_t dst_count = rcompare_diff_dest_line_count(handle, fi, hi, di);
    int applied = rcompare_diff_applied(handle, fi, hi, di);

    const char* type_str = "Unknown";
    switch (diff_type) {
        case RCOMPARE_DIFF_UNCHANGED:
            type_str = "Unchanged";
            break;
        case RCOMPARE_DIFF_CHANGE:
            type_str = "Change";
            break;
        case RCOMPARE_DIFF_INSERT:
            type_str = "Insert";
            break;
        case RCOMPARE_DIFF_DELETE:
            type_str = "Delete";
            break;
    }

    printf("    Diff %zu [%s]:\n", di, type_str);
    printf("      Source: line %zu (%zu lines)\n", src_line_no, src_count);
    printf("      Dest:   line %zu (%zu lines)\n", dst_line_no, dst_count);
    printf("      Applied: %s\n", applied ? "Yes" : "No");

    // Show source lines
    if (src_count > 0) {
        printf("      Source lines:\n");
        for (size_t li = 0; li < src_count; li++) {
            const char* line = rcompare_diff_source_line_at(handle, fi, hi, di, li);
            if (line) {
                printf("        - %s", line);
                if (line[strlen(line) - 1] != '\n') {
                    printf("\n");
                }
            }
        }
    }

    // Show destination lines
    if (dst_count > 0) {
        printf("      Dest lines:\n");
        for (size_t li = 0; li < dst_count; li++) {
            const char* line = rcompare_diff_dest_line_at(handle, fi, hi, di, li);
            if (line) {
                printf("        + %s", line);
                if (line[strlen(line) - 1] != '\n') {
                    printf("\n");
                }
            }
        }
    }
}

int main(void) {
    printf("RCompare FFI Patch Application Example\n");
    printf("=======================================\n\n");

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

    printf("✓ Parsed diff successfully\n");

    // Show initial state
    printf("\nOriginal file content:\n");
    printf("----------------------\n%s\n", ORIGINAL_FILE);

    // Blend the original file with the patch
    printf("Blending original file with patch...\n");
    result = rcompare_blend_file(
        handle,
        0,
        (const uint8_t*)ORIGINAL_FILE,
        strlen(ORIGINAL_FILE)
    );

    if (result != 0) {
        fprintf(stderr, "Error: Failed to blend file\n");
        rcompare_free_patchset(handle);
        return 1;
    }

    int is_blended = rcompare_filepatch_is_blended(handle, 0);
    printf("✓ File blended: %s\n", is_blended ? "Yes" : "No");

    // Show hunks after blending
    size_t hunk_count = rcompare_filepatch_hunk_count(handle, 0);
    printf("\nHunks after blending: %zu\n", hunk_count);

    for (size_t hi = 0; hi < hunk_count; hi++) {
        uint32_t hunk_type = rcompare_hunk_type(handle, 0, hi);
        size_t diff_count = rcompare_hunk_diff_count(handle, 0, hi);

        printf("\n  Hunk %zu (%s): %zu differences\n",
               hi + 1,
               hunk_type == RCOMPARE_HUNK_NORMAL ? "Original" : "Blended",
               diff_count);
    }

    // Find and apply only Change differences (flat indexed)
    printf("\n\nApplying individual change differences:\n");
    printf("---------------------------------------\n");

    // First, count non-Unchanged differences to get flat index range
    size_t flat_idx = 0;
    for (size_t hi = 0; hi < hunk_count; hi++) {
        size_t diff_count = rcompare_hunk_diff_count(handle, 0, hi);
        for (size_t di = 0; di < diff_count; di++) {
            uint32_t diff_type = rcompare_diff_type(handle, 0, hi, di);
            if (diff_type != RCOMPARE_DIFF_UNCHANGED) {
                printf("\nFlat index %zu:\n", flat_idx);
                print_difference(handle, 0, hi, di);

                // Apply this difference
                result = rcompare_apply_difference(handle, 0, flat_idx);
                if (result == 0) {
                    printf("  ✓ Applied successfully\n");

                    // Verify it's now marked as applied
                    int applied = rcompare_diff_applied(handle, 0, hi, di);
                    printf("  Applied status: %s\n", applied ? "Applied" : "Not applied");
                } else {
                    fprintf(stderr, "  ✗ Failed to apply\n");
                }

                flat_idx++;
            }
        }
    }

    // Unapply all and reapply in one operation
    printf("\n\nUnapplying all differences:\n");
    printf("---------------------------\n");
    result = rcompare_unapply_all(handle, 0);
    if (result == 0) {
        printf("✓ Unapplied all differences\n");
    } else {
        fprintf(stderr, "✗ Failed to unapply all\n");
    }

    printf("\nApplying all differences at once:\n");
    printf("---------------------------------\n");
    result = rcompare_apply_all(handle, 0);
    if (result == 0) {
        printf("✓ Applied all differences\n");
    } else {
        fprintf(stderr, "✗ Failed to apply all\n");
    }

    // Show final serialized output
    printf("\n\nFinal serialized patch (blended hunks excluded):\n");
    printf("================================================\n");
    char* serialized = rcompare_serialize_diff(handle);
    if (serialized) {
        printf("%s", serialized);
        rcompare_free_string(serialized);
    }

    // Cleanup
    rcompare_free_patchset(handle);
    printf("\n✓ Cleanup complete\n");

    return 0;
}
