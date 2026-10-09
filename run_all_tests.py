"""
FILE: run_all_tests.py

WHAT THIS FILE DOES
    Automated check that the whole system still works. Run it after changing code:
        python run_all_tests.py
    It uses a temporary database, so real specifications, bins and counters are not touched.

MAIN PARTS
    - 1. Database and saved counters
    - 2. Emergency stop
    - 3. Sample image generator
    - 4. OpenCV classifier + measurement on the sample images
    - 5. Tolerance check and bin decision
    - 6. ESP32 simulator
    - 7. Main window opens with all six tabs
    - 8. Trained YOLO classifier (skipped when no model has been trained)
"""

import sys
import tempfile
import os
import cv2
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Run against a throwaway database so tests never touch production specs, bins or counters.
# This must be set before any backend module is imported.
os.environ["FASTENER_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="fastener_test_"), "test.db")

from backend.app_config import BASE_DIR, SAMPLE_IMAGES_DIR, ALLOWED_CATEGORIES, YOLO_MODEL_FILE
from backend.app_logging import app_logger, log_session_step
from backend.image_loading_and_overlays import generate_sample_dataset, load_image, cv_to_qpixmap
from backend.opencv_shape_classifier import LocalFastenerClassifier
from backend.yolo_classifier import yolo_classifier
from backend.opencv_measurement import dimension_engine
from backend.tolerance_and_bin_decision import verification_engine
from backend.esp32_communication import hardware_manager
from backend.sqlite_database import db_instance
from frontend.main_window import MainWindow

def run_tests():
    print("==================================================")
    print("RUNNING EXTENDED INDUSTRIAL SUITE TEST SUITE")
    print("==================================================")

    # Initialize Qt Application
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test SQLite Database & Persistent Batch Counters
    print("\n[1/8] Testing SQLite Database, Custom Sizes & Persistent Batch Counters...")
    specs = db_instance.get_specifications()
    assert len(specs) >= 15, f"Expected at least 15 ISO specifications, got {len(specs)}"

    # Test adding a custom specification
    new_id = db_instance.add_specification("BOLT", "M8 x 45 Custom", 8.0, 7.78, 8.22, 45.0, 44.0, 46.0)
    assert new_id > 0, "Failed to insert custom specification"
    db_instance.delete_specification(new_id)

    # Test saving and restoring batch counters
    db_instance.save_batch_counters({"BOLT": 15, "NUT": 12, "ACCEPTED": 25, "REJECTED": 2})
    loaded_counters = db_instance.load_batch_counters()
    assert loaded_counters.get("BOLT") == 15 and loaded_counters.get("ACCEPTED") == 25, f"Counter persistence error: {loaded_counters}"
    print(f"SQLite DB & Persistence validated ({len(specs)} ISO specs, persistent session counters active).")

    # 2. Test Emergency Stop (E-STOP)
    print("\n[2/8] Testing Hardware Emergency Stop (E-STOP) Kill Switch...")
    hardware_manager.emergency_stop()
    assert hardware_manager._is_estopped, "E-Stop state not set"
    assert hardware_manager.telemetry["state"] == "EMERGENCY_STOP", "Telemetry state not EMERGENCY_STOP"
    assert not hardware_manager.send_command({"command": "CONVEYOR", "action": "RUN"}), "Motion command accepted during E-Stop"
    assert not hardware_manager.telemetry["conveyor"], "Conveyor started during E-Stop"
    hardware_manager.reset_estop()
    assert not hardware_manager._is_estopped, "E-Stop reset failed"
    assert hardware_manager.telemetry["state"] == "READY", "Telemetry state not READY after reset"
    print("Emergency Stop (E-STOP) hardware & software kill switch verified.")

    # 3. Test Sample Dataset Generation
    print("\n[3/8] Testing Sample Dataset Generator...")
    generate_sample_dataset(str(SAMPLE_IMAGES_DIR))
    sample_files = os.listdir(SAMPLE_IMAGES_DIR)
    assert len(sample_files) >= 4, "Expected at least 4 sample images"
    print(f"Samples: {sample_files}")

    # 4. Test Local Classifier & Calibrated Dimensional Measurements
    print("\n[4/8] Testing Local Classifier & Calibrated OpenCV Measurement...")
    local_clf = LocalFastenerClassifier()
    # The built-in samples are drawn to scale, so each must be accepted as its nominal size
    expected_samples = {
        "sample_01_hex_nut.png": ("NUT", "M8 Nut"),
        "sample_02_hex_bolt.png": ("BOLT", "M8 x 40"),
        "sample_03_wood_screw.png": ("SCREW", "M4 x 20 Screw"),
        "sample_04_flat_washer.png": ("WASHER", "M8 Washer"),
    }
    for filename in sample_files:
        filepath = os.path.join(SAMPLE_IMAGES_DIR, filename)
        img = load_image(filepath)
        assert img is not None, f"Failed loading {filename}"

        class_res = local_clf.classify(img)
        category = class_res["category"]
        assert category in ALLOWED_CATEGORIES, f"Invalid category: {class_res}"

        meas = dimension_engine.measure_fastener(img, category, roi_bbox=class_res.get("roi"))
        print(f"  -> {filename}: {category} | Length: {meas.get('length_mm', 0):.1f}mm, Stem Dia: {meas.get('stem_dia_mm', 0):.1f}mm, Inner Dia: {meas.get('inner_dia_mm', 0):.1f}mm")

        if filename in expected_samples:
            exp_category, exp_size = expected_samples[filename]
            assert meas["success"], f"Measurement failed for {filename}"
            verif = verification_engine.verify_and_decide(category, class_res["confidence"], meas)
            assert category == exp_category, f"{filename}: expected {exp_category}, got {category}"
            assert verif["decision"] == "ACCEPT" and verif["matched_size"] == exp_size, f"{filename}: {verif['reason']}"

    # A shape that is not a fastener must never be accepted
    blob = np.full((1300, 1000, 3), 235, dtype=np.uint8)
    cv2.rectangle(blob, (240, 130), (760, 910), (40, 35, 30), -1)
    blob_class = local_clf.classify(blob)
    blob_meas = dimension_engine.measure_fastener(blob, blob_class["category"], roi_bbox=blob_class.get("roi"))
    blob_verif = verification_engine.verify_and_decide(blob_class["category"], blob_class["confidence"], blob_meas)
    assert blob_verif["decision"] == "REJECT", f"Non-fastener object was not rejected: {blob_verif}"
    print("  -> Non-fastener object correctly rejected.")

    # 5. Test Tolerance Verification & Tray Mapping
    print("\n[5/8] Testing Specification Matching & Dynamic Bin Decision Engine...")
    bolt_meas = {"success": True, "stem_dia_mm": 8.0, "length_mm": 40.0}
    verif = verification_engine.verify_and_decide("BOLT", 0.95, bolt_meas)
    assert verif["decision"] == "ACCEPT", f"Expected ACCEPT for standard M8 bolt, got {verif}"
    print(f"Decision verified: {verif['matched_size']} -> Decision: {verif['decision']} -> Bin {verif['assigned_tray']} (Angle: {verif['servo_angle']}°)")

    # 6. Test Hardware Simulator & Sorting Sequence
    print("\n[6/8] Testing ESP32 Hardware Simulator & Sorting Cycle...")
    hardware_manager.set_mode("SIMULATOR")
    assert hardware_manager._is_connected, "Hardware simulator failed to connect"
    hardware_manager.send_command({"command": "SORT", "tray": 2, "angle": 65})
    assert hardware_manager.telemetry["chute_angle"] == 65, "Chute angle update failed in simulator"
    print("ESP32 Hardware Simulation validated.")

    # 7. Test Master PySide6 Multi-Tab GUI Window Launch with E-STOP & Custom Tabs
    print("\n[7/8] Testing Master Desktop Window & All Workstation Tabs...")
    window = MainWindow()
    assert window.tabs.count() == 6, f"Expected 6 dashboard tabs, got {window.tabs.count()}"
    window.show()
    print("MainWindow with all 6 tabs, E-STOP banner, and persistent counters initialized.")

    # Auto close after 1 second
    QTimer.singleShot(1000, app.quit)
    app.exec()
    print("Master GUI event loop executed and exited cleanly.")

    # 8. Test Trained YOLO Classifier
    print("\n[8/8] Testing Trained YOLO Classifier...")
    if not YOLO_MODEL_FILE.exists():
        print("  -> Skipped: no trained model yet (run train_yolo_classifier.py).")
    else:
        blank = yolo_classifier.classify(np.full((480, 640, 3), 200, dtype=np.uint8))
        assert blank["success"], f"YOLO model failed to run: {blank['reason']}"

        # Held-out photos the model was not trained on; most of them must be named correctly
        test_dir = BASE_DIR / "fastener_sorter_cls" / "test"
        checked = correct = 0
        for category in ("BOLT", "NUT", "SCREW", "WASHER"):
            for path in sorted((test_dir / category).glob("*.jpg"))[:5]:
                result = yolo_classifier.classify(load_image(str(path)))
                checked += 1
                correct += int(result["category"] == category)
        if checked:
            assert correct >= 0.8 * checked, f"YOLO named only {correct}/{checked} held-out photos correctly"
            print(f"YOLO classifier validated: {correct}/{checked} held-out photos named correctly.")
        else:
            print("YOLO classifier loads and runs (no held-out photos found to score).")

    print("\n==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY! (8/8)")
    print("==================================================")
    log_session_step("TESTS", "All 8 extended industrial suite verification tests passed.")

if __name__ == "__main__":
    run_tests()
