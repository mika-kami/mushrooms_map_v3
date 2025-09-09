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

# Initialize the EasyOCR reader
print("Initializing EasyOCR Reader...")
reader = easyocr.Reader(["en"])
print("EasyOCR Reader initialized.")


def _extract_date_from_filename(filename: str, prefix: str) -> Optional[str]:
    """Extracts 'dd.mm.yyyy' from a filename like 'prefix_dd.mm.yyyy.png'."""
    base = os.path.basename(filename)
    if base.startswith(prefix) and base.endswith(".png"):
        return base[len(prefix) : -4]
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
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
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
    Generates a processed map by comparing the last few raw images.
    - Darkens areas where 'HIGH' probability overlaps across at least two maps.
    - Highlights stable 'VERY HIGH' probability areas in blue.
    """
    latest_raw_path = get_latest_image_path(RAW_DIR)
    if not latest_raw_path:
        print("No raw images available to process.")
        return None

    # 1. Determine the required name for the processed file
    latest_raw_date = _extract_date_from_filename(latest_raw_path, "image_")
    if not latest_raw_date:
        print(f"Could not extract date from raw file: {latest_raw_path}")
        return None

    target_processed_filename = f"processed_{latest_raw_date}.png"
    target_processed_filepath = os.path.join(PROCESSED_DIR, target_processed_filename)

    # 2. Check if the up-to-date processed file already exists
    if os.path.exists(target_processed_filepath):
        print(
            f"Processed map for {latest_raw_date} already exists. Skipping processing."
        )
        return target_processed_filepath

    # 3. If not, proceed with creating the new map
    print(f"Generating new processed map for date: {latest_raw_date}")
    raw_images = sorted(
        [os.path.join(RAW_DIR, f) for f in os.listdir(RAW_DIR)],
        key=os.path.getmtime,
        reverse=True,
    )

    if len(raw_images) == 1:
        shutil.copy(raw_images[0], target_processed_filepath)
        print("Only one raw image found. Copied it as the processed map.")
        return target_processed_filepath

    base_image = Image.open(raw_images[0]).convert("RGB")
    final_map_np = np.array(base_image, dtype=np.float32)

    # Initialize arrays for weighted probabilities and occurrence counts
    high_prob_weights = np.zeros(final_map_np.shape[:2], dtype=np.float32)
    very_high_prob_weights = np.zeros(final_map_np.shape[:2], dtype=np.float32)
    high_prob_occurrence_count = np.zeros(final_map_np.shape[:2], dtype=np.int8)
    very_high_prob_occurrence_count = np.zeros(final_map_np.shape[:2], dtype=np.int8)

    # Process each raw image
    for i, img_path in enumerate(raw_images[: len(IMAGE_WEIGHTS)]):
        image = Image.open(img_path).convert("RGB")
        weight = IMAGE_WEIGHTS[i]

        # Process HIGH probability areas
        high_prob_mask = np.array(_get_color_mask(image, HIGH_PROB_RGB)) / 255.0
        high_prob_weights += high_prob_mask * weight
        high_prob_occurrence_count += (high_prob_mask > 0).astype(np.int8)

        # Process VERY HIGH probability areas
        very_high_prob_mask = (
            np.array(_get_color_mask(image, VERY_HIGH_PROB_RGB)) / 255.0
        )
        very_high_prob_weights += very_high_prob_mask * weight
        very_high_prob_occurrence_count += (very_high_prob_mask > 0).astype(np.int8)

    # An area is only considered if it appears in at least 2 images.
    # Zero out the weights for areas that do not meet the overlap criteria.
    high_prob_weights[high_prob_occurrence_count < 2] = 0
    very_high_prob_weights[very_high_prob_occurrence_count < 2] = 0

    # Calculate total weights for the darkening effect.
    # Darkening is caused by overlapping HIGH prob areas and any VERY HIGH prob areas.
    total_weights = high_prob_weights + very_high_prob_weights
    darken_factor = np.maximum(1.0 - total_weights, 0.75)

    # Apply darkening to the entire map
    for c in range(3):
        final_map_np[:, :, c] *= darken_factor

    # Highlight the most stable VERY HIGH probability areas in blue
    highlight_mask = very_high_prob_weights > 0.7
    final_map_np[highlight_mask] = HIGHLIGHT_COLOR

    final_map = Image.fromarray(np.clip(final_map_np, 0, 255).astype(np.uint8))

    # 4. Save the new file and clean up old ones
    final_map.save(target_processed_filepath, optimize=True)
    print(f"New processed map saved: {target_processed_filepath}")

    # Clean up any other processed files
    for f in os.listdir(PROCESSED_DIR):
        if f != target_processed_filename:
            os.remove(os.path.join(PROCESSED_DIR, f))
            print(f"Removed old processed map: {f}")

    return target_processed_filepath
