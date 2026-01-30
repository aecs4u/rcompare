/*
 * rcompare_ffi.h - C FFI for rcompare patch parsing, engine, and serialization.
 *
 * All functions use opaque RComparePatchSet handles.
 * String pointers returned by accessor functions are valid until
 * rcompare_free_patchset() is called on the owning handle.
 */

#ifndef RCOMPARE_FFI_H
#define RCOMPARE_FFI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque handle */
typedef struct RComparePatchSet RComparePatchSet;

/* --- Enums (match Rust repr(u32)) --- */

/* DiffFormat */
#define RCOMPARE_FORMAT_UNKNOWN  0
#define RCOMPARE_FORMAT_UNIFIED  1
#define RCOMPARE_FORMAT_CONTEXT  2
#define RCOMPARE_FORMAT_NORMAL   3
#define RCOMPARE_FORMAT_ED       4
#define RCOMPARE_FORMAT_RCS      5

/* DiffGenerator */
#define RCOMPARE_GEN_UNKNOWN     0
#define RCOMPARE_GEN_DIFF        1
#define RCOMPARE_GEN_CVSDIFF     2
#define RCOMPARE_GEN_PERFORCE    3
#define RCOMPARE_GEN_SUBVERSION  4

/* DifferenceType */
#define RCOMPARE_DIFF_UNCHANGED  0
#define RCOMPARE_DIFF_CHANGE     1
#define RCOMPARE_DIFF_INSERT     2
#define RCOMPARE_DIFF_DELETE     3

/* HunkType */
#define RCOMPARE_HUNK_NORMAL        0
#define RCOMPARE_HUNK_ADDEDBYBLEND  1

/* --- Lifecycle --- */

/**
 * Parse diff text and create a PatchSet handle.
 * @param input  UTF-8 diff text
 * @param len    Length of input in bytes
 * @param out    Receives the handle on success
 * @return 0 on success, -1 on error
 */
int rcompare_parse_diff(const unsigned char *input, size_t len,
                        RComparePatchSet **out);

/** Free a PatchSet handle and all associated memory. */
void rcompare_free_patchset(RComparePatchSet *handle);

/** Free a string returned by rcompare_serialize_diff. */
void rcompare_free_string(char *s);

/* --- PatchSet accessors --- */

size_t   rcompare_patchset_file_count(const RComparePatchSet *h);
uint32_t rcompare_patchset_format(const RComparePatchSet *h);
uint32_t rcompare_patchset_generator(const RComparePatchSet *h);

/* --- FilePatch accessors (by file index) --- */

const char *rcompare_filepatch_source(RComparePatchSet *h, size_t idx);
const char *rcompare_filepatch_destination(RComparePatchSet *h, size_t idx);
const char *rcompare_filepatch_source_timestamp(RComparePatchSet *h, size_t idx);
const char *rcompare_filepatch_dest_timestamp(RComparePatchSet *h, size_t idx);
const char *rcompare_filepatch_source_revision(RComparePatchSet *h, size_t idx);
const char *rcompare_filepatch_dest_revision(RComparePatchSet *h, size_t idx);
size_t      rcompare_filepatch_hunk_count(const RComparePatchSet *h, size_t idx);
int         rcompare_filepatch_is_blended(const RComparePatchSet *h, size_t idx);

/* --- Hunk accessors (file_idx fi, hunk_idx hi) --- */

size_t      rcompare_hunk_source_start(const RComparePatchSet *h, size_t fi, size_t hi);
size_t      rcompare_hunk_source_count(const RComparePatchSet *h, size_t fi, size_t hi);
size_t      rcompare_hunk_dest_start(const RComparePatchSet *h, size_t fi, size_t hi);
size_t      rcompare_hunk_dest_count(const RComparePatchSet *h, size_t fi, size_t hi);
const char *rcompare_hunk_function_name(RComparePatchSet *h, size_t fi, size_t hi);
size_t      rcompare_hunk_diff_count(const RComparePatchSet *h, size_t fi, size_t hi);
uint32_t    rcompare_hunk_type(const RComparePatchSet *h, size_t fi, size_t hi);

/* --- Difference accessors (file_idx fi, hunk_idx hi, diff_idx di) --- */

uint32_t    rcompare_diff_type(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
size_t      rcompare_diff_source_line_no(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
size_t      rcompare_diff_dest_line_no(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
size_t      rcompare_diff_source_line_count(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
size_t      rcompare_diff_dest_line_count(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
const char *rcompare_diff_source_line_at(RComparePatchSet *h, size_t fi, size_t hi, size_t di, size_t li);
const char *rcompare_diff_dest_line_at(RComparePatchSet *h, size_t fi, size_t hi, size_t di, size_t li);
int         rcompare_diff_applied(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);
int         rcompare_diff_conflict(const RComparePatchSet *h, size_t fi, size_t hi, size_t di);

/* --- Patch engine --- */

/**
 * Blend original file content into a FilePatch, adding context hunks.
 * @return 0 on success, -1 on error
 */
int rcompare_blend_file(RComparePatchSet *h, size_t fi,
                        const unsigned char *content, size_t len);

int rcompare_apply_difference(RComparePatchSet *h, size_t fi, size_t flat_idx);
int rcompare_unapply_difference(RComparePatchSet *h, size_t fi, size_t flat_idx);
int rcompare_apply_all(RComparePatchSet *h, size_t fi);
int rcompare_unapply_all(RComparePatchSet *h, size_t fi);

/* --- Serialization --- */

/**
 * Serialize the PatchSet to unified diff text.
 * @return Newly allocated C string (caller must free with rcompare_free_string),
 *         or NULL on error.
 */
char *rcompare_serialize_diff(const RComparePatchSet *h);

#ifdef __cplusplus
}
#endif

#endif /* RCOMPARE_FFI_H */
