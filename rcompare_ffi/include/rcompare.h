/**
 * @file rcompare.h
 * @brief C API for RCompare patch parsing and manipulation
 *
 * This library provides libkomparediff2-compatible patch parsing, manipulation,
 * and serialization functionality. It supports unified diff, context diff, and
 * other common diff formats.
 *
 * @example
 * ```c
 * // Parse a diff
 * PatchSetHandle* handle = NULL;
 * const char* diff_text = "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n";
 * if (rcompare_parse_diff((const uint8_t*)diff_text, strlen(diff_text), &handle) == 0) {
 *     // Access patch data
 *     size_t file_count = rcompare_patchset_file_count(handle);
 *
 *     // Serialize back to diff
 *     char* serialized = rcompare_serialize_diff(handle);
 *     printf("%s", serialized);
 *
 *     // Cleanup
 *     rcompare_free_string(serialized);
 *     rcompare_free_patchset(handle);
 * }
 * ```
 *
 * @note All string pointers returned by accessor functions are valid until
 *       rcompare_free_patchset() is called (arena allocation pattern).
 *
 * @note Strings returned by rcompare_serialize_diff() must be freed with
 *       rcompare_free_string().
 */

#ifndef RCOMPARE_H
#define RCOMPARE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

/**
 * @brief Opaque handle to a parsed patch set
 *
 * Created by rcompare_parse_diff() and freed by rcompare_free_patchset().
 * Do not attempt to dereference or manipulate directly.
 */
typedef struct PatchSetHandle PatchSetHandle;

/* ========================================================================== */
/*                              Enumerations                                  */
/* ========================================================================== */

/**
 * @brief Diff output format types
 */
typedef enum {
    RCOMPARE_FORMAT_UNKNOWN = 0,  /**< Unknown or mixed format */
    RCOMPARE_FORMAT_UNIFIED = 1,  /**< Unified diff (diff -u) */
    RCOMPARE_FORMAT_CONTEXT = 2,  /**< Context diff (diff -c) */
    RCOMPARE_FORMAT_NORMAL = 3,   /**< Normal diff (diff) */
    RCOMPARE_FORMAT_ED = 4,       /**< Ed script format */
    RCOMPARE_FORMAT_RCS = 5       /**< RCS format */
} RCompareDiffFormat;

/**
 * @brief Tool that generated the diff output
 */
typedef enum {
    RCOMPARE_GENERATOR_UNKNOWN = 0,    /**< Unknown generator */
    RCOMPARE_GENERATOR_DIFF = 1,       /**< Plain diff utility */
    RCOMPARE_GENERATOR_CVS = 2,        /**< CVS diff */
    RCOMPARE_GENERATOR_PERFORCE = 3,   /**< Perforce */
    RCOMPARE_GENERATOR_SUBVERSION = 4  /**< Subversion */
} RCompareDiffGenerator;

/**
 * @brief Type of a difference block
 */
typedef enum {
    RCOMPARE_DIFF_UNCHANGED = 0,  /**< Context line (unchanged) */
    RCOMPARE_DIFF_CHANGE = 1,     /**< Modified line(s) */
    RCOMPARE_DIFF_INSERT = 2,     /**< Added line(s) */
    RCOMPARE_DIFF_DELETE = 3      /**< Removed line(s) */
} RCompareDifferenceType;

/**
 * @brief Hunk type (original vs blended)
 */
typedef enum {
    RCOMPARE_HUNK_NORMAL = 0,        /**< Original hunk from diff */
    RCOMPARE_HUNK_ADDED_BY_BLEND = 1 /**< Context added by blending */
} RCompareHunkType;

/* ========================================================================== */
/*                           Lifecycle Functions                              */
/* ========================================================================== */

/**
 * @brief Parse diff text into a PatchSet
 *
 * @param input Pointer to UTF-8 encoded diff text
 * @param len Length of input in bytes
 * @param out Output parameter for the PatchSetHandle
 * @return 0 on success, -1 on error
 *
 * @note The caller must free the handle with rcompare_free_patchset()
 * @note Returns -1 if input is NULL, out is NULL, or parsing fails
 */
int rcompare_parse_diff(const uint8_t* input, size_t len, PatchSetHandle** out);

/**
 * @brief Free a PatchSet handle and all associated memory
 *
 * @param handle Handle to free (can be NULL)
 *
 * @note Safe to call with NULL handle
 * @note After calling, all string pointers from accessors become invalid
 */
void rcompare_free_patchset(PatchSetHandle* handle);

/**
 * @brief Free a string returned by rcompare_serialize_diff()
 *
 * @param s String to free (can be NULL)
 *
 * @note Safe to call with NULL
 * @note Do not use this to free strings from accessor functions
 */
void rcompare_free_string(char* s);

/* ========================================================================== */
/*                         PatchSet Accessors                                 */
/* ========================================================================== */

/**
 * @brief Get the number of file patches in the set
 *
 * @param handle PatchSet handle
 * @return Number of files, or 0 if handle is NULL
 */
size_t rcompare_patchset_file_count(const PatchSetHandle* handle);

/**
 * @brief Get the detected diff format
 *
 * @param handle PatchSet handle
 * @return Format enum value, or RCOMPARE_FORMAT_UNKNOWN if handle is NULL
 */
uint32_t rcompare_patchset_format(const PatchSetHandle* handle);

/**
 * @brief Get the detected diff generator
 *
 * @param handle PatchSet handle
 * @return Generator enum value, or RCOMPARE_GENERATOR_UNKNOWN if handle is NULL
 */
uint32_t rcompare_patchset_generator(const PatchSetHandle* handle);

/* ========================================================================== */
/*                         FilePatch Accessors                                */
/* ========================================================================== */

/**
 * @brief Get the source file path
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Source path string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_source(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the destination file path
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Destination path string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_destination(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the source file timestamp
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Timestamp string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_source_timestamp(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the destination file timestamp
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Timestamp string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_dest_timestamp(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the source file revision string
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Revision string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_source_revision(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the destination file revision string
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Revision string, or NULL if handle/index invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_filepatch_dest_revision(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Get the number of hunks in a file patch
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return Number of hunks, or 0 if handle/index invalid
 */
size_t rcompare_filepatch_hunk_count(const PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Check if original file has been blended into the patch
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return 1 if blended, 0 if not or if handle/index invalid
 */
int rcompare_filepatch_is_blended(const PatchSetHandle* handle, size_t file_idx);

/* ========================================================================== */
/*                            Hunk Accessors                                  */
/* ========================================================================== */

/**
 * @brief Get the source file starting line number for a hunk
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Line number (1-based), or 0 if handle/indices invalid
 */
size_t rcompare_hunk_source_start(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the number of source lines in a hunk
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Line count, or 0 if handle/indices invalid
 */
size_t rcompare_hunk_source_count(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the destination file starting line number for a hunk
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Line number (1-based), or 0 if handle/indices invalid
 */
size_t rcompare_hunk_dest_start(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the number of destination lines in a hunk
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Line count, or 0 if handle/indices invalid
 */
size_t rcompare_hunk_dest_count(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the function/context name from hunk header
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Function name string, or NULL if not present or handle/indices invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_hunk_function_name(PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the number of differences in a hunk
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Number of differences, or 0 if handle/indices invalid
 */
size_t rcompare_hunk_diff_count(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/**
 * @brief Get the hunk type (normal vs added by blend)
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @return Hunk type enum value, or 0 if handle/indices invalid
 */
uint32_t rcompare_hunk_type(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx);

/* ========================================================================== */
/*                        Difference Accessors                                */
/* ========================================================================== */

/**
 * @brief Get the type of a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return Difference type enum value, or 0 if handle/indices invalid
 */
uint32_t rcompare_diff_type(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Get the source file line number for a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return Line number (1-based), or 0 if handle/indices invalid
 */
size_t rcompare_diff_source_line_no(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Get the destination file line number for a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return Line number (1-based), or 0 if handle/indices invalid
 */
size_t rcompare_diff_dest_line_no(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Get the number of source lines in a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return Line count, or 0 if handle/indices invalid
 */
size_t rcompare_diff_source_line_count(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Get the number of destination lines in a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return Line count, or 0 if handle/indices invalid
 */
size_t rcompare_diff_dest_line_count(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Get a source line from a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @param line_idx Line index within the difference (0-based)
 * @return Line string, or NULL if handle/indices invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_diff_source_line_at(PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx, size_t line_idx);

/**
 * @brief Get a destination line from a difference
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @param line_idx Line index within the difference (0-based)
 * @return Line string, or NULL if handle/indices invalid
 *
 * @note String valid until rcompare_free_patchset() is called
 */
const char* rcompare_diff_dest_line_at(PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx, size_t line_idx);

/**
 * @brief Check if a difference has been applied
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return 1 if applied, 0 if not or if handle/indices invalid
 */
int rcompare_diff_applied(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/**
 * @brief Check if a difference has a conflict
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param hunk_idx Hunk index (0-based)
 * @param diff_idx Difference index (0-based)
 * @return 1 if conflict exists, 0 if not or if handle/indices invalid
 */
int rcompare_diff_conflict(const PatchSetHandle* handle, size_t file_idx, size_t hunk_idx, size_t diff_idx);

/* ========================================================================== */
/*                           Patch Engine Functions                           */
/* ========================================================================== */

/**
 * @brief Blend original file content into a file patch
 *
 * This inserts context hunks containing the original file content around
 * and between the patch hunks, creating a complete file model.
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param content Original file content (UTF-8)
 * @param len Length of content in bytes
 * @return 0 on success, -1 on error
 *
 * @note After blending, rcompare_filepatch_is_blended() returns 1
 */
int rcompare_blend_file(PatchSetHandle* handle, size_t file_idx, const uint8_t* content, size_t len);

/**
 * @brief Apply a single difference by flat index
 *
 * Flat index counts only non-Unchanged differences across all hunks.
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param flat_diff_idx Flat difference index (0-based)
 * @return 0 on success, -1 on error
 *
 * @note Updates tracking line numbers for subsequent differences
 */
int rcompare_apply_difference(PatchSetHandle* handle, size_t file_idx, size_t flat_diff_idx);

/**
 * @brief Unapply a single difference by flat index
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @param flat_diff_idx Flat difference index (0-based)
 * @return 0 on success, -1 on error
 *
 * @note Updates tracking line numbers for subsequent differences
 */
int rcompare_unapply_difference(PatchSetHandle* handle, size_t file_idx, size_t flat_diff_idx);

/**
 * @brief Apply all differences in a file patch
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return 0 on success, -1 on error
 */
int rcompare_apply_all(PatchSetHandle* handle, size_t file_idx);

/**
 * @brief Unapply all differences in a file patch
 *
 * @param handle PatchSet handle
 * @param file_idx File index (0-based)
 * @return 0 on success, -1 on error
 */
int rcompare_unapply_all(PatchSetHandle* handle, size_t file_idx);

/* ========================================================================== */
/*                        Serialization Functions                             */
/* ========================================================================== */

/**
 * @brief Serialize a PatchSet to unified diff text
 *
 * @param handle PatchSet handle
 * @return Newly allocated C string containing unified diff, or NULL on error
 *
 * @note Caller must free the returned string with rcompare_free_string()
 * @note Blended hunks are skipped during serialization
 */
char* rcompare_serialize_diff(const PatchSetHandle* handle);

#ifdef __cplusplus
}
#endif

#endif /* RCOMPARE_H */
