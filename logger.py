"""
Logging module for AI Fastener Inspection System.
Sets up structured logging to files and console, plus session tracking in logs.txt.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from config import LOGS_DIR, BASE_DIR

APP_LOG_FILE = LOGS_DIR / "application.log"
TRACKING_LOG_FILE = BASE_DIR / "logs.txt"

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
