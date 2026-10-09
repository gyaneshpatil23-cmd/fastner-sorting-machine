"""
FILE: backend/app_config.py

WHAT THIS FILE DOES
    Central settings and constants for the whole app. Change a value here and every file that uses it follows.

MAIN PARTS
    - Folder paths (project, logs, sample images, .env)
    - App name and version
    - The fastener categories (NUT, BOLT, SCREW, WASHER, UNKNOWN) with descriptions and colours
    - Confidence thresholds (high / medium / low)
    - List of selectable AI models and the Gemini API key reader
    - YOLO model file location and minimum confidence
    - Camera defaults and supported image file types

USED BY
    backend/app_logging.py
    backend/camera_capture.py
    backend/gemini_cloud_classifier.py
    backend/image_loading_and_overlays.py
    backend/inspection_pipeline.py
    backend/opencv_measurement.py
    backend/opencv_shape_classifier.py
    backend/sqlite_database.py
    backend/tolerance_and_bin_decision.py
    frontend/ai_settings_dialog.py
    frontend/inspection_result_panel.py
    frontend/main_window.py
    frontend/tab_inspection_history.py
    main.py
    run_all_tests.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================================
# FOLDER PATHS
# Where the project, logs, sample images and the .env file live.
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
SAMPLE_IMAGES_DIR = BASE_DIR / "sample_images"
ENV_FILE = BASE_DIR / ".env"

# Ensure runtime directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
load_dotenv(dotenv_path=ENV_FILE)

# ============================================================================
# APP NAME AND VERSION
# Shown in the window title.
# ============================================================================
APP_TITLE = "AI Fastener Inspection System"
APP_SUBTITLE = "Vision-Based Fastener Classification Prototype"
APP_VERSION = "1.0.0 Pro Prototype"

# ============================================================================
# FASTENER CATEGORIES
# Category names, their descriptions and display colours.
# ============================================================================
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

# ============================================================================
# CONFIDENCE LEVELS
# What counts as high / medium / low confidence, and the colour of each.
# ============================================================================
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

# ============================================================================
# AI MODEL CHOICES AND GEMINI API KEY
# ============================================================================
MODEL_YOLO = "YOLO11n Fastener Classifier (Offline, Trained)"
MODEL_LOCAL_OFFLINE = "Local Offline Vision Engine (Zero-Config)"
AVAILABLE_MODELS = [
    MODEL_YOLO,
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

# ============================================================================
# YOLO CLASSIFIER
# The trained model file (made by train_yolo_classifier.py) and how sure it must be.
# ============================================================================
YOLO_MODEL_FILE = BASE_DIR / "models" / "fastener_yolo11n_cls.pt"
# Below this confidence the part is reported as UNKNOWN instead of guessing a category
YOLO_MIN_CONFIDENCE = 0.50
# Confidence needed to name a part when another region of the same picture looks empty.
# Measured on held-out photos: 0.85 kept every real part and rejected 94% of empty frames.
YOLO_CONFIDENCE_WHEN_DISPUTED = 0.85
# The class the model answers with when there is no fastener in the picture
YOLO_NO_FASTENER_CLASS = "NO_FASTENER"

# Photos saved with the "Save Photo for Training" button, one folder per class. They are added to the
# training set by build_classifier_dataset.py so the model learns your own camera, parts and lighting.
CAMERA_PHOTOS_DIR = BASE_DIR / "my_camera_photos"
TRAINING_CLASSES = ["BOLT", "NUT", "SCREW", "WASHER", "RIVET", YOLO_NO_FASTENER_CLASS]

def get_startup_model() -> str:
    """The model the app starts with: the trained YOLO model when it exists, otherwise the OpenCV rules."""
    return MODEL_YOLO if YOLO_MODEL_FILE.exists() else MODEL_LOCAL_OFFLINE

# ============================================================================
# CAMERA DEFAULTS
# ============================================================================
# True  = start with the laptop's built-in camera (current development setup)
# False = start with the external USB inspection camera when one is plugged in
PREFER_BUILT_IN_CAMERA = True
DEFAULT_CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# ============================================================================
# IMAGE FILE TYPES THE APP CAN OPEN
# ============================================================================
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
