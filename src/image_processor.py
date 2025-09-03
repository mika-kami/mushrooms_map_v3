import os
import re
import shutil
import requests
import easyocr
from PIL import Image
import numpy as np
from datetime import datetime
from typing import Optional
from src.config import (
    IMAGE_URL,
    RAW_DIR,
    PROCESSED_DIR,
    MAX_SAVED_IMAGES,
    HIGH_PROB_RGB,
    VERY_HIGH_PROB_RGB,
    RGB_TOLERANCE,
    HIGHLIGHT_COLOR,
    IMAGE_WEIGHTS,
)
from src.geo_processor import GeoProcessor

# Initialize the EasyOCR reader
print("Initializing EasyOCR Reader...")
reader = easyocr.Reader(["en"])
print("EasyOCR Reader initialized.")

# Initialize the geo processor
geo_processor = GeoProcessor()

# Cropping parameters for processed images
CROP_PARAMS = {
    "left": 173,  # pixels to crop from left
    "right": 173,  # pixels to crop from right
    "top": 282,  # pixels to crop from top
    "bottom": 297  # pixels to crop from bottom
}


def _extract_date_from_filename(filename: str, prefix: str) -> Optional[str]:
    """Extracts 'dd.mm.yyyy' from a filename like 'prefix_dd.mm.yyyy.png'."""
    # Use regex to properly extract the date pattern
    pattern = rf'{re.escape(prefix)}(\d{{2}}\.\d{{2}}\.\d{{4}})\.png$'
    match = re.match(pattern, filename)
    return match.group(1) if match else None


def _parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string in dd.mm.yyyy format to datetime object."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return None


def _scan_date_from_image_easyocr(image: Image.Image) -> Optional[str]:
    """Scans an image for a date pattern."""
    try:
        img_np = np.array(image)
        result = reader.readtext(img_np)
        full_text = " ".join([text for _, text, _ in result])
        match = re.search(r"\b(\d{2})\s*\.\s*(\d{2})\s*\.\s*(\d{4})\b", full_text)
        if match:
            date_str = re.sub(r"\s+", "", match.group(0))
            return date_str
        return None
    except Exception as e:
        print(f"An error occurred during EasyOCR: {e}")
        return None


def crop_processed_image(image_path: str) -> Optional[str]:
    """
    Crop the processed image according to specified parameters.

    Args:
        image_path: Path to the processed image

    Returns:
        Path to the cropped image, or None if cropping failed
    """
    try:
        print(f"Cropping processed image: {image_path}")

        # Load the image
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        print(f"Original image size: {width}x{height}")

        # Calculate crop box (left, upper, right, lower)
        left = CROP_PARAMS["left"]
        top = CROP_PARAMS["top"]
        right = width - CROP_PARAMS["right"]
        bottom = height - CROP_PARAMS["bottom"]

        print(f"Cropping with parameters: left={left}, top={top}, right={right}, bottom={bottom}")

        # Validate crop parameters
        if left >= right or top >= bottom:
            print(f"Invalid crop parameters: would result in zero or negative dimensions")
            return None

        if right > width or bottom > height:
            print(f"Crop parameters exceed image dimensions")
            return None

        # Perform the crop
        cropped_image = image.crop((left, top, right, bottom))
        new_width, new_height = cropped_image.size
        print(f"Cropped image size: {new_width}x{new_height}")

        # Save the cropped image (overwrite original)
        cropped_image.save(image_path, optimize=True)
        print(f"Cropped image saved: {image_path}")

        return image_path

    except Exception as e:
        print(f"Error cropping image: {e}")
        import traceback
        traceback.print_exc()
        return None


def download_image() -> Optional[str]:
    """Downloads and saves the image."""
    try:
        response = requests.get(IMAGE_URL, stream=True)
        response.raise_for_status()
        image = Image.open(response.raw).convert("RGB")

        date_str = _scan_date_from_image_easyocr(image) or datetime.now().strftime(
            "%d.%m.%Y"
        )

        filename = f"image_{date_str}.png"
        filepath = os.path.join(RAW_DIR, filename)

        if os.path.exists(filepath):
            print(f"Raw image for {date_str} already exists. Download ignored.")
            return None

        image.save(filepath)
        print(f"New raw image saved: {filepath}")
        _manage_image_quantity()
        return filepath

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {e}")
        return None


def _manage_image_quantity():
    """Keeps the number of raw images within the limit."""
    images = sorted(
        [os.path.join(RAW_DIR, f) for f in os.listdir(RAW_DIR)], key=os.path.getmtime
    )
    while len(images) > MAX_SAVED_IMAGES:
        os.remove(images.pop(0))


def get_latest_image_path(directory: str) -> Optional[str]:
    """Finds the most recent file in a directory."""
    if not os.path.exists(directory):
        return None
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.png')]
    return max(files, key=os.path.getmtime) if files else None


def _get_color_mask(image: Image.Image, target_rgb: tuple) -> Image.Image:
    """Identifies areas matching a target RGB color and returns a mask."""
    data = np.array(image)
    lower_bound = np.array(target_rgb) * (1 - RGB_TOLERANCE)
    upper_bound = np.array(target_rgb) * (1 + RGB_TOLERANCE)
    in_range = np.all((data >= lower_bound) & (data <= upper_bound), axis=-1)
    return Image.fromarray(in_range.astype(np.uint8) * 255)


def create_comparison_map() -> Optional[str]:
    """
    Generates a processed map ONLY if the latest raw image is newer than
    the existing processed map. Ensures only one processed image is stored.
    Now includes image cropping and generates GeoJSON data for geographic mapping.
    """
    # Get raw files and sort by date in filename (newest first)
    if not os.path.exists(RAW_DIR):
        print("Raw directory doesn't exist")
        return None

    raw_files = [f for f in os.listdir(RAW_DIR) if f.startswith('image_') and f.endswith('.png')]
    if not raw_files:
        print("No raw images available to process.")
        return None

    # Extract dates and sort by actual date (newest first)
    raw_files_with_dates = []
    for filename in raw_files:
        date_str = _extract_date_from_filename(filename, "image_")
        if date_str:
            date_obj = _parse_date_string(date_str)
            if date_obj:
                filepath = os.path.join(RAW_DIR, filename)
                raw_files_with_dates.append((filename, filepath, date_obj, date_str))

    if not raw_files_with_dates:
        print("No valid date files found")
        return None

    # Sort by date (newest first)
    raw_files_sorted = sorted(raw_files_with_dates, key=lambda x: x[2], reverse=True)

    # Get the newest raw file by date
    latest_raw_filename, latest_raw_path, latest_date_obj, latest_raw_date = raw_files_sorted[0]
    print(f"Latest raw file by date: {latest_raw_filename} ({latest_raw_date})")

    print(f"Extracted date from newest raw file: {latest_raw_date}")
    target_processed_filename = f"processed_{latest_raw_date}.png"
    target_processed_filepath = os.path.join(PROCESSED_DIR, target_processed_filename)
    print(f"Target processed filename: {target_processed_filename}")

    # 2. Check if the up-to-date processed file already exists
    if os.path.exists(target_processed_filepath):
        print(f"Processed map for {latest_raw_date} already exists. Checking if cropping needed...")

        # Check if the image needs cropping (check if it has the original dimensions)
        test_image = Image.open(target_processed_filepath)
        test_width, test_height = test_image.size
        test_image.close()

        # If image is larger than expected after cropping, crop it
        expected_width = test_width - CROP_PARAMS["left"] - CROP_PARAMS["right"]
        expected_height = test_height - CROP_PARAMS["top"] - CROP_PARAMS["bottom"]

        # If dimensions suggest uncropped image, crop it
        if test_width > expected_width or test_height > expected_height:
            print("Image appears uncropped, applying crop...")
            crop_processed_image(target_processed_filepath)

        # Always try to generate GeoJSON with the CORRECT date
        _generate_geojson_with_correct_date(target_processed_filepath, latest_raw_date)
        return target_processed_filepath

    # 3. Process images - use the date-sorted order for consistency
    print(f"Generating new processed map for date: {latest_raw_date}")

    # Use date-sorted raw files (newest first) for processing weights
    print(f"Processing {len(raw_files_sorted)} raw images in chronological order (newest first):")
    for i, (filename, filepath, date_obj, date_str) in enumerate(raw_files_sorted[:len(IMAGE_WEIGHTS)]):
        weight = IMAGE_WEIGHTS[i] if i < len(IMAGE_WEIGHTS) else 0
        print(f"  {i + 1}. {filename} ({date_str}) (weight: {weight})")

    if len(raw_files_sorted) == 1:
        # Copy single image and crop it
        shutil.copy(raw_files_sorted[0][1], target_processed_filepath)
        crop_processed_image(target_processed_filepath)
        # Generate GeoJSON for single image with correct date
        _generate_geojson_with_correct_date(target_processed_filepath, latest_raw_date)
        return target_processed_filepath

    # Process multiple images for comparison
    base_image = Image.open(raw_files_sorted[0][1]).convert("RGB")
    final_map_np = np.array(base_image, dtype=np.float32)

    high_prob_weights = np.zeros(final_map_np.shape[:2], dtype=np.float32)
    very_high_prob_weights = np.zeros(final_map_np.shape[:2], dtype=np.float32)

    for i, (filename, filepath, date_obj, date_str) in enumerate(raw_files_sorted[:len(IMAGE_WEIGHTS)]):
        image = Image.open(filepath).convert("RGB")
        weight = IMAGE_WEIGHTS[i]
        print(f"Processing {filename} ({date_str}) with weight {weight}")

        high_prob_weights += (
                np.array(_get_color_mask(image, HIGH_PROB_RGB)) / 255.0 * weight
        )
        very_high_prob_weights += (
                np.array(_get_color_mask(image, VERY_HIGH_PROB_RGB)) / 255.0 * weight
        )

    total_weights = high_prob_weights + very_high_prob_weights
    darken_factor = np.maximum(1.0 - total_weights, 0.75)

    for c in range(3):
        final_map_np[:, :, c] *= darken_factor

    highlight_mask = very_high_prob_weights > 0.7
    final_map_np[highlight_mask] = HIGHLIGHT_COLOR

    final_map = Image.fromarray(np.clip(final_map_np, 0, 255).astype(np.uint8))

    # 4. Save the processed image
    final_map.save(target_processed_filepath, optimize=True)
    print(f"New processed map saved: {target_processed_filepath}")

    # 5. Crop the processed image
    crop_processed_image(target_processed_filepath)

    # Clean up any other processed files
    for f in os.listdir(PROCESSED_DIR):
        if f != target_processed_filename and f.endswith('.png'):
            os.remove(os.path.join(PROCESSED_DIR, f))
            print(f"Removed old processed map: {f}")

    # 6. Generate GeoJSON data for geographic mapping with correct date
    _generate_geojson_with_correct_date(target_processed_filepath, latest_raw_date)

    return target_processed_filepath


def _generate_geojson_with_correct_date(processed_image_path: str, date_str: str):
    """
    Generate GeoJSON file with the correct date, replacing any existing one.

    Args:
        processed_image_path: Path to the processed (and cropped) image
        date_str: Correct date string for the image
    """
    from src.config import GEOJSON_DIR

    geojson_filename = f"mushroom_areas_{date_str}.geojson"
    geojson_path = os.path.join(GEOJSON_DIR, geojson_filename)

    # Remove old GeoJSON files first
    if os.path.exists(GEOJSON_DIR):
        for f in os.listdir(GEOJSON_DIR):
            if f.endswith('.geojson') and f != geojson_filename:
                old_path = os.path.join(GEOJSON_DIR, f)
                os.remove(old_path)
                print(f"Removed old GeoJSON: {f}")

    print(f"Generating GeoJSON data for {date_str}...")
    print(f"Processing cropped image: {processed_image_path}")

    try:
        # Debug: Check if image has highlighted areas
        image = Image.open(processed_image_path).convert("RGB")
        img_array = np.array(image)
        print(f"Cropped image dimensions: {image.size}")

        # Count blue pixels (highlighted areas)
        blue_mask = (img_array[:, :, 0] < 50) & (img_array[:, :, 1] < 50) & (img_array[:, :, 2] > 200)
        blue_pixel_count = np.sum(blue_mask)
        print(f"Found {blue_pixel_count} blue highlighted pixels in cropped image")

        # Also check for any non-standard blue highlighting
        alt_blue_mask = (img_array[:, :, 2] > img_array[:, :, 0] + 100) & (
                    img_array[:, :, 2] > img_array[:, :, 1] + 100)
        alt_blue_count = np.sum(alt_blue_mask)
        print(f"Found {alt_blue_count} alternative blue pixels in cropped image")

        result_path = geo_processor.process_image_to_geojson(processed_image_path, date_str)
        if result_path:
            print(f"GeoJSON generated successfully: {result_path}")
        else:
            print("Failed to generate GeoJSON data")
    except Exception as e:
        print(f"Error generating GeoJSON: {e}")
        import traceback
        traceback.print_exc()


def get_coordinates_for_pixel(x: int, y: int) -> Optional[tuple]:
    """
    Convert pixel coordinates to geographic coordinates.
    Note: These coordinates are for the CROPPED image.

    Args:
        x: Pixel x-coordinate in cropped image
        y: Pixel y-coordinate in cropped image

    Returns:
        Tuple of (longitude, latitude) or None if conversion fails
    """
    try:
        return geo_processor.pixel_to_coordinates(x, y)
    except Exception as e:
        print(f"Error converting coordinates: {e}")
        return None


def get_pixel_for_coordinates(longitude: float, latitude: float) -> Optional[tuple]:
    """
    Convert geographic coordinates to pixel coordinates.
    Note: These coordinates are for the CROPPED image.

    Args:
        longitude: Longitude in WGS84
        latitude: Latitude in WGS84

    Returns:
        Tuple of (x, y) pixel coordinates in cropped image or None if conversion fails
    """
    try:
        return geo_processor.coordinates_to_pixel(longitude, latitude)
    except Exception as e:
        print(f"Error converting coordinates: {e}")
        return None
