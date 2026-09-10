"""
Verification and Test Suite for AI Fastener Inspection System.
Validates all modules, image processing, Gemini client parser, and PySide6 GUI launch.
"""

import sys
import os
import cv2
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from config import BASE_DIR, SAMPLE_IMAGES_DIR, ALLOWED_CATEGORIES
from logger import app_logger, log_session_step
from image_utils import generate_sample_dataset, load_image, cv_to_qpixmap, draw_classification_overlay
from gemini_client import GeminiVisionClient
from classifier import FastenerClassifierManager
from ui.main_window import MainWindow

def run_tests():
    print("==================================================")
    print("RUNNING AI FASTENER CLASSIFIER TEST SUITE")
    print("==================================================")

    # Initialize Qt Application first so QPixmap/QImage operations succeed
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test Sample Dataset Generation
    print("\n[1/5] Testing Sample Dataset Generator...")
    generate_sample_dataset(str(SAMPLE_IMAGES_DIR))
    sample_files = os.listdir(SAMPLE_IMAGES_DIR)
    print(f"Generated samples: {sample_files}")
    assert len(sample_files) >= 4, "Expected at least 4 sample images"

    # 2. Test Image Loading and Overlay Rendering
    print("\n[2/5] Testing OpenCV & Qt Image Conversions...")
    for filename in sample_files:
        filepath = os.path.join(SAMPLE_IMAGES_DIR, filename)
        img = load_image(filepath)
        assert img is not None, f"Failed loading {filename}"
        pixmap = cv_to_qpixmap(img)
        assert not pixmap.isNull(), f"Failed converting {filename} to QPixmap"
        
        # Test overlay drawing for each category
        for cat in ["NUT", "BOLT", "SCREW", "WASHER", "UNKNOWN"]:
            annotated = draw_classification_overlay(img, cat, 0.92)
            assert annotated is not None and annotated.shape == img.shape

    from local_classifier import LocalFastenerClassifier
    local_clf = LocalFastenerClassifier()
    for filename in sample_files:
        filepath = os.path.join(SAMPLE_IMAGES_DIR, filename)
        img = load_image(filepath)
        local_res = local_clf.classify(img)
        assert local_res["category"] in ALLOWED_CATEGORIES, f"Invalid category from local classifier: {local_res}"
        print(f"  -> Local classified {filename}: {local_res['category']} ({int(local_res['confidence']*100)}%)")
    print("Image conversion, overlay, and local classifier tests PASSED.")

    # 3. Test Gemini JSON Parser & Validation
    print("\n[3/5] Testing Gemini Client JSON Parser Edge Cases...")
    client = GeminiVisionClient()

    # Valid direct JSON
    raw1 = '{"category": "bolt", "confidence": 0.96, "reason": "Six-sided head with threaded shaft."}'
    res1 = client._parse_json_response(raw1)
    assert res1["category"] == "BOLT", f"Failed category: {res1}"
    assert abs(res1["confidence"] - 0.96) < 1e-4, f"Failed confidence: {res1}"

    # Markdown code block wrapped JSON
    raw2 = '```json\n{\n  "category": "NUT",\n  "confidence": 94,\n  "reason": "Internal threads with hex profile."\n}\n```'
    res2 = client._parse_json_response(raw2)
    assert res2["category"] == "NUT", f"Failed markdown json: {res2}"
    assert abs(res2["confidence"] - 0.94) < 1e-4, f"Failed percentage conversion: {res2}"

    # Invalid / Invented Category
    raw3 = '{"category": "SPARK_PLUG", "confidence": 0.85, "reason": "Not standard"}'
    res3 = client._parse_json_response(raw3)
    assert res3["category"] == "UNKNOWN", f"Should normalize to UNKNOWN: {res3}"

    # Malformed text
    raw4 = "Analysis output: category is screw with 0.88 confidence. Reason: pointed tip."
    res4 = client._parse_json_response(raw4)
    assert res4["category"] in ALLOWED_CATEGORIES
    print("Gemini client parser tests PASSED.")

    # 4. Test Classifier Manager State & Counters
    print("\n[4/5] Testing Classifier Manager & Counters...")
    manager = FastenerClassifierManager()
    assert manager.counters["NUT"] == 0
    manager._on_worker_finished({"category": "NUT", "confidence": 0.95, "reason": "Test"})
    assert manager.counters["NUT"] == 1
    manager.reset_counters()
    assert manager.counters["NUT"] == 0
    print("Classifier manager state tests PASSED.")

    # 5. Test PySide6 GUI Window Instantiation & Event Loop
    print("\n[5/5] Testing PySide6 Desktop GUI Launch...")
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    print("MainWindow initialized and shown.")

    # Automatically close after 1 second of successful event processing
    QTimer.singleShot(1000, app.quit)
    app.exec()
    print("PySide6 Desktop event loop executed and exited cleanly.")

    print("\n==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY! (5/5)")
    print("==================================================")
    log_session_step("TESTS", "All verification tests passed (5/5).")

if __name__ == "__main__":
    run_tests()
