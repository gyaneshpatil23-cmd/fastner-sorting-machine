"""
Verification and Test Suite for Complete Industrial AI Fastener Inspection System.
Validates Database, Persistent Counters, Hierarchical Specifications,
Emergency Stop (E-STOP), Calibrated Measurement, and PySide6 Master Workstation.
"""

import sys
import os
import cv2
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from backend.config import BASE_DIR, SAMPLE_IMAGES_DIR, ALLOWED_CATEGORIES
from backend.logger import app_logger, log_session_step
from backend.image_utils import generate_sample_dataset, load_image, cv_to_qpixmap
from backend.local_classifier import LocalFastenerClassifier
from backend.dimensional_measurement import dimension_engine
from backend.verification_engine import verification_engine
from backend.hardware_comm import hardware_manager
from backend.database import db_instance
from frontend.main_window import MainWindow

def run_tests():
    print("==================================================")
    print("RUNNING EXTENDED INDUSTRIAL SUITE TEST SUITE")
    print("==================================================")

    # Initialize Qt Application
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test SQLite Database & Persistent Batch Counters
    print("\n[1/7] Testing SQLite Database, Custom Sizes & Persistent Batch Counters...")
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
    print("\n[2/7] Testing Hardware Emergency Stop (E-STOP) Kill Switch...")
    hardware_manager.emergency_stop()
    assert hardware_manager._is_estopped, "E-Stop state not set"
    assert hardware_manager.telemetry["state"] == "EMERGENCY_STOP", "Telemetry state not EMERGENCY_STOP"
    hardware_manager.reset_estop()
    assert not hardware_manager._is_estopped, "E-Stop reset failed"
    assert hardware_manager.telemetry["state"] == "READY", "Telemetry state not READY after reset"
    print("Emergency Stop (E-STOP) hardware & software kill switch verified.")

    # 3. Test Sample Dataset Generation
    print("\n[3/7] Testing Sample Dataset Generator...")
    generate_sample_dataset(str(SAMPLE_IMAGES_DIR))
    sample_files = os.listdir(SAMPLE_IMAGES_DIR)
    assert len(sample_files) >= 4, "Expected at least 4 sample images"
    print(f"Samples: {sample_files}")

    # 4. Test Local Classifier & Calibrated Dimensional Measurements
    print("\n[4/7] Testing Local Classifier & Calibrated OpenCV Measurement...")
    local_clf = LocalFastenerClassifier()
    for filename in sample_files:
        filepath = os.path.join(SAMPLE_IMAGES_DIR, filename)
        img = load_image(filepath)
        assert img is not None, f"Failed loading {filename}"
        
        class_res = local_clf.classify(img)
        category = class_res["category"]
        assert category in ALLOWED_CATEGORIES, f"Invalid category: {class_res}"
        
        meas = dimension_engine.measure_fastener(img, category)
        assert meas["success"], f"Measurement failed for {filename}"
        print(f"  -> {filename}: {category} | Length: {meas.get('length_mm', 0):.1f}mm, Stem Dia: {meas.get('stem_dia_mm', 0):.1f}mm, Inner Dia: {meas.get('inner_dia_mm', 0):.1f}mm")

    # 5. Test Tolerance Verification & Tray Mapping
    print("\n[5/7] Testing Specification Matching & Dynamic Bin Decision Engine...")
    bolt_meas = {"success": True, "stem_dia_mm": 8.0, "length_mm": 40.0}
    verif = verification_engine.verify_and_decide("BOLT", 0.95, bolt_meas)
    assert verif["decision"] == "ACCEPT", f"Expected ACCEPT for standard M8 bolt, got {verif}"
    print(f"Decision verified: {verif['matched_size']} -> Decision: {verif['decision']} -> Bin {verif['assigned_tray']} (Angle: {verif['servo_angle']}°)")

    # 6. Test Hardware Simulator & Sorting Sequence
    print("\n[6/7] Testing ESP32 Hardware Simulator & Sorting Cycle...")
    hardware_manager.set_mode("SIMULATOR")
    assert hardware_manager._is_connected, "Hardware simulator failed to connect"
    hardware_manager.send_command({"command": "SORT", "tray": 2, "angle": 65})
    assert hardware_manager.telemetry["chute_angle"] == 65, "Chute angle update failed in simulator"
    print("ESP32 Hardware Simulation validated.")

    # 7. Test Master PySide6 Multi-Tab GUI Window Launch with E-STOP & Custom Tabs
    print("\n[7/7] Testing Master Desktop Window & All Workstation Tabs...")
    window = MainWindow()
    assert window.tabs.count() == 6, f"Expected 6 dashboard tabs, got {window.tabs.count()}"
    window.show()
    print("MainWindow with all 6 tabs, E-STOP banner, and persistent counters initialized.")

    # Auto close after 1 second
    QTimer.singleShot(1000, app.quit)
    app.exec()
    print("Master GUI event loop executed and exited cleanly.")

    print("\n==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY! (7/7)")
    print("==================================================")
    log_session_step("TESTS", "All 7 extended industrial suite verification tests passed.")

if __name__ == "__main__":
    run_tests()
