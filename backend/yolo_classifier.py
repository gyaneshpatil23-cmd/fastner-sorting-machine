"""
FILE: backend/yolo_classifier.py

WHAT THIS FILE DOES
    Decides what kind of fastener is in the image using the trained YOLO11n-cls model
    (models/fastener_yolo11n_cls.pt, produced by train_yolo_classifier.py).
    Unlike the OpenCV rules in opencv_shape_classifier.py, it has learned from real photos, so it
    works on ordinary camera pictures and does not need a plain background.
    It only says WHAT the part is. Size is still measured by opencv_measurement.py.

MAIN PARTS
    - Model loading: the model is loaded the first time it is needed, not at app start
    - Where to look: the whole picture, the centre guide box, and the outline OpenCV finds
    - classify(): run the model on each of those regions and keep the most confident fastener answer;
      the model's NO_FASTENER class means there is nothing to identify
    - yolo_classifier: the shared classifier object the rest of the app uses

USED BY
    backend/inspection_pipeline.py
    frontend/ai_settings_dialog.py
    frontend/main_window.py
"""

import importlib.util
import threading
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from backend.app_config import (
    ALLOWED_CATEGORIES, CATEGORY_UNKNOWN, YOLO_MODEL_FILE, YOLO_MIN_CONFIDENCE, YOLO_NO_FASTENER_CLASS,
    YOLO_CONFIDENCE_WHEN_DISPUTED
)
from backend.app_logging import app_logger
from backend.image_loading_and_overlays import centre_guide_box, detect_fastener_roi

ENGINE_NAME = "YOLO11n-cls Trained Classifier"
Region = Tuple[int, int, int, int]  # x, y, width, height


# ============================================================================
# YOLO CLASSIFIER
# ============================================================================
class YoloFastenerClassifier:
    """Fastener type recognition with the trained YOLO11n classification model."""

    def __init__(self):
        self._model = None
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()

    # ========================================================================
    # MODEL LOADING
    # PyTorch takes a few seconds to load, so it is only loaded on first use.
    # ========================================================================
    def is_available(self) -> bool:
        """True when the model file exists, the YOLO software is installed, and loading has not failed."""
        return YOLO_MODEL_FILE.exists() and self._software_installed() and self._load_error is None

    @staticmethod
    def _software_installed() -> bool:
        return importlib.util.find_spec("ultralytics") is not None

    def unavailable_reason(self) -> str:
        if not YOLO_MODEL_FILE.exists():
            return f"No trained model found at models/{YOLO_MODEL_FILE.name}. Run train_yolo_classifier.py first."
        if not self._software_installed():
            return ("The YOLO software (ultralytics) is not installed in the Python that started the app. "
                    "Start the app with the project's .venv, or run: pip install -r requirements.txt")
        return self._load_error or ""

    def _load(self):
        with self._lock:
            if self._model is not None or self._load_error is not None:
                return
            if not self._software_installed():
                self._load_error = self.unavailable_reason()
                app_logger.error(self._load_error)
                return
            try:
                from ultralytics import YOLO
                self._model = YOLO(str(YOLO_MODEL_FILE))
                app_logger.info(f"YOLO classifier loaded: {YOLO_MODEL_FILE.name}, classes {list(self._model.names.values())}")
            except Exception as e:
                self._load_error = f"The YOLO model could not be loaded ({e})."
                app_logger.error(self._load_error)

    # ========================================================================
    # WHERE TO LOOK
    # The part may fill the picture or be a small object in it, so several regions are tried.
    # ========================================================================
    @staticmethod
    def _candidate_regions(cv_img: np.ndarray) -> List[Tuple[str, Region]]:
        h, w = cv_img.shape[:2]
        regions: List[Tuple[str, Region]] = [("whole picture", (0, 0, w, h)), ("centre guide box", centre_guide_box(w, h))]

        outline = detect_fastener_roi(cv_img)
        if outline is not None:
            _, _, ow, oh = outline
            # An outline covering nearly everything adds nothing over the whole picture
            if ow >= 24 and oh >= 24 and ow * oh < 0.80 * w * h:
                regions.append(("outline found by OpenCV", outline))
        return regions

    @staticmethod
    def _square_crop(cv_img: np.ndarray, region: Region) -> np.ndarray:
        """Cuts the region out and pads it to a square, so a long bolt or screw is not cropped at the ends."""
        x, y, w, h = region
        crop = cv_img[y:y + h, x:x + w]
        side = max(w, h)
        top, left = (side - h) // 2, (side - w) // 2
        return cv2.copyMakeBorder(crop, top, side - h - top, left, side - w - left, cv2.BORDER_REPLICATE)

    # ========================================================================
    # CLASSIFY
    # Returns the same result format as the other classifiers.
    # ========================================================================
    def classify(self, cv_img: np.ndarray) -> Dict[str, Any]:
        if cv_img is None or cv_img.size == 0:
            return self._failure("Empty image frame received.")

        self._load()
        if self._model is None:
            return self._failure(self.unavailable_reason())

        try:
            if cv_img.ndim == 2:
                cv_img = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2BGR)

            regions = self._candidate_regions(cv_img)
            crops = [self._square_crop(cv_img, region) for _, region in regions]
            results = self._model.predict(crops, device="cpu", verbose=False)

            def top(i: int) -> Tuple[str, float]:
                return str(self._model.names[int(results[i].probs.top1)]), float(results[i].probs.top1conf)

            # Keep the region the model is most sure shows a fastener. A region that looks empty does not
            # overrule it (the part may simply be small in that view), but it raises the confidence needed.
            indexes = range(len(results))
            empty = [i for i in indexes if top(i)[0] == YOLO_NO_FASTENER_CLASS]
            needed = YOLO_CONFIDENCE_WHEN_DISPUTED if empty else YOLO_MIN_CONFIDENCE
            with_part = [i for i in indexes if top(i)[0] != YOLO_NO_FASTENER_CLASS and top(i)[1] >= needed]
            best = max(with_part or empty or indexes, key=lambda i: top(i)[1])
            probs = results[best].probs
            region_name, region = regions[best]
            yolo_class = str(self._model.names[int(probs.top1)])
            confidence = float(probs.top1conf)
            scores = {str(self._model.names[i]): round(float(p), 3) for i, p in enumerate(probs.data.tolist())}

            category = yolo_class.upper()
            if yolo_class == YOLO_NO_FASTENER_CLASS:
                category = CATEGORY_UNKNOWN
                reason = "YOLO: No fastener found in the picture. Hold the part inside the guide box, close to the camera."
            elif confidence < YOLO_MIN_CONFIDENCE:
                category = CATEGORY_UNKNOWN
                reason = (f"YOLO: Not confident enough to name the part "
                          f"(best guess {yolo_class} at {confidence:.0%}). Move it closer or improve the lighting.")
            elif category not in ALLOWED_CATEGORIES or category == CATEGORY_UNKNOWN:
                category = CATEGORY_UNKNOWN
                reason = f"YOLO: Recognised as {yolo_class} ({confidence:.0%}), which is not one of the app's fastener categories."
            else:
                reason = f"YOLO: Recognised as {yolo_class} with {confidence:.0%} confidence (looked at the {region_name})."

            return {
                "success": True,
                "category": category,
                "confidence": round(confidence, 2),
                "reason": reason,
                "roi": region,
                "engine": ENGINE_NAME,
                "yolo_class": yolo_class,
                "scores": scores,
            }
        except Exception as e:
            app_logger.error(f"YOLO Classifier Exception: {e}")
            return self._failure(f"Image analysis failed ({e}).")

    @staticmethod
    def _failure(message: str) -> Dict[str, Any]:
        # Never guess a category after a failure: an unknown part must not be sorted as a good one
        return {"success": False, "category": CATEGORY_UNKNOWN, "confidence": 0.0,
                "reason": f"YOLO: {message}", "roi": None, "engine": ENGINE_NAME}


# ============================================================================
# SHARED INSTANCE
# Created once here; every other file imports this same object.
# ============================================================================
yolo_classifier = YoloFastenerClassifier()
