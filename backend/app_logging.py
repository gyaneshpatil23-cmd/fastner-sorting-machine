"""
FILE: backend/app_logging.py

WHAT THIS FILE DOES
    Sets up the two log files the app writes while it runs.

MAIN PARTS
    - logs/application.log : detailed technical log (also printed to the console)
    - logs.txt             : short step-by-step history of each session
    - app_logger           : use app_logger.info(...) / .warning(...) / .error(...)
    - log_session_step()   : add one line to logs.txt

USED BY
    backend/camera_capture.py
    backend/esp32_communication.py
    backend/gemini_cloud_classifier.py
    backend/image_loading_and_overlays.py
    backend/inspection_pipeline.py
    backend/opencv_measurement.py
    backend/opencv_shape_classifier.py
    backend/sqlite_database.py
    backend/tolerance_and_bin_decision.py
    frontend/ai_settings_dialog.py
    frontend/main_window.py
    frontend/tab_bins_and_chute_angles.py
    frontend/tab_camera_calibration.py
    frontend/tab_hardware_control.py
    frontend/tab_inspection_history.py
    frontend/tab_iso_specifications.py
    main.py
    run_all_tests.py
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from backend.app_config import LOGS_DIR, BASE_DIR

# ============================================================================
# LOG FILE LOCATIONS
# ============================================================================
APP_LOG_FILE = LOGS_DIR / "application.log"
TRACKING_LOG_FILE = BASE_DIR / "logs.txt"

# ============================================================================
# APPLICATION LOG
# Detailed technical log: logs/application.log and the console.
# ============================================================================
def setup_logger(name: str = "FastenerVision") -> logging.Logger:
    """Configures and returns a thread-safe logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Formatter for structured logs
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File Handler (application.log)
    try:
        file_handler = logging.FileHandler(APP_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file handler: {e}")

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

app_logger = setup_logger()

# ============================================================================
# SESSION LOG
# Short step-by-step history written to logs.txt.
# ============================================================================
def log_session_step(step_tag: str, message: str):
    """
    Appends a step message to logs.txt for persistent session tracking.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_entry = f"[{timestamp}] [{step_tag}] {message}\n"
    
    # Also log to main app logger
    app_logger.info(f"[{step_tag}] {message}")
    
    try:
        with open(TRACKING_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_entry)
    except Exception as e:
        app_logger.error(f"Failed writing to logs.txt: {e}")
