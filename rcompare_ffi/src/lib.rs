//! C FFI layer for rcompare's patch parsing, engine, and serialization.
//!
//! Exposes opaque PatchSet handles and accessor functions for use from C/C++.
//! All strings returned by accessor functions are owned by the PatchSet and
//! valid until `rcompare_free_patchset` is called (arena pattern).

#![allow(private_interfaces)]

use rcompare_common::{DiffFormat, DiffGenerator, HunkType, PatchSet};
use rcompare_core::{PatchEngine, PatchParser, PatchSerializer};
use std::ffi::{c_char, CString};
use std::ptr;

/// Opaque handle to a PatchSet, with pre-computed CString cache for arena allocation.
struct PatchSetHandle {
    patch_set: PatchSet,
    /// Cached CStrings for all string fields, kept alive until handle is freed.
    string_cache: Vec<CString>,
}

impl PatchSetHandle {
    fn new(ps: PatchSet) -> Self {
        Self {
            patch_set: ps,
            string_cache: Vec::new(),
        }
    }

    /// Cache a string and return a pointer valid for the lifetime of this handle.
    fn cache_str(&mut self, s: &str) -> *const c_char {
        let cs = CString::new(s).unwrap_or_default();
        let ptr = cs.as_ptr();
        self.string_cache.push(cs);
        ptr
    }
}

// ===== Lifecycle =====

/// Parse diff text and create a PatchSet handle.
/// Returns 0 on success, -1 on error.
/// On success, `*out` is set to the handle (caller must free with `rcompare_free_patchset`).
#[no_mangle]
pub unsafe extern "C" fn rcompare_parse_diff(
    input: *const u8,
    len: usize,
    out: *mut *mut PatchSetHandle,
) -> i32 {
    if input.is_null() || out.is_null() {
        return -1;
    }
    let slice = std::slice::from_raw_parts(input, len);
    let text = match std::str::from_utf8(slice) {
        Ok(s) => s,
        Err(_) => return -1,
    };

    let parser = PatchParser::new();
    match parser.parse_string(text) {
        Ok(ps) => {
            let handle = Box::new(PatchSetHandle::new(ps));
            *out = Box::into_raw(handle);
            0
        }
        Err(_) => -1,
    }
}

/// Free a PatchSet handle and all cached strings.
#[no_mangle]
pub unsafe extern "C" fn rcompare_free_patchset(handle: *mut PatchSetHandle) {
    if !handle.is_null() {
        drop(Box::from_raw(handle));
    }
}

/// Free a string allocated by `rcompare_serialize_diff`.
#[no_mangle]
pub unsafe extern "C" fn rcompare_free_string(s: *mut c_char) {
    if !s.is_null() {
        drop(CString::from_raw(s));
    }
}

// ===== PatchSet accessors =====

#[no_mangle]
pub unsafe extern "C" fn rcompare_patchset_file_count(h: *const PatchSetHandle) -> usize {
    if h.is_null() {
        return 0;
    }
    (*h).patch_set.files.len()
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_patchset_format(h: *const PatchSetHandle) -> u32 {
    if h.is_null() {
        return DiffFormat::Unknown as u32;
    }
    (*h).patch_set.format as u32
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_patchset_generator(h: *const PatchSetHandle) -> u32 {
    if h.is_null() {
        return DiffGenerator::Unknown as u32;
    }
    (*h).patch_set.generator as u32
}

// ===== FilePatch accessors =====

macro_rules! fp_string_accessor {
    ($name:ident, $field:ident) => {
        #[no_mangle]
        pub unsafe extern "C" fn $name(
            h: *mut PatchSetHandle,
            idx: usize,
        ) -> *const c_char {
            if h.is_null() {
                return ptr::null();
            }
            let handle = &mut *h;
            if idx >= handle.patch_set.files.len() {
                return ptr::null();
            }
            handle.cache_str(&handle.patch_set.files[idx].$field.clone())
        }
    };
}

fp_string_accessor!(rcompare_filepatch_source, source);
fp_string_accessor!(rcompare_filepatch_destination, destination);
fp_string_accessor!(rcompare_filepatch_source_timestamp, source_timestamp);
fp_string_accessor!(rcompare_filepatch_dest_timestamp, dest_timestamp);
fp_string_accessor!(rcompare_filepatch_source_revision, source_revision);
fp_string_accessor!(rcompare_filepatch_dest_revision, dest_revision);

#[no_mangle]
pub unsafe extern "C" fn rcompare_filepatch_hunk_count(
    h: *const PatchSetHandle,
    idx: usize,
) -> usize {
    if h.is_null() {
        return 0;
    }
    let ps = &(*h).patch_set;
    if idx >= ps.files.len() {
        return 0;
    }
    ps.files[idx].hunks.len()
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_filepatch_is_blended(
    h: *const PatchSetHandle,
    idx: usize,
) -> i32 {
    if h.is_null() {
        return 0;
    }
    let ps = &(*h).patch_set;
    if idx >= ps.files.len() {
        return 0;
    }
    ps.files[idx].blended as i32
}

// ===== Hunk accessors =====

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_source_start(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> usize {
    get_hunk(h, fi, hi).map_or(0, |hk| hk.source_start)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_source_count(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> usize {
    get_hunk(h, fi, hi).map_or(0, |hk| hk.source_count)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_dest_start(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> usize {
    get_hunk(h, fi, hi).map_or(0, |hk| hk.dest_start)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_dest_count(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> usize {
    get_hunk(h, fi, hi).map_or(0, |hk| hk.dest_count)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_function_name(
    h: *mut PatchSetHandle,
    fi: usize,
    hi: usize,
) -> *const c_char {
    if h.is_null() {
        return ptr::null();
    }
    let handle = &mut *h;
    let name = handle
        .patch_set
        .files
        .get(fi)
        .and_then(|fp| fp.hunks.get(hi))
        .and_then(|hk| hk.function_name.clone());
    match name {
        Some(s) => handle.cache_str(&s),
        None => ptr::null(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_diff_count(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> usize {
    get_hunk(h, fi, hi).map_or(0, |hk| hk.differences.len())
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_hunk_type(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> u32 {
    get_hunk(h, fi, hi).map_or(0, |hk| match hk.hunk_type {
        HunkType::Normal => 0,
        HunkType::AddedByBlend => 1,
    })
}

// ===== Difference accessors =====

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_type(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> u32 {
    get_diff(h, fi, hi, di).map_or(0, |d| d.diff_type as u32)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_source_line_no(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> usize {
    get_diff(h, fi, hi, di).map_or(0, |d| d.source_line_no)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_dest_line_no(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> usize {
    get_diff(h, fi, hi, di).map_or(0, |d| d.dest_line_no)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_source_line_count(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> usize {
    get_diff(h, fi, hi, di).map_or(0, |d| d.source_line_count())
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_dest_line_count(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> usize {
    get_diff(h, fi, hi, di).map_or(0, |d| d.dest_line_count())
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_source_line_at(
    h: *mut PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
    li: usize,
) -> *const c_char {
    if h.is_null() {
        return ptr::null();
    }
    let handle = &mut *h;
    let line = handle
        .patch_set
        .files
        .get(fi)
        .and_then(|fp| fp.hunks.get(hi))
        .and_then(|hk| hk.differences.get(di))
        .and_then(|d| d.source_lines.get(li))
        .cloned();
    match line {
        Some(s) => handle.cache_str(&s),
        None => ptr::null(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_dest_line_at(
    h: *mut PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
    li: usize,
) -> *const c_char {
    if h.is_null() {
        return ptr::null();
    }
    let handle = &mut *h;
    let line = handle
        .patch_set
        .files
        .get(fi)
        .and_then(|fp| fp.hunks.get(hi))
        .and_then(|hk| hk.differences.get(di))
        .and_then(|d| d.dest_lines.get(li))
        .cloned();
    match line {
        Some(s) => handle.cache_str(&s),
        None => ptr::null(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_applied(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> i32 {
    get_diff(h, fi, hi, di).map_or(0, |d| d.applied as i32)
}

#[no_mangle]
pub unsafe extern "C" fn rcompare_diff_conflict(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> i32 {
    get_diff(h, fi, hi, di).map_or(0, |d| d.conflict as i32)
}

// ===== Patch engine =====

/// Blend original file content into a FilePatch.
/// Returns 0 on success, -1 on error.
#[no_mangle]
pub unsafe extern "C" fn rcompare_blend_file(
    h: *mut PatchSetHandle,
    fi: usize,
    content: *const u8,
    len: usize,
) -> i32 {
    if h.is_null() || content.is_null() {
        return -1;
    }
    let handle = &mut *h;
    if fi >= handle.patch_set.files.len() {
        return -1;
    }
    let slice = std::slice::from_raw_parts(content, len);
    let text = match std::str::from_utf8(slice) {
        Ok(s) => s,
        Err(_) => return -1,
    };
    match PatchEngine::blend_file(&mut handle.patch_set.files[fi], text) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Apply a single difference by flat index.
#[no_mangle]
pub unsafe extern "C" fn rcompare_apply_difference(
    h: *mut PatchSetHandle,
    fi: usize,
    flat_idx: usize,
) -> i32 {
    if h.is_null() {
        return -1;
    }
    let handle = &mut *h;
    if fi >= handle.patch_set.files.len() {
        return -1;
    }
    match PatchEngine::apply_difference(&mut handle.patch_set.files[fi], flat_idx) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Unapply a single difference by flat index.
#[no_mangle]
pub unsafe extern "C" fn rcompare_unapply_difference(
    h: *mut PatchSetHandle,
    fi: usize,
    flat_idx: usize,
) -> i32 {
    if h.is_null() {
        return -1;
    }
    let handle = &mut *h;
    if fi >= handle.patch_set.files.len() {
        return -1;
    }
    match PatchEngine::unapply_difference(&mut handle.patch_set.files[fi], flat_idx) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Apply all differences in a FilePatch.
#[no_mangle]
pub unsafe extern "C" fn rcompare_apply_all(
    h: *mut PatchSetHandle,
    fi: usize,
) -> i32 {
    if h.is_null() {
        return -1;
    }
    let handle = &mut *h;
    if fi >= handle.patch_set.files.len() {
        return -1;
    }
    match PatchEngine::apply_all(&mut handle.patch_set.files[fi]) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Unapply all differences in a FilePatch.
#[no_mangle]
pub unsafe extern "C" fn rcompare_unapply_all(
    h: *mut PatchSetHandle,
    fi: usize,
) -> i32 {
    if h.is_null() {
        return -1;
    }
    let handle = &mut *h;
    if fi >= handle.patch_set.files.len() {
        return -1;
    }
    match PatchEngine::unapply_all(&mut handle.patch_set.files[fi]) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

// ===== Serialization =====

/// Serialize the PatchSet to unified diff text.
/// Returns a newly allocated C string (caller must free with `rcompare_free_string`).
#[no_mangle]
pub unsafe extern "C" fn rcompare_serialize_diff(
    h: *const PatchSetHandle,
) -> *mut c_char {
    if h.is_null() {
        return ptr::null_mut();
    }
    let text = PatchSerializer::serialize(&(*h).patch_set);
    match CString::new(text) {
        Ok(cs) => cs.into_raw(),
        Err(_) => ptr::null_mut(),
    }
}

// ===== Helpers =====

unsafe fn get_hunk<'a>(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
) -> Option<&'a rcompare_common::Hunk> {
    if h.is_null() {
        return None;
    }
    (&(*h).patch_set.files).get(fi)?.hunks.get(hi)
}

unsafe fn get_diff<'a>(
    h: *const PatchSetHandle,
    fi: usize,
    hi: usize,
    di: usize,
) -> Option<&'a rcompare_common::PatchDifference> {
    get_hunk(h, fi, hi)?.differences.get(di)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Sample unified diff for testing
    const SAMPLE_DIFF: &str = r#"--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
 line1
-line2
+line2_modified
 line3
"#;

    const MULTI_FILE_DIFF: &str = r#"--- a/file1.txt
+++ b/file1.txt
@@ -1,2 +1,2 @@
-old line
+new line
 unchanged
--- a/file2.txt
+++ b/file2.txt
@@ -1,1 +1,2 @@
 existing
+added line
"#;

    // ===== Lifecycle Tests =====

    #[test]
    fn test_parse_valid_diff_and_free() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            let result = rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            assert_eq!(result, 0, "Parse should succeed");
            assert!(!handle.is_null(), "Handle should not be null");

            // Verify basic properties
            assert_eq!(rcompare_patchset_file_count(handle), 1);

            // Free the handle
            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_parse_null_input() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            let result = rcompare_parse_diff(ptr::null(), 0, &mut handle as *mut _);
            assert_eq!(result, -1, "Should return error for null input");
        }
    }

    #[test]
    fn test_parse_null_output() {
        unsafe {
            let result = rcompare_parse_diff(SAMPLE_DIFF.as_ptr(), SAMPLE_DIFF.len(), ptr::null_mut());
            assert_eq!(result, -1, "Should return error for null output pointer");
        }
    }

    #[test]
    fn test_parse_invalid_utf8() {
        unsafe {
            let invalid_bytes: &[u8] = &[0xFF, 0xFE, 0xFD];
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            let result = rcompare_parse_diff(
                invalid_bytes.as_ptr(),
                invalid_bytes.len(),
                &mut handle as *mut _,
            );
            assert_eq!(result, -1, "Should return error for invalid UTF-8");
        }
    }

    #[test]
    fn test_parse_malformed_diff() {
        unsafe {
            // The parser is lenient - empty/random text just produces empty patchset
            // Test with truly malformed diff structure (incomplete header)
            let malformed = "--- a/file.txt\n+++ b/file.txt\n@@ invalid hunk header";
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            let result = rcompare_parse_diff(
                malformed.as_ptr(),
                malformed.len(),
                &mut handle as *mut _,
            );
            // Parser may be lenient and return empty patchset (success)
            // or may fail - both are acceptable behaviors
            if result == 0 {
                assert!(!handle.is_null());
                rcompare_free_patchset(handle);
            }
        }
    }

    #[test]
    fn test_free_null_handle() {
        unsafe {
            // Should not crash
            rcompare_free_patchset(ptr::null_mut());
        }
    }

    #[test]
    fn test_free_string_null() {
        unsafe {
            // Should not crash
            rcompare_free_string(ptr::null_mut());
        }
    }

    // ===== PatchSet Accessor Tests =====

    #[test]
    fn test_patchset_accessors() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            assert_eq!(rcompare_patchset_file_count(handle), 1);
            assert_ne!(rcompare_patchset_format(handle), DiffFormat::Unknown as u32);
            assert_ne!(rcompare_patchset_generator(handle), DiffGenerator::Unknown as u32);

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_patchset_accessors_null_handle() {
        unsafe {
            assert_eq!(rcompare_patchset_file_count(ptr::null()), 0);
            assert_eq!(rcompare_patchset_format(ptr::null()), DiffFormat::Unknown as u32);
            assert_eq!(rcompare_patchset_generator(ptr::null()), DiffGenerator::Unknown as u32);
        }
    }

    #[test]
    fn test_multi_file_patchset() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                MULTI_FILE_DIFF.as_ptr(),
                MULTI_FILE_DIFF.len(),
                &mut handle as *mut _,
            );

            assert_eq!(rcompare_patchset_file_count(handle), 2);

            rcompare_free_patchset(handle);
        }
    }

    // ===== FilePatch Accessor Tests =====

    #[test]
    fn test_filepatch_string_accessors() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Test source/destination paths
            let source = rcompare_filepatch_source(handle, 0);
            assert!(!source.is_null(), "Source path should not be null");
            let source_str = std::ffi::CStr::from_ptr(source).to_str().unwrap();
            assert!(source_str.contains("test.txt"));

            let dest = rcompare_filepatch_destination(handle, 0);
            assert!(!dest.is_null(), "Destination path should not be null");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_filepatch_string_accessors_invalid_index() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Test out-of-bounds index
            let source = rcompare_filepatch_source(handle, 999);
            assert!(source.is_null(), "Should return null for invalid index");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_filepatch_hunk_count() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            assert_eq!(rcompare_filepatch_hunk_count(handle, 0), 1);
            assert_eq!(rcompare_filepatch_hunk_count(handle, 999), 0);

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_filepatch_is_blended() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Initially not blended
            assert_eq!(rcompare_filepatch_is_blended(handle, 0), 0);

            // Invalid index returns 0
            assert_eq!(rcompare_filepatch_is_blended(handle, 999), 0);

            rcompare_free_patchset(handle);
        }
    }

    // ===== Hunk Accessor Tests =====

    #[test]
    fn test_hunk_accessors() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Test hunk properties
            let source_start = rcompare_hunk_source_start(handle, 0, 0);
            let source_count = rcompare_hunk_source_count(handle, 0, 0);
            let dest_start = rcompare_hunk_dest_start(handle, 0, 0);
            let dest_count = rcompare_hunk_dest_count(handle, 0, 0);

            assert!(source_start > 0, "Source start should be positive");
            assert!(source_count > 0, "Source count should be positive");
            assert!(dest_start > 0, "Dest start should be positive");
            assert!(dest_count > 0, "Dest count should be positive");

            let diff_count = rcompare_hunk_diff_count(handle, 0, 0);
            assert!(diff_count > 0, "Should have differences");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_hunk_accessors_invalid_indices() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Invalid file index
            assert_eq!(rcompare_hunk_source_start(handle, 999, 0), 0);
            // Invalid hunk index
            assert_eq!(rcompare_hunk_source_start(handle, 0, 999), 0);

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_hunk_function_name() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let _func_name = rcompare_hunk_function_name(handle, 0, 0);
            // For simple diffs, function name may be null
            // Just verify it doesn't crash

            // Invalid indices should return null
            assert!(rcompare_hunk_function_name(handle, 999, 0).is_null());

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_hunk_type() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let hunk_type = rcompare_hunk_type(handle, 0, 0);
            // 0 = Normal, 1 = AddedByBlend
            assert!(hunk_type <= 1);

            rcompare_free_patchset(handle);
        }
    }

    // ===== Difference Accessor Tests =====

    #[test]
    fn test_diff_accessors() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let diff_count = rcompare_hunk_diff_count(handle, 0, 0);
            assert!(diff_count > 0);

            // Test first difference
            let diff_type = rcompare_diff_type(handle, 0, 0, 0);
            assert!(diff_type <= 2, "Diff type should be 0=Unchanged, 1=Insert, 2=Delete");

            let _source_line_no = rcompare_diff_source_line_no(handle, 0, 0, 0);
            let _dest_line_no = rcompare_diff_dest_line_no(handle, 0, 0, 0);
            // Line numbers are usize, no need to check >= 0

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_diff_line_accessors() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let source_line_count = rcompare_diff_source_line_count(handle, 0, 0, 0);
            let dest_line_count = rcompare_diff_dest_line_count(handle, 0, 0, 0);

            // If source lines exist, test accessor
            if source_line_count > 0 {
                let line = rcompare_diff_source_line_at(handle, 0, 0, 0, 0);
                assert!(!line.is_null(), "Line should not be null");
            }

            // If dest lines exist, test accessor
            if dest_line_count > 0 {
                let line = rcompare_diff_dest_line_at(handle, 0, 0, 0, 0);
                assert!(!line.is_null(), "Line should not be null");
            }

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_diff_applied_and_conflict_flags() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let applied = rcompare_diff_applied(handle, 0, 0, 0);
            let conflict = rcompare_diff_conflict(handle, 0, 0, 0);

            // Should be 0 or 1 (boolean flags)
            assert!(applied == 0 || applied == 1);
            assert!(conflict == 0 || conflict == 1);

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_diff_accessors_invalid_indices() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Invalid indices should return safe defaults
            assert_eq!(rcompare_diff_type(handle, 999, 0, 0), 0);
            assert_eq!(rcompare_diff_source_line_no(handle, 0, 999, 0), 0);
            assert_eq!(rcompare_diff_dest_line_no(handle, 0, 0, 999), 0);
            assert!(rcompare_diff_source_line_at(handle, 0, 0, 0, 999).is_null());

            rcompare_free_patchset(handle);
        }
    }

    // ===== Engine Integration Tests =====

    #[test]
    fn test_blend_file() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let original_content = "line1\nline2\nline3\n";
            let result = rcompare_blend_file(
                handle,
                0,
                original_content.as_ptr(),
                original_content.len(),
            );

            assert_eq!(result, 0, "Blend should succeed");
            assert_eq!(rcompare_filepatch_is_blended(handle, 0), 1, "Should be marked as blended");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_blend_file_null_handle() {
        unsafe {
            let content = "test";
            let result = rcompare_blend_file(ptr::null_mut(), 0, content.as_ptr(), content.len());
            assert_eq!(result, -1, "Should return error for null handle");
        }
    }

    #[test]
    fn test_blend_file_null_content() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let result = rcompare_blend_file(handle, 0, ptr::null(), 0);
            assert_eq!(result, -1, "Should return error for null content");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_blend_file_invalid_index() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let content = "test";
            let result = rcompare_blend_file(handle, 999, content.as_ptr(), content.len());
            assert_eq!(result, -1, "Should return error for invalid file index");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_apply_difference() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Blend first
            let original = "line1\nline2\nline3\n";
            rcompare_blend_file(handle, 0, original.as_ptr(), original.len());

            // Apply a difference (flat index 0)
            let result = rcompare_apply_difference(handle, 0, 0);
            assert_eq!(result, 0, "Apply should succeed");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_unapply_difference() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let original = "line1\nline2\nline3\n";
            rcompare_blend_file(handle, 0, original.as_ptr(), original.len());

            // Apply then unapply
            rcompare_apply_difference(handle, 0, 0);
            let result = rcompare_unapply_difference(handle, 0, 0);
            assert_eq!(result, 0, "Unapply should succeed");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_apply_all() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let original = "line1\nline2\nline3\n";
            rcompare_blend_file(handle, 0, original.as_ptr(), original.len());

            let result = rcompare_apply_all(handle, 0);
            assert_eq!(result, 0, "Apply all should succeed");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_unapply_all() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let original = "line1\nline2\nline3\n";
            rcompare_blend_file(handle, 0, original.as_ptr(), original.len());
            rcompare_apply_all(handle, 0);

            let result = rcompare_unapply_all(handle, 0);
            assert_eq!(result, 0, "Unapply all should succeed");

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_engine_operations_null_handle() {
        unsafe {
            assert_eq!(rcompare_apply_difference(ptr::null_mut(), 0, 0), -1);
            assert_eq!(rcompare_unapply_difference(ptr::null_mut(), 0, 0), -1);
            assert_eq!(rcompare_apply_all(ptr::null_mut(), 0), -1);
            assert_eq!(rcompare_unapply_all(ptr::null_mut(), 0), -1);
        }
    }

    #[test]
    fn test_engine_operations_invalid_index() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            assert_eq!(rcompare_apply_difference(handle, 999, 0), -1);
            assert_eq!(rcompare_unapply_difference(handle, 999, 0), -1);
            assert_eq!(rcompare_apply_all(handle, 999), -1);
            assert_eq!(rcompare_unapply_all(handle, 999), -1);

            rcompare_free_patchset(handle);
        }
    }

    // ===== Serialization Tests =====

    #[test]
    fn test_serialize_diff() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            let serialized = rcompare_serialize_diff(handle);
            assert!(!serialized.is_null(), "Serialization should succeed");

            // Verify it's valid UTF-8 and contains expected content
            let result_str = std::ffi::CStr::from_ptr(serialized).to_str().unwrap();
            assert!(result_str.contains("test.txt"), "Should contain filename");

            // Free the serialized string
            rcompare_free_string(serialized);
            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_serialize_diff_null_handle() {
        unsafe {
            let result = rcompare_serialize_diff(ptr::null());
            assert!(result.is_null(), "Should return null for null handle");
        }
    }

    #[test]
    fn test_round_trip_parse_serialize() {
        unsafe {
            // Parse original
            let mut handle1: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle1 as *mut _,
            );

            // Serialize
            let serialized = rcompare_serialize_diff(handle1);
            assert!(!serialized.is_null());

            // Parse serialized version
            let serialized_cstr = std::ffi::CStr::from_ptr(serialized);
            let serialized_bytes = serialized_cstr.to_bytes();
            let mut handle2: *mut PatchSetHandle = ptr::null_mut();
            let result = rcompare_parse_diff(
                serialized_bytes.as_ptr(),
                serialized_bytes.len(),
                &mut handle2 as *mut _,
            );

            assert_eq!(result, 0, "Round-trip parse should succeed");
            assert_eq!(
                rcompare_patchset_file_count(handle1),
                rcompare_patchset_file_count(handle2),
                "File counts should match"
            );

            // Cleanup
            rcompare_free_string(serialized);
            rcompare_free_patchset(handle1);
            rcompare_free_patchset(handle2);
        }
    }

    // ===== String Cache Lifetime Tests =====

    #[test]
    fn test_string_cache_lifetime() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Get multiple string pointers
            let source1 = rcompare_filepatch_source(handle, 0);
            let source2 = rcompare_filepatch_source(handle, 0);

            // Both should be valid and point to valid strings
            assert!(!source1.is_null());
            assert!(!source2.is_null());

            let str1 = std::ffi::CStr::from_ptr(source1).to_str().unwrap();
            let str2 = std::ffi::CStr::from_ptr(source2).to_str().unwrap();

            // Strings should be equal (though pointers may differ due to caching)
            assert_eq!(str1, str2);

            rcompare_free_patchset(handle);
        }
    }

    #[test]
    fn test_multiple_string_accesses() {
        unsafe {
            let mut handle: *mut PatchSetHandle = ptr::null_mut();
            rcompare_parse_diff(
                SAMPLE_DIFF.as_ptr(),
                SAMPLE_DIFF.len(),
                &mut handle as *mut _,
            );

            // Access multiple strings to grow the cache
            let _source = rcompare_filepatch_source(handle, 0);
            let _dest = rcompare_filepatch_destination(handle, 0);
            let _timestamp = rcompare_filepatch_source_timestamp(handle, 0);
            let _revision = rcompare_filepatch_source_revision(handle, 0);

            // All accesses should succeed without issues
            // Free should clean up all cached strings
            rcompare_free_patchset(handle);
        }
    }
}
