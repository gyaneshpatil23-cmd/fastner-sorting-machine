"""
Configuration module for AI Fastener Inspection System.
Handles environment variables, application constants, classification categories,
and confidence thresholds.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
SAMPLE_IMAGES_DIR = BASE_DIR / "sample_images"
ENV_FILE = BASE_DIR / ".env"

# Ensure runtime directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
load_dotenv(dotenv_path=ENV_FILE)

# Application Information
APP_TITLE = "AI Fastener Inspection System"
APP_SUBTITLE = "Vision-Based Fastener Classification Prototype"
APP_VERSION = "1.0.0 Pro Prototype"

# Classification Categories
CATEGORY_NUT = "NUT"
CATEGORY_BOLT = "BOLT"
CATEGORY_SCREW = "SCREW"
CATEGORY_WASHER = "WASHER"
CATEGORY_UNKNOWN = "UNKNOWN"

ALLOWED_CATEGORIES = [
    CATEGORY_NUT,
    CATEGORY_BOLT,
    CATEGORY_SCREW,
    CATEGORY_WASHER,
    CATEGORY_UNKNOWN,
]

CATEGORY_DESCRIPTIONS = {
    CATEGORY_NUT: "Internally threaded fastener with center hole (hexagonal / square / flange).",
    CATEGORY_BOLT: "Externally threaded cylindrical fastener intended for use with a nut.",
    CATEGORY_SCREW: "Threaded fastener with distinct drive head (Phillips, slotted, countersunk, etc.).",
    CATEGORY_WASHER: "Flat or locking annular ring with central hole for load distribution.",
    CATEGORY_UNKNOWN: "Object geometry does not match standard fastener profiles or is unrecognizable.",
}

CATEGORY_COLORS = {
    CATEGORY_NUT: "#2563EB",      # Engineering Blue
    CATEGORY_BOLT: "#059669",     # Emerald Green
    CATEGORY_SCREW: "#D97706",    # Industrial Amber
    CATEGORY_WASHER: "#7C3AED",   # Purple
    CATEGORY_UNKNOWN: "#64748B",  # Slate Gray
}

# Confidence Level Thresholds
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

def get_confidence_level(confidence: float) -> str:
    """Returns 'HIGH CONFIDENCE', 'MEDIUM CONFIDENCE', or 'LOW CONFIDENCE'."""
    if confidence >= CONFIDENCE_HIGH_THRESHOLD:
        return "HIGH CONFIDENCE"
    elif confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "MEDIUM CONFIDENCE"
    else:
        return "LOW CONFIDENCE"

def get_confidence_color(confidence: float) -> str:
    """Return hex color code corresponding to confidence level."""
    if confidence >= CONFIDENCE_HIGH_THRESHOLD:
        return "#15803D"  # Dark green
    elif confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "#B45309"  # Amber
    else:
        return "#B91C1C"  # Dark red

# AI Configuration
MODEL_LOCAL_OFFLINE = "Local Offline Vision Engine (Zero-Config)"
AVAILABLE_MODELS = [
    MODEL_LOCAL_OFFLINE,
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-2.5-flash",
]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", MODEL_LOCAL_OFFLINE)

def get_gemini_api_key() -> str:
    """Retrieves GEMINI_API_KEY from environment or .env file."""
    # Reload in case .env was modified or created in GUI
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()

# Camera Configuration
DEFAULT_CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# File Formats Supported
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
