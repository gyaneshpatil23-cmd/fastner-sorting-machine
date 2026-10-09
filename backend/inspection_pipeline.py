"""
FILE: backend/inspection_pipeline.py

WHAT THIS FILE DOES
    Runs one complete inspection from start to finish, in the background so the window stays responsive:
        1. classify the part   (trained YOLO model, Gemini, or the offline OpenCV rules)
        2. measure it          (opencv_measurement.py)
        3. check tolerances and pick a bin (tolerance_and_bin_decision.py)
        4. save the result     (sqlite_database.py)
        5. start the physical sorting cycle (esp32_communication.py)

MAIN PARTS
    - FastenerInspectionWorker: the background thread that performs the five steps above
    - Sort-by-type mode: step 3 only picks the bin for the fastener type; sizes are shown but not judged
    - Shape cross-check: a 'washer' whose outline has corners is corrected to a nut
    - FastenerClassifierManager: what the UI calls to start an inspection; also keeps the batch counters

USED BY
    frontend/main_window.py
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from backend.app_config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER,
    CATEGORY_UNKNOWN, ALLOWED_CATEGORIES, DEFAULT_MODEL, MODEL_LOCAL_OFFLINE, MODEL_YOLO,
    YOLO_NO_FASTENER_CLASS,
    get_gemini_api_key
)
from backend.gemini_cloud_classifier import GeminiVisionClient
from backend.opencv_shape_classifier import LocalFastenerClassifier
from backend.yolo_classifier import yolo_classifier
from backend.opencv_measurement import dimension_engine, outline_has_corners
from backend.tolerance_and_bin_decision import verification_engine
from backend.esp32_communication import hardware_manager
from backend.sqlite_database import db_instance
from backend.app_logging import app_logger, log_session_step


# ============================================================================
# INSPECTION WORKER
# Runs one full inspection in a background thread:
# classify -> measure -> verify -> save -> sort.
# ============================================================================
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
        identify_only: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.cv_img = cv_img.copy() if cv_img is not None else None
        self.model_name = model_name
        self.auto_sort = auto_sort
        self.identify_only = identify_only
        self.gemini_client = GeminiVisionClient(model_name=self.model_name)
        self.local_classifier = LocalFastenerClassifier()

    def _classify(self):
        """
        Runs the classifier for the selected model.
        Returns (result, used_outline_rules). If the selected model fails, the offline OpenCV rules take over.
        """
        if self.model_name == MODEL_YOLO:
            class_res = yolo_classifier.classify(self.cv_img)
            label = "YOLO model unavailable"
        elif self.model_name != MODEL_LOCAL_OFFLINE and get_gemini_api_key():
            class_res = self.gemini_client.classify_image(self.cv_img, model_name=self.model_name)
            label = "Cloud AI unavailable"
        else:
            return self.local_classifier.classify(self.cv_img), True

        if class_res.get("success", False):
            return class_res, False

        # An outage or missing model must not send good parts to the reject bin: fall back to the offline engine
        problem = class_res.get("reason", "Analysis failed.")
        app_logger.warning(f"{label}, using offline engine: {problem}")
        class_res = self.local_classifier.classify(self.cv_img)
        class_res["reason"] = f"[{label}: {problem}] {class_res.get('reason', '')}"
        return class_res, True

    def run(self):
        if self.cv_img is None or self.cv_img.size == 0:
            self.error.emit("Invalid or empty image frame provided for inspection.")
            return

        try:
            # 1. Step 1: Category Classification
            class_res, is_local = self._classify()
            category = class_res.get("category", CATEGORY_UNKNOWN)
            confidence = float(class_res.get("confidence", 0.0))

            # 2. Step 2: Calibrated Dimensional Measurement (OpenCV)
            # The OpenCV classifier returns a box round the part, so the same object is measured.
            # YOLO only reports which region of the picture it looked at (it may lie inside the part),
            # so after YOLO the part is found again in the whole picture.
            measure_roi = class_res.get("roi") if is_local else None
            meas_res = dimension_engine.measure_fastener(self.cv_img, category, roi_bbox=measure_roi)

            # Cross-check the class against the measured shape: a washer is round, so an outline with
            # flat sides and corners is a nut, however sure the classifier was
            if category == CATEGORY_WASHER and meas_res.get("success") and outline_has_corners(meas_res.get("contour")):
                class_res["reason"] = (
                    "Shape check: the outline has flat sides and corners, so this is a NUT, not a WASHER. "
                    f"[{class_res.get('reason', '')}]"
                )
                category = CATEGORY_NUT
                meas_res = dimension_engine.measure_fastener(self.cv_img, category, roi_bbox=measure_roi)

            if self.identify_only:
                # Sort-by-type mode: the bin is chosen from the fastener type; sizes are shown but not judged
                verif_res = verification_engine.route_by_type(category, meas_res)
                verif_res["reason"] = f"{class_res.get('reason', '')} {verif_res.get('reason', '')}".strip()
            else:
                # 3. Step 3: Specification & Tolerance Verification
                verif_res = verification_engine.verify_and_decide(category, confidence, meas_res)

                if category == CATEGORY_UNKNOWN:
                    # Show why the classifier could not name the part, not only that it was rejected
                    verif_res["reason"] = f"{class_res.get('reason', '')} {verif_res.get('reason', '')}".strip()

                # The offline engine only matches outlines, so a shape whose size fits no fastener is not one
                if is_local and verif_res.get("unrecognized"):
                    class_res["reason"] = (
                        f"Outline resembles a {category.lower()}, but its size matches no configured fastener. "
                        f"{class_res.get('reason', '')}"
                    )
                    category = CATEGORY_UNKNOWN
                    confidence = min(confidence, 0.30)
                    meas_res["category"] = CATEGORY_UNKNOWN

            if class_res.get("yolo_class") == YOLO_NO_FASTENER_CLASS:
                # An empty pad is not a reject: there is no part to send anywhere
                verif_res["assigned_tray"] = 0
                verif_res["servo_angle"] = 0
                verif_res["reason"] = f"{class_res.get('reason', '')} Nothing was sorted."

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
                "assigned_tray": verif_res.get("assigned_tray", 0),
                "servo_angle": verif_res.get("servo_angle", 0),
                "reason": verif_res.get("reason", ""),
                "inconsistency_detected": verif_res.get("inconsistency_detected", False),
                "tolerance_errors": verif_res.get("tolerance_errors", []),
                "nominal_spec": verif_res.get("nominal_spec"),
                "identify_only": self.identify_only,
                "engine": class_res.get("engine", ""),
                "raw_image": self.cv_img
            }

            # 4. Step 4: Persist in SQLite Database
            db_instance.log_inspection(inspection_packet)

            # 5. Step 5: Dispatch Hardware Sorting Cycle if enabled (bin 0 means there is nowhere to route the part)
            if self.auto_sort and inspection_packet["decision"] != "REINSPECT" and inspection_packet["assigned_tray"] > 0:
                hardware_manager.execute_sorting_cycle(
                    tray_id=inspection_packet["assigned_tray"],
                    servo_angle=inspection_packet["servo_angle"]
                )

            self.finished.emit(inspection_packet)

        except Exception as e:
            app_logger.error(f"Inspection pipeline failure: {e}")
            self.error.emit(f"Inspection failed: {str(e)}")


# ============================================================================
# INSPECTION MANAGER
# Starts inspections for the UI and keeps the batch counters.
# ============================================================================
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
        auto_sort: bool = True,
        identify_only: bool = False
    ) -> Optional[FastenerInspectionWorker]:
        """Spawns asynchronous worker thread."""
        if self._current_worker and self._current_worker.isRunning():
            app_logger.warning("Inspection already in progress.")
            return None

        self._current_worker = FastenerInspectionWorker(cv_img, model_name, auto_sort, identify_only, parent=self)
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
