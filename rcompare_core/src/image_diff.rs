use exif as kamadak_exif;
use image::{DynamicImage, GenericImageView, Rgba, RgbaImage};
use rcompare_common::RCompareError;
use std::collections::HashMap;
use std::path::Path;

/// EXIF metadata for an image
#[derive(Debug, Clone, Default)]
pub struct ExifMetadata {
    pub make: Option<String>,
    pub model: Option<String>,
    pub datetime: Option<String>,
    pub exposure_time: Option<String>,
    pub f_number: Option<String>,
    pub iso: Option<String>,
    pub focal_length: Option<String>,
    pub gps_latitude: Option<String>,
    pub gps_longitude: Option<String>,
    pub orientation: Option<String>,
    pub software: Option<String>,
    pub other_tags: HashMap<String, String>,
}

/// Difference in EXIF metadata between two images
#[derive(Debug, Clone)]
pub struct ExifDifference {
    pub tag_name: String,
    pub left_value: Option<String>,
    pub right_value: Option<String>,
}

/// Result of an image comparison
#[derive(Debug, Clone)]
pub struct ImageDiffResult {
    /// Total number of pixels
    pub total_pixels: u64,
    /// Number of different pixels
    pub different_pixels: u64,
    /// Percentage of pixels that are different (0.0 - 100.0)
    pub difference_percentage: f64,
    /// Mean absolute difference per channel (0-255)
    pub mean_diff: f64,
    /// Whether images have same dimensions
    pub same_dimensions: bool,
    /// Left image dimensions
    pub left_dimensions: (u32, u32),
    /// Right image dimensions
    pub right_dimensions: (u32, u32),
    /// EXIF metadata from left image
    pub left_exif: Option<ExifMetadata>,
    /// EXIF metadata from right image
    pub right_exif: Option<ExifMetadata>,
    /// Differences in EXIF metadata
    pub exif_differences: Vec<ExifDifference>,
}

/// Comparison mode for images
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImageCompareMode {
    /// Count pixels that differ by any amount
    Exact,
    /// Count pixels that differ by more than a threshold
    Threshold(u8),
    /// Compare perceptual similarity
    Perceptual,
}

impl Default for ImageCompareMode {
    fn default() -> Self {
        Self::Threshold(1)
    }
}

/// Engine for comparing images
pub struct ImageDiffEngine {
    mode: ImageCompareMode,
    /// Compare EXIF metadata if available
    compare_exif: bool,
    /// Pixel difference tolerance (0-255)
    tolerance: u8,
}

impl ImageDiffEngine {
    pub fn new() -> Self {
        Self {
            mode: ImageCompareMode::default(),
            compare_exif: false,
            tolerance: 1,
        }
    }

    pub fn with_mode(mut self, mode: ImageCompareMode) -> Self {
        self.mode = mode;
        self
    }

    pub fn with_exif_compare(mut self, enabled: bool) -> Self {
        self.compare_exif = enabled;
        self
    }

    pub fn with_tolerance(mut self, tolerance: u8) -> Self {
        self.tolerance = tolerance;
        self
    }

    pub fn set_tolerance(&mut self, tolerance: u8) {
        self.tolerance = tolerance;
    }

    pub fn tolerance(&self) -> u8 {
        self.tolerance
    }

    /// Extract EXIF metadata from an image file
    fn extract_exif(&self, path: &Path) -> Option<ExifMetadata> {
        if !self.compare_exif {
            return None;
        }

        let file = std::fs::File::open(path).ok()?;
        let mut bufreader = std::io::BufReader::new(file);
        let exifreader = kamadak_exif::Reader::new();
        let exif_data = exifreader.read_from_container(&mut bufreader).ok()?;

        let mut metadata = ExifMetadata::default();

        // Extract common EXIF tags
        if let Some(field) = exif_data.get_field(kamadak_exif::Tag::Make, kamadak_exif::In::PRIMARY)
        {
            metadata.make = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::Model, kamadak_exif::In::PRIMARY)
        {
            metadata.model = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::DateTime, kamadak_exif::In::PRIMARY)
        {
            metadata.datetime = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::ExposureTime, kamadak_exif::In::PRIMARY)
        {
            metadata.exposure_time = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::FNumber, kamadak_exif::In::PRIMARY)
        {
            metadata.f_number = Some(field.display_value().to_string());
        }
        if let Some(field) = exif_data.get_field(
            kamadak_exif::Tag::PhotographicSensitivity,
            kamadak_exif::In::PRIMARY,
        ) {
            metadata.iso = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::FocalLength, kamadak_exif::In::PRIMARY)
        {
            metadata.focal_length = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::GPSLatitude, kamadak_exif::In::PRIMARY)
        {
            metadata.gps_latitude = Some(field.display_value().to_string());
        }
        if let Some(field) =
            exif_data.get_field(kamadak_exif::Tag::GPSLongitude, kamadak_exif::In::PRIMARY)
        {
            metadata.gps_longitude = Some(field.display_value().to_string());
        }
        if let Some(orient_field) =
            exif_data.get_field(kamadak_exif::Tag::Orientation, kamadak_exif::In::PRIMARY)
        {
            metadata.orientation = Some(orient_field.display_value().to_string());
        }
        if let Some(sw_field) =
            exif_data.get_field(kamadak_exif::Tag::Software, kamadak_exif::In::PRIMARY)
        {
            metadata.software = Some(sw_field.display_value().to_string());
        }

        // Store other tags
        for field in exif_data.fields() {
            let tag_name = format!("{:?}", field.tag);
            let tag_value = field.display_value().to_string();
            metadata.other_tags.entry(tag_name).or_insert(tag_value);
        }

        Some(metadata)
    }

    /// Compare EXIF metadata between two images
    fn compare_exif_metadata(
        &self,
        left: &Option<ExifMetadata>,
        right: &Option<ExifMetadata>,
    ) -> Vec<ExifDifference> {
        let mut differences = Vec::new();

        match (left, right) {
            (Some(l), Some(r)) => {
                // Compare common fields
                if l.make != r.make {
                    differences.push(ExifDifference {
                        tag_name: "Make".to_string(),
                        left_value: l.make.clone(),
                        right_value: r.make.clone(),
                    });
                }
                if l.model != r.model {
                    differences.push(ExifDifference {
                        tag_name: "Model".to_string(),
                        left_value: l.model.clone(),
                        right_value: r.model.clone(),
                    });
                }
                if l.datetime != r.datetime {
                    differences.push(ExifDifference {
                        tag_name: "DateTime".to_string(),
                        left_value: l.datetime.clone(),
                        right_value: r.datetime.clone(),
                    });
                }
                if l.exposure_time != r.exposure_time {
                    differences.push(ExifDifference {
                        tag_name: "ExposureTime".to_string(),
                        left_value: l.exposure_time.clone(),
                        right_value: r.exposure_time.clone(),
                    });
                }
                if l.f_number != r.f_number {
                    differences.push(ExifDifference {
                        tag_name: "FNumber".to_string(),
                        left_value: l.f_number.clone(),
                        right_value: r.f_number.clone(),
                    });
                }
                if l.iso != r.iso {
                    differences.push(ExifDifference {
                        tag_name: "ISO".to_string(),
                        left_value: l.iso.clone(),
                        right_value: r.iso.clone(),
                    });
                }
                if l.focal_length != r.focal_length {
                    differences.push(ExifDifference {
                        tag_name: "FocalLength".to_string(),
                        left_value: l.focal_length.clone(),
                        right_value: r.focal_length.clone(),
                    });
                }
                if l.gps_latitude != r.gps_latitude {
                    differences.push(ExifDifference {
                        tag_name: "GPSLatitude".to_string(),
                        left_value: l.gps_latitude.clone(),
                        right_value: r.gps_latitude.clone(),
                    });
                }
                if l.gps_longitude != r.gps_longitude {
                    differences.push(ExifDifference {
                        tag_name: "GPSLongitude".to_string(),
                        left_value: l.gps_longitude.clone(),
                        right_value: r.gps_longitude.clone(),
                    });
                }
                if l.orientation != r.orientation {
                    differences.push(ExifDifference {
                        tag_name: "Orientation".to_string(),
                        left_value: l.orientation.clone(),
                        right_value: r.orientation.clone(),
                    });
                }
                if l.software != r.software {
                    differences.push(ExifDifference {
                        tag_name: "Software".to_string(),
                        left_value: l.software.clone(),
                        right_value: r.software.clone(),
                    });
                }
            }
            (Some(_), None) => {
                differences.push(ExifDifference {
                    tag_name: "EXIF Data".to_string(),
                    left_value: Some("Present".to_string()),
                    right_value: None,
                });
            }
            (None, Some(_)) => {
                differences.push(ExifDifference {
                    tag_name: "EXIF Data".to_string(),
                    left_value: None,
                    right_value: Some("Present".to_string()),
                });
            }
            (None, None) => {}
        }

        differences
    }

    /// Compare two image files
    pub fn compare_files(
        &self,
        left: &Path,
        right: &Path,
    ) -> Result<ImageDiffResult, RCompareError> {
        // Extract EXIF metadata if enabled
        let left_exif = self.extract_exif(left);
        let right_exif = self.extract_exif(right);

        let left_img = image::open(left).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open left image: {}", e),
            ))
        })?;

        let right_img = image::open(right).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open right image: {}", e),
            ))
        })?;

        self.compare_images_with_exif(&left_img, &right_img, left_exif, right_exif)
    }

    /// Compare two images (without EXIF)
    pub fn compare_images(
        &self,
        left: &DynamicImage,
        right: &DynamicImage,
    ) -> Result<ImageDiffResult, RCompareError> {
        self.compare_images_with_exif(left, right, None, None)
    }

    /// Compare two images with EXIF metadata
    pub fn compare_images_with_exif(
        &self,
        left: &DynamicImage,
        right: &DynamicImage,
        left_exif: Option<ExifMetadata>,
        right_exif: Option<ExifMetadata>,
    ) -> Result<ImageDiffResult, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();
        let same_dimensions = left_dims == right_dims;

        let exif_differences = self.compare_exif_metadata(&left_exif, &right_exif);

        if !same_dimensions {
            // Images have different dimensions - consider fully different
            let total = (left_dims.0 as u64 * left_dims.1 as u64)
                .max(right_dims.0 as u64 * right_dims.1 as u64);
            return Ok(ImageDiffResult {
                total_pixels: total,
                different_pixels: total,
                difference_percentage: 100.0,
                mean_diff: 255.0,
                same_dimensions: false,
                left_dimensions: left_dims,
                right_dimensions: right_dims,
                left_exif,
                right_exif,
                exif_differences,
            });
        }

        let left_rgba = left.to_rgba8();
        let right_rgba = right.to_rgba8();

        let (width, height) = left_dims;
        let total_pixels = (width as u64) * (height as u64);
        let mut different_pixels = 0u64;
        let mut total_diff = 0u64;

        for y in 0..height {
            for x in 0..width {
                let left_pixel = left_rgba.get_pixel(x, y);
                let right_pixel = right_rgba.get_pixel(x, y);

                if self.pixels_differ(left_pixel, right_pixel) {
                    different_pixels += 1;
                }

                // Calculate per-channel difference for mean
                let diff = self.pixel_difference(left_pixel, right_pixel);
                total_diff += diff as u64;
            }
        }

        let difference_percentage = (different_pixels as f64 / total_pixels as f64) * 100.0;
        let mean_diff = total_diff as f64 / (total_pixels as f64 * 4.0); // 4 channels

        Ok(ImageDiffResult {
            total_pixels,
            different_pixels,
            difference_percentage,
            mean_diff,
            same_dimensions: true,
            left_dimensions: left_dims,
            right_dimensions: right_dims,
            left_exif,
            right_exif,
            exif_differences,
        })
    }

    /// Create a difference visualization image
    pub fn create_diff_image(
        &self,
        left: &DynamicImage,
        right: &DynamicImage,
    ) -> Result<RgbaImage, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();

        if left_dims != right_dims {
            return Err(RCompareError::Comparison(
                "Cannot create diff image for images with different dimensions".to_string(),
            ));
        }

        let left_rgba = left.to_rgba8();
        let right_rgba = right.to_rgba8();

        let (width, height) = left_dims;
        let mut diff_image = RgbaImage::new(width, height);

        for y in 0..height {
            for x in 0..width {
                let left_pixel = left_rgba.get_pixel(x, y);
                let right_pixel = right_rgba.get_pixel(x, y);

                let diff_pixel = if self.pixels_differ(left_pixel, right_pixel) {
                    // Highlight difference in red
                    Rgba([255, 0, 0, 255])
                } else {
                    // Show original pixel (grayscale)
                    let gray =
                        ((left_pixel[0] as u16 + left_pixel[1] as u16 + left_pixel[2] as u16) / 3)
                            as u8;
                    Rgba([gray, gray, gray, 255])
                };

                diff_image.put_pixel(x, y, diff_pixel);
            }
        }

        Ok(diff_image)
    }

    /// Create a side-by-side comparison image
    pub fn create_side_by_side(
        &self,
        left: &DynamicImage,
        right: &DynamicImage,
    ) -> Result<RgbaImage, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();

        let left_rgba = left.to_rgba8();
        let right_rgba = right.to_rgba8();

        // Create combined image
        let total_width = left_dims.0 + right_dims.0 + 4; // 4px gap
        let max_height = left_dims.1.max(right_dims.1);

        let mut combined = RgbaImage::new(total_width, max_height);

        // Fill with background
        for pixel in combined.pixels_mut() {
            *pixel = Rgba([128, 128, 128, 255]);
        }

        // Copy left image
        for y in 0..left_dims.1 {
            for x in 0..left_dims.0 {
                combined.put_pixel(x, y, *left_rgba.get_pixel(x, y));
            }
        }

        // Copy right image
        let offset_x = left_dims.0 + 4;
        for y in 0..right_dims.1 {
            for x in 0..right_dims.0 {
                combined.put_pixel(offset_x + x, y, *right_rgba.get_pixel(x, y));
            }
        }

        Ok(combined)
    }

    /// Create an overlay blend of two images
    pub fn create_overlay(
        &self,
        left: &DynamicImage,
        right: &DynamicImage,
        blend: f32,
    ) -> Result<RgbaImage, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();

        if left_dims != right_dims {
            return Err(RCompareError::Comparison(
                "Cannot create overlay for images with different dimensions".to_string(),
            ));
        }

        let left_rgba = left.to_rgba8();
        let right_rgba = right.to_rgba8();

        let (width, height) = left_dims;
        let mut overlay = RgbaImage::new(width, height);
        let blend = blend.clamp(0.0, 1.0);
        let left_weight = 1.0 - blend;

        for y in 0..height {
            for x in 0..width {
                let left_pixel = left_rgba.get_pixel(x, y);
                let right_pixel = right_rgba.get_pixel(x, y);

                let r = (left_pixel[0] as f32 * left_weight + right_pixel[0] as f32 * blend) as u8;
                let g = (left_pixel[1] as f32 * left_weight + right_pixel[1] as f32 * blend) as u8;
                let b = (left_pixel[2] as f32 * left_weight + right_pixel[2] as f32 * blend) as u8;
                let a = (left_pixel[3] as f32 * left_weight + right_pixel[3] as f32 * blend) as u8;

                overlay.put_pixel(x, y, Rgba([r, g, b, a]));
            }
        }

        Ok(overlay)
    }

    fn pixels_differ(&self, left: &Rgba<u8>, right: &Rgba<u8>) -> bool {
        match self.mode {
            ImageCompareMode::Exact => {
                // Use tolerance even in exact mode (tolerance of 0 means truly exact)
                self.channel_diff(left[0], right[0]) > self.tolerance
                    || self.channel_diff(left[1], right[1]) > self.tolerance
                    || self.channel_diff(left[2], right[2]) > self.tolerance
                    || self.channel_diff(left[3], right[3]) > self.tolerance
            }
            ImageCompareMode::Threshold(thresh) => {
                // Use the maximum of mode threshold and tolerance setting
                let effective_threshold = thresh.max(self.tolerance);
                self.channel_diff(left[0], right[0]) > effective_threshold
                    || self.channel_diff(left[1], right[1]) > effective_threshold
                    || self.channel_diff(left[2], right[2]) > effective_threshold
                    || self.channel_diff(left[3], right[3]) > effective_threshold
            }
            ImageCompareMode::Perceptual => {
                // Simple perceptual difference using weighted RGB
                // Use tolerance to adjust sensitivity (default 1 = ~3.0 threshold)
                let threshold = 3.0 * (self.tolerance as f32);
                let left_luma =
                    0.299 * left[0] as f32 + 0.587 * left[1] as f32 + 0.114 * left[2] as f32;
                let right_luma =
                    0.299 * right[0] as f32 + 0.587 * right[1] as f32 + 0.114 * right[2] as f32;
                (left_luma - right_luma).abs() > threshold
            }
        }
    }

    fn channel_diff(&self, a: u8, b: u8) -> u8 {
        a.abs_diff(b)
    }

    fn pixel_difference(&self, left: &Rgba<u8>, right: &Rgba<u8>) -> u32 {
        self.channel_diff(left[0], right[0]) as u32
            + self.channel_diff(left[1], right[1]) as u32
            + self.channel_diff(left[2], right[2]) as u32
            + self.channel_diff(left[3], right[3]) as u32
    }
}

impl Default for ImageDiffEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a file path appears to be an image based on extension
pub fn is_image_file(path: &Path) -> bool {
    if let Some(ext) = path.extension() {
        let ext = ext.to_string_lossy().to_lowercase();
        matches!(
            ext.as_str(),
            "png"
                | "jpg"
                | "jpeg"
                | "gif"
                | "bmp"
                | "ico"
                | "tiff"
                | "tif"
                | "webp"
                | "pnm"
                | "pbm"
                | "pgm"
                | "ppm"
                | "dds"
                | "tga"
                | "ff"
        )
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgba;

    #[test]
    fn test_identical_images() {
        let engine = ImageDiffEngine::new();

        let mut left = RgbaImage::new(10, 10);
        let mut right = RgbaImage::new(10, 10);

        for pixel in left.pixels_mut() {
            *pixel = Rgba([100, 150, 200, 255]);
        }
        for pixel in right.pixels_mut() {
            *pixel = Rgba([100, 150, 200, 255]);
        }

        let left_dyn = DynamicImage::ImageRgba8(left);
        let right_dyn = DynamicImage::ImageRgba8(right);

        let result = engine.compare_images(&left_dyn, &right_dyn).unwrap();

        assert_eq!(result.different_pixels, 0);
        assert_eq!(result.difference_percentage, 0.0);
    }

    #[test]
    fn test_different_images() {
        let engine = ImageDiffEngine::new();

        let mut left = RgbaImage::new(10, 10);
        let mut right = RgbaImage::new(10, 10);

        for pixel in left.pixels_mut() {
            *pixel = Rgba([100, 150, 200, 255]);
        }
        for pixel in right.pixels_mut() {
            *pixel = Rgba([200, 100, 50, 255]);
        }

        let left_dyn = DynamicImage::ImageRgba8(left);
        let right_dyn = DynamicImage::ImageRgba8(right);

        let result = engine.compare_images(&left_dyn, &right_dyn).unwrap();

        assert_eq!(result.different_pixels, 100);
        assert_eq!(result.difference_percentage, 100.0);
    }

    #[test]
    fn test_different_dimensions() {
        let engine = ImageDiffEngine::new();

        let left = RgbaImage::new(10, 10);
        let right = RgbaImage::new(20, 20);

        let left_dyn = DynamicImage::ImageRgba8(left);
        let right_dyn = DynamicImage::ImageRgba8(right);

        let result = engine.compare_images(&left_dyn, &right_dyn).unwrap();

        assert!(!result.same_dimensions);
        assert_eq!(result.difference_percentage, 100.0);
    }

    #[test]
    fn test_is_image_file() {
        assert!(is_image_file(Path::new("test.png")));
        assert!(is_image_file(Path::new("test.JPG")));
        assert!(is_image_file(Path::new("test.jpeg")));
        assert!(!is_image_file(Path::new("test.txt")));
        assert!(!is_image_file(Path::new("test.rs")));
    }

    #[test]
    fn test_tolerance_adjustment() {
        // Create images with slight differences
        let mut left = RgbaImage::new(10, 10);
        let mut right = RgbaImage::new(10, 10);

        for pixel in left.pixels_mut() {
            *pixel = Rgba([100, 100, 100, 255]);
        }
        for pixel in right.pixels_mut() {
            // Slightly different (difference of 2 per channel)
            *pixel = Rgba([102, 102, 102, 255]);
        }

        let left_dyn = DynamicImage::ImageRgba8(left);
        let right_dyn = DynamicImage::ImageRgba8(right);

        // With tolerance 1 (default), should detect differences
        let engine_low = ImageDiffEngine::new().with_tolerance(1);
        let result_low = engine_low.compare_images(&left_dyn, &right_dyn).unwrap();
        assert_eq!(result_low.different_pixels, 100);

        // With tolerance 3, should not detect differences (diff is 2)
        let engine_high = ImageDiffEngine::new().with_tolerance(3);
        let result_high = engine_high.compare_images(&left_dyn, &right_dyn).unwrap();
        assert_eq!(result_high.different_pixels, 0);
    }

    #[test]
    fn test_exif_comparison() {
        // Create two ExifMetadata instances
        let left_exif = ExifMetadata {
            make: Some("Canon".to_string()),
            model: Some("EOS 5D Mark IV".to_string()),
            iso: Some("400".to_string()),
            ..Default::default()
        };

        let right_exif = ExifMetadata {
            make: Some("Canon".to_string()),
            model: Some("EOS 5D Mark IV".to_string()),
            iso: Some("800".to_string()), // Different ISO
            ..Default::default()
        };

        let engine = ImageDiffEngine::new().with_exif_compare(true);
        let diffs = engine.compare_exif_metadata(&Some(left_exif), &Some(right_exif));

        // Should detect ISO difference
        assert_eq!(diffs.len(), 1);
        assert_eq!(diffs[0].tag_name, "ISO");
        assert_eq!(diffs[0].left_value, Some("400".to_string()));
        assert_eq!(diffs[0].right_value, Some("800".to_string()));
    }

    #[test]
    fn test_exif_missing() {
        let left_exif = ExifMetadata {
            make: Some("Canon".to_string()),
            ..Default::default()
        };

        let engine = ImageDiffEngine::new().with_exif_compare(true);
        let diffs = engine.compare_exif_metadata(&Some(left_exif), &None);

        // Should detect that one image has EXIF and the other doesn't
        assert_eq!(diffs.len(), 1);
        assert_eq!(diffs[0].tag_name, "EXIF Data");
        assert_eq!(diffs[0].left_value, Some("Present".to_string()));
        assert_eq!(diffs[0].right_value, None);
    }
}
