"""
Fastener Inspection Orchestrator module for AI Fastener Inspection System.
Integrates classification, calibrated dimensional measurement, ISO tolerance verification,
database logging, and automated sorting hardware dispatch.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from backend.config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER,
    CATEGORY_UNKNOWN, ALLOWED_CATEGORIES, DEFAULT_MODEL, MODEL_LOCAL_OFFLINE,
    get_gemini_api_key
)
from backend.gemini_client import GeminiVisionClient
from backend.local_classifier import LocalFastenerClassifier
from backend.dimensional_measurement import dimension_engine
from backend.verification_engine import verification_engine
from backend.hardware_comm import hardware_manager
from backend.database import db_instance
from backend.logger import app_logger, log_session_step


class FastenerInspectionWorker(QThread):
    """
    Asynchronous QThread worker that runs the full inspection pipeline:
    Visual Classification -> Physical Dimensioning -> Specification Verification -> Tray Mapping.
    """
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        cv_img: np.ndarray,
        model_name: str = DEFAULT_MODEL,
        auto_sort: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.cv_img = cv_img.copy() if cv_img is not None else None
        self.model_name = model_name
        self.auto_sort = auto_sort
        self.gemini_client = GeminiVisionClient(model_name=self.model_name)
        self.local_classifier = LocalFastenerClassifier()

    def run(self):
        if self.cv_img is None or self.cv_img.size == 0:
            self.error.emit("Invalid or empty image frame provided for inspection.")
            return

        try:
            # 1. Step 1: Category Classification
            api_key = get_gemini_api_key()
            is_local = (self.model_name == MODEL_LOCAL_OFFLINE) or (not api_key)

            if is_local:
                class_res = self.local_classifier.classify(self.cv_img)
            else:
                class_res = self.gemini_client.classify_image(self.cv_img, model_name=self.model_name)
                if not class_res.get("success", False) and class_res.get("error") == "API_KEY_MISSING":
                    class_res = self.local_classifier.classify(self.cv_img)

            category = class_res.get("category", CATEGORY_UNKNOWN)
            confidence = float(class_res.get("confidence", 0.0))

            # 2. Step 2: Calibrated Dimensional Measurement (OpenCV)
            meas_res = dimension_engine.measure_fastener(self.cv_img, category)

            # 3. Step 3: Specification & Tolerance Verification
            verif_res = verification_engine.verify_and_decide(category, confidence, meas_res)

            # Combine into unified inspection packet
            inspection_packet: Dict[str, Any] = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "category": category,
                "confidence": confidence,
                "classification_reason": class_res.get("reason", ""),
                "measurements": meas_res,
                "length_mm": meas_res.get("length_mm", 0.0),
                "stem_dia_mm": meas_res.get("stem_dia_mm", 0.0),
                "head_width_mm": meas_res.get("head_width_mm", 0.0),
                "inner_dia_mm": meas_res.get("inner_dia_mm", 0.0),
                "outer_dia_mm": meas_res.get("outer_dia_mm", 0.0),
                "decision": verif_res.get("decision", "REJECT"),
                "detected_size": verif_res.get("matched_size", "Unknown"),
                "assigned_tray": verif_res.get("assigned_tray", 10),
                "servo_angle": verif_res.get("servo_angle", 180),
                "reason": verif_res.get("reason", ""),
                "inconsistency_detected": verif_res.get("inconsistency_detected", False),
                "tolerance_errors": verif_res.get("tolerance_errors", []),
                "nominal_spec": verif_res.get("nominal_spec"),
                "raw_image": self.cv_img
            }

            # 4. Step 4: Persist in SQLite Database
            db_instance.log_inspection(inspection_packet)

            # 5. Step 5: Dispatch Hardware Sorting Cycle if enabled
            if self.auto_sort and inspection_packet["decision"] != "REINSPECT":
                hardware_manager.execute_sorting_cycle(
                    tray_id=inspection_packet["assigned_tray"],
                    servo_angle=inspection_packet["servo_angle"]
                )

            self.finished.emit(inspection_packet)

        except Exception as e:
            app_logger.error(f"Inspection pipeline failure: {e}")
            self.error.emit(f"Inspection failed: {str(e)}")


class FastenerClassifierManager(QObject):
    """Coordinates inspections, batch statistics, and event subscriptions."""
    inspection_completed = Signal(dict)
    counters_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_worker: Optional[FastenerInspectionWorker] = None
        
        # Load persistent counters from SQLite database
        saved_counters = db_instance.load_batch_counters()
        self.counters = {cat: saved_counters.get(cat, 0) for cat in ALLOWED_CATEGORIES}
        self.counters["ACCEPTED"] = saved_counters.get("ACCEPTED", 0)
        self.counters["REJECTED"] = saved_counters.get("REJECTED", 0)
        self.history: List[Dict[str, Any]] = []

    def start_classification(
        self,
        cv_img: np.ndarray,
        model_name: str = DEFAULT_MODEL,
        auto_sort: bool = True
    ) -> Optional[FastenerInspectionWorker]:
        """Spawns asynchronous worker thread."""
        if self._current_worker and self._current_worker.isRunning():
            app_logger.warning("Inspection already in progress.")
            return None

        self._current_worker = FastenerInspectionWorker(cv_img, model_name, auto_sort, parent=self)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.error.connect(self._on_worker_error)
        self._current_worker.start()
        return self._current_worker

    def _on_worker_finished(self, result: Dict[str, Any]):
        category = result.get("category", CATEGORY_UNKNOWN)
        decision = result.get("decision", "REJECT")

        if category in self.counters:
            self.counters[category] += 1
        else:
            self.counters[CATEGORY_UNKNOWN] += 1

        if decision == "ACCEPT":
            self.counters["ACCEPTED"] += 1
        elif decision == "REJECT":
            self.counters["REJECTED"] += 1

        # Persist counters to SQLite
        db_instance.save_batch_counters(self.counters)

        self.history.append(result)
        self.counters_updated.emit(self.counters.copy())
        self.inspection_completed.emit(result)

    def _on_worker_error(self, error_message: str):
        log_session_step("ERROR", f"Inspection error: {error_message}")

    def reset_counters(self):
        for cat in self.counters:
            self.counters[cat] = 0
        db_instance.save_batch_counters(self.counters)
        self.counters_updated.emit(self.counters.copy())
        db_instance.reset_tray_counts()
        log_session_step("SYSTEM", "Batch counters reset.")

    def clear_history(self):
        self.history.clear()
        db_instance.clear_history()
        log_session_step("SYSTEM", "Inspection history cleared.")
