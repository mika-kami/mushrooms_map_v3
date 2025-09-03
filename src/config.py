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

# --- Time To Run Job ---
UPD1_TIME_UTC = {"hh": 10, "mm": 00}
UPD2_TIME_UTC = {"hh": 19, "mm": 00} # Temporary disabled

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

# Create directories if they don't exist
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
