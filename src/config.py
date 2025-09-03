import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Telegram Bot ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- File Paths ---
MAPS_DIR = "/tmp/maps"
RAW_DIR = os.path.join(MAPS_DIR, "raw")
PROCESSED_DIR = os.path.join(MAPS_DIR, "processed")
GEOJSON_DIR = os.path.join(MAPS_DIR, "geojson")  # Directory for GeoJSON files
KML_DIR = os.path.join(MAPS_DIR, "kml")         # Directory for KML files

# --- Time To Run Job ---
UPD1_TIME_UTC = {"hh": 10, "mm": 00}
UPD2_TIME_UTC = {"hh": 19, "mm": 00}  # Temporary disabled

# --- Image Processing ---
IMAGE_URL = "https://info.chmi.cz/bio/maps/houby_1.png"
MAX_SAVED_IMAGES = 4
HIGH_PROB_RGB = (176, 221, 156)
VERY_HIGH_PROB_RGB = (112, 189, 143)
RGB_TOLERANCE = 0.03  # 3%
HIGHLIGHT_COLOR = (0, 0, 255)  # Blue

# --- Weights for comparison ---
# Newest to oldest: 40%, 30%, 20%, 10%
IMAGE_WEIGHTS = [0.4, 0.3, 0.2, 0.1]

# --- Image Cropping Parameters ---
# These parameters define how much to crop from each side of the processed image
CROP_PARAMS = {
    "left": 173,    # pixels to crop from left side
    "right": 173,   # pixels to crop from right side
    "top": 282,     # pixels to crop from top
    "bottom": 297   # pixels to crop from bottom
}

# --- Geographic Coordinate Mapping ---
# Czech Republic bounding box coordinates (approximate)
# These coordinates define the geographic bounds of the Czech Republic
# NOTE: These bounds now apply to the CROPPED image area
CZECH_BOUNDS = {
    "north": 51.0557,   # Northernmost point
    "south": 48.5518,   # Southernmost point
    "east": 18.8658,    # Easternmost point
    "west": 12.0964     # Westernmost point
}

# Image dimensions for coordinate mapping (will be updated dynamically)
# These represent the pixel dimensions of the CROPPED map image
IMAGE_BOUNDS = {
    "width": None,   # Will be set when first cropped image is processed
    "height": None   # Will be set when first cropped image is processed
}

# Coordinate system settings
COORDINATE_SYSTEM = "EPSG:4326"  # WGS84 coordinate system
OUTPUT_FORMATS = ["geojson", "kml"]  # Output formats for geographic data

# Minimum area threshold for geographic features (in pixels)
MIN_FEATURE_AREA = 400

# KML styling options
KML_STYLES = {
    "very_high": {
        "color": "ff0000ff",  # Red color in KML format (AABBGGRR)
        "fill_color": "770000ff",  # Semi-transparent red fill
        "line_width": 2
    },
    "high": {
        "color": "ff00ff00",  # Green color in KML format
        "fill_color": "7700ff00",  # Semi-transparent green fill
        "line_width": 2
    },
    "default": {
        "color": "ffffff00",  # Yellow color in KML format
        "fill_color": "77ffff00",  # Semi-transparent yellow fill
        "line_width": 1
    }
}

# Create directories if they don't exist
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(GEOJSON_DIR, exist_ok=True)  # Create GeoJSON directory
os.makedirs(KML_DIR, exist_ok=True)      # Create KML directory
