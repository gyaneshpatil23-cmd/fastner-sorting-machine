"""
Fastener Classifier Management module for AI Fastener Inspection System.
Manages asynchronous classification tasks using QThread worker to keep the GUI responsive.
Designed with modularity for future hardware (ESP32/conveyor/sorting chute) integration.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from config import (
    CATEGORY_NUT,
    CATEGORY_BOLT,
    CATEGORY_SCREW,
    CATEGORY_WASHER,
    CATEGORY_UNKNOWN,
    ALLOWED_CATEGORIES,
    DEFAULT_MODEL,
    MODEL_LOCAL_OFFLINE,
    get_gemini_api_key
)
from gemini_client import GeminiVisionClient
from local_classifier import LocalFastenerClassifier
from logger import app_logger, log_session_step


class FastenerClassificationWorker(QThread):
    """
    Asynchronous QThread worker to perform vision inference
    (either via Local Offline Vision Engine or Gemini API)
    without blocking the PySide6 UI event loop.
    """
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, cv_img: np.ndarray, model_name: str = DEFAULT_MODEL, parent=None):
        super().__init__(parent)
        self.cv_img = cv_img.copy() if cv_img is not None else None
        self.model_name = model_name
        self.gemini_client = GeminiVisionClient(model_name=self.model_name)
        self.local_classifier = LocalFastenerClassifier()

    def run(self):
        """Worker thread execution method."""
        if self.cv_img is None or self.cv_img.size == 0:
            err_msg = "Invalid or empty image frame provided for classification."
            app_logger.error(err_msg)
            self.error.emit(err_msg)
            return

        try:
            api_key = get_gemini_api_key()
            is_local = (self.model_name == MODEL_LOCAL_OFFLINE) or (not api_key)

            if is_local:
                app_logger.info("Executing classification via Local Offline Computer Vision Engine...")
                result = self.local_classifier.classify(self.cv_img)
            else:
                app_logger.info(f"Starting fastener classification using Gemini model '{self.model_name}'...")
                result = self.gemini_client.classify_image(self.cv_img, model_name=self.model_name)
                
                # If Gemini encountered missing key or network issue, fallback to local engine
                if not result.get("success", False) and result.get("error") == "API_KEY_MISSING":
                    app_logger.info("Falling back to Local Offline Vision Engine...")
                    result = self.local_classifier.classify(self.cv_img)
            
            # Attach timestamp
            result["timestamp"] = datetime.now().strftime("%H:%M:%S")
            result["date"] = datetime.now().strftime("%Y-%m-%d")
            
            self.finished.emit(result)
        except Exception as e:
            app_logger.error(f"Worker exception: {e}, attempting local fallback...")
            try:
                fallback_res = self.local_classifier.classify(self.cv_img)
                fallback_res["timestamp"] = datetime.now().strftime("%H:%M:%S")
                fallback_res["date"] = datetime.now().strftime("%Y-%m-%d")
                self.finished.emit(fallback_res)
            except Exception as e2:
                self.error.emit(f"Classification failed: {str(e2)}")


class FastenerClassifierManager(QObject):
    """
    High-level manager for fastener inspection operations.
    Maintains statistics/counters and records inspection history in-memory.
    """
    inspection_completed = Signal(dict)
    counters_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_worker: Optional[FastenerClassificationWorker] = None
        
        # Category Counters
        self.counters = {cat: 0 for cat in ALLOWED_CATEGORIES}
        
        # In-memory inspection history list of dicts
        self.history: List[Dict[str, Any]] = []

    def start_classification(self, cv_img: np.ndarray, model_name: str = DEFAULT_MODEL) -> Optional[FastenerClassificationWorker]:
        """Spawns an asynchronous worker thread for classification."""
        if self._current_worker and self._current_worker.isRunning():
            app_logger.warning("Classification already in progress. Ignoring duplicate request.")
            return None

        self._current_worker = FastenerClassificationWorker(cv_img, model_name)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.error.connect(self._on_worker_error)
        self._current_worker.start()
        return self._current_worker

    def _on_worker_finished(self, result: Dict[str, Any]):
        """Handles successful worker completion and updates counters/history."""
        category = result.get("category", CATEGORY_UNKNOWN)
        confidence = result.get("confidence", 0.0)

        # Update counter
        if category in self.counters:
            self.counters[category] += 1
        else:
            self.counters[CATEGORY_UNKNOWN] += 1

        # Add to history
        self.history.append(result)
        
        # Log event
        log_session_step(
            "INSPECTION",
            f"Detected {category} (Confidence: {int(confidence*100)}%) - {result.get('reason', '')}"
        )

        self.counters_updated.emit(self.counters.copy())
        self.inspection_completed.emit(result)

    def _on_worker_error(self, error_message: str):
        """Handles worker failure gracefully."""
        log_session_step("ERROR", f"Classification error: {error_message}")

    def reset_counters(self):
        """Resets all category counters to zero."""
        for cat in self.counters:
            self.counters[cat] = 0
        self.counters_updated.emit(self.counters.copy())
        log_session_step("SYSTEM", "Category counters reset to zero.")

    def clear_history(self):
        """Clears in-memory inspection history."""
        self.history.clear()
        log_session_step("SYSTEM", "Inspection history cleared.")
