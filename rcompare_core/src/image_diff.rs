use image::{DynamicImage, GenericImageView, Rgba, RgbaImage};
use rcompare_common::RCompareError;
use std::path::Path;

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
}

impl ImageDiffEngine {
    pub fn new() -> Self {
        Self {
            mode: ImageCompareMode::default(),
        }
    }

    pub fn with_mode(mut self, mode: ImageCompareMode) -> Self {
        self.mode = mode;
        self
    }

    /// Compare two image files
    pub fn compare_files(&self, left: &Path, right: &Path) -> Result<ImageDiffResult, RCompareError> {
        let left_img = image::open(left)
            .map_err(|e| RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open left image: {}", e)
            )))?;

        let right_img = image::open(right)
            .map_err(|e| RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to open right image: {}", e)
            )))?;

        self.compare_images(&left_img, &right_img)
    }

    /// Compare two images
    pub fn compare_images(&self, left: &DynamicImage, right: &DynamicImage) -> Result<ImageDiffResult, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();
        let same_dimensions = left_dims == right_dims;

        if !same_dimensions {
            // Images have different dimensions - consider fully different
            let total = (left_dims.0 as u64 * left_dims.1 as u64).max(right_dims.0 as u64 * right_dims.1 as u64);
            return Ok(ImageDiffResult {
                total_pixels: total,
                different_pixels: total,
                difference_percentage: 100.0,
                mean_diff: 255.0,
                same_dimensions: false,
                left_dimensions: left_dims,
                right_dimensions: right_dims,
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
        })
    }

    /// Create a difference visualization image
    pub fn create_diff_image(&self, left: &DynamicImage, right: &DynamicImage) -> Result<RgbaImage, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();

        if left_dims != right_dims {
            return Err(RCompareError::Comparison(
                "Cannot create diff image for images with different dimensions".to_string()
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
                    let gray = ((left_pixel[0] as u16 + left_pixel[1] as u16 + left_pixel[2] as u16) / 3) as u8;
                    Rgba([gray, gray, gray, 255])
                };

                diff_image.put_pixel(x, y, diff_pixel);
            }
        }

        Ok(diff_image)
    }

    /// Create a side-by-side comparison image
    pub fn create_side_by_side(&self, left: &DynamicImage, right: &DynamicImage) -> Result<RgbaImage, RCompareError> {
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
    pub fn create_overlay(&self, left: &DynamicImage, right: &DynamicImage, blend: f32) -> Result<RgbaImage, RCompareError> {
        let left_dims = left.dimensions();
        let right_dims = right.dimensions();

        if left_dims != right_dims {
            return Err(RCompareError::Comparison(
                "Cannot create overlay for images with different dimensions".to_string()
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
                left[0] != right[0] || left[1] != right[1] || left[2] != right[2] || left[3] != right[3]
            }
            ImageCompareMode::Threshold(thresh) => {
                self.channel_diff(left[0], right[0]) > thresh ||
                self.channel_diff(left[1], right[1]) > thresh ||
                self.channel_diff(left[2], right[2]) > thresh ||
                self.channel_diff(left[3], right[3]) > thresh
            }
            ImageCompareMode::Perceptual => {
                // Simple perceptual difference using weighted RGB
                let left_luma = 0.299 * left[0] as f32 + 0.587 * left[1] as f32 + 0.114 * left[2] as f32;
                let right_luma = 0.299 * right[0] as f32 + 0.587 * right[1] as f32 + 0.114 * right[2] as f32;
                (left_luma - right_luma).abs() > 3.0
            }
        }
    }

    fn channel_diff(&self, a: u8, b: u8) -> u8 {
        if a > b { a - b } else { b - a }
    }

    fn pixel_difference(&self, left: &Rgba<u8>, right: &Rgba<u8>) -> u32 {
        self.channel_diff(left[0], right[0]) as u32 +
        self.channel_diff(left[1], right[1]) as u32 +
        self.channel_diff(left[2], right[2]) as u32 +
        self.channel_diff(left[3], right[3]) as u32
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
        matches!(ext.as_str(),
            "png" | "jpg" | "jpeg" | "gif" | "bmp" | "ico" | "tiff" | "tif" |
            "webp" | "pnm" | "pbm" | "pgm" | "ppm" | "dds" | "tga" | "ff"
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
}
