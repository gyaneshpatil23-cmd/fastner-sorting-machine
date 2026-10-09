"""
FILE: frontend/tab_camera_calibration.py

WHAT THIS FILE DOES
    Tab 5 'Camera Calibration': set the camera scale (millimetres per pixel) that converts
    pixel measurements into real sizes.

MAIN PARTS
    - Calibrate from a part: inspect a part, type its real size measured by hand, and the scale is worked out
    - Manual scale: type the millimetres-per-pixel value directly
    - Save to database / reset to default

USED BY
    frontend/main_window.py
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QDoubleSpinBox, QGroupBox, QMessageBox, QComboBox
)

from backend.sqlite_database import db_instance
from backend.opencv_measurement import dimension_engine
from backend.app_logging import log_session_step

# ============================================================================
# CALIBRATION TAB
# ============================================================================
class CameraCalibrationPanel(QWidget):
    """Interactive camera calibration interface."""
    calibration_updated = Signal(float)

    # The readings of an inspection that can be used as the known reference size
    REFERENCE_READINGS = [
        ("length_mm", "Length"),
        ("stem_dia_mm", "Shank diameter"),
        ("head_width_mm", "Head width"),
        ("inner_dia_mm", "Hole diameter"),
        ("outer_dia_mm", "Outer diameter"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_scale = None  # scale (mm/px) the last inspection was measured with
        self.init_ui()

    # ========================================================================
    # LAYOUT
    # ========================================================================
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ---------------- 1. Calibrate from a part measured by hand ----------------
        part_group = QGroupBox("CALIBRATE FROM A PART YOU HAVE MEASURED BY HAND")
        p_layout = QVBoxLayout(part_group)
        p_layout.setContentsMargins(14, 16, 14, 14)
        p_layout.setSpacing(12)

        part_desc = QLabel(
            "<b>Use this when the app's sizes are wrong:</b><br>"
            "1. Fix the camera in place, then inspect a part on the Live Inspection tab.<br>"
            "2. Measure the same part with a ruler or caliper and type the real size below.<br>"
            "3. Click the button. The scale is corrected so the app reads the real size.<br>"
            "The scale is only right for this camera distance: recalibrate if the camera or the part height moves."
        )
        part_desc.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.5;")
        part_desc.setWordWrap(True)
        p_layout.addWidget(part_desc)

        self.last_part_lbl = QLabel("No part inspected yet. Inspect a part on the Live Inspection tab first.")
        self.last_part_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        p_layout.addWidget(self.last_part_lbl)

        part_row = QHBoxLayout()
        part_row.addWidget(QLabel("Reading to correct:"))
        self.reading_combo = QComboBox()
        self.reading_combo.currentIndexChanged.connect(self._on_reading_selected)
        part_row.addWidget(self.reading_combo)
        part_row.addWidget(QLabel("Real size:"))
        self.true_size_spin = QDoubleSpinBox()
        self.true_size_spin.setRange(0.10, 1000.0)
        self.true_size_spin.setDecimals(2)
        self.true_size_spin.setSuffix(" mm")
        part_row.addWidget(self.true_size_spin)
        self.calibrate_btn = QPushButton("Set Scale from This Part")
        self.calibrate_btn.setStyleSheet("background-color: #15803D; color: white; font-weight: 700; padding: 8px 18px;")
        self.calibrate_btn.clicked.connect(self._on_calibrate_from_part)
        self.calibrate_btn.setEnabled(False)
        part_row.addWidget(self.calibrate_btn)
        part_row.addStretch()
        p_layout.addLayout(part_row)
        layout.addWidget(part_group)

        # ---------------- 2. Manual scale ----------------
        group = QGroupBox("MANUAL SCALE (MILLIMETRES PER PIXEL)")
        g_layout = QVBoxLayout(group)
        g_layout.setContentsMargins(14, 16, 14, 14)
        g_layout.setSpacing(12)

        desc = QLabel(
            "Every measurement is a pixel count multiplied by this scale. "
            "Type a value here only if you already know the scale for your camera setup."
        )
        desc.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.5;")
        desc.setWordWrap(True)
        g_layout.addWidget(desc)

        # Reference Input
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Reference size used (for the record):"))
        self.ref_spin = QDoubleSpinBox()
        self.ref_spin.setRange(1.0, 500.0)
        self.ref_spin.setValue(25.0)
        self.ref_spin.setSuffix(" mm")
        row1.addWidget(self.ref_spin)
        row1.addStretch()
        g_layout.addLayout(row1)

        # Current Scale Display
        curr_scale = db_instance.get_calibration("default")
        self.scale_lbl = QLabel(f"Current Calibrated Scale: <b>{curr_scale:.4f} mm / pixel</b>")
        self.scale_lbl.setStyleSheet("font-size: 13px; color: #2563EB; padding: 6px; background-color: #EFF6FF; border-radius: 4px;")
        g_layout.addWidget(self.scale_lbl)

        # Scale Spinbox for Manual Adjustment
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Manual Scale Factor (mm/px):"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.001, 10.0)
        self.scale_spin.setDecimals(4)
        self.scale_spin.setValue(curr_scale)
        row2.addWidget(self.scale_spin)
        row2.addStretch()
        g_layout.addLayout(row2)

        # Action Buttons
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save Calibration to Database")
        save_btn.setStyleSheet("background-color: #2563EB; color: white; font-weight: 700; padding: 8px 18px;")
        save_btn.clicked.connect(self._on_save_clicked)

        reset_btn = QPushButton("Reset to Default (0.125 mm/px)")
        reset_btn.clicked.connect(self._on_reset_clicked)

        btn_box.addWidget(save_btn)
        btn_box.addWidget(reset_btn)
        btn_box.addStretch()
        g_layout.addLayout(btn_box)

        layout.addWidget(group)
        layout.addStretch()

    # ========================================================================
    # CALIBRATE FROM A PART
    # new scale = old scale x (real size / size the app measured)
    # ========================================================================
    def set_last_measurement(self, result: dict):
        """Called by the main window after every inspection, so its readings can be used as the reference."""
        measurements = result.get("measurements", {})
        readings = [(label, float(result.get(key) or 0.0)) for key, label in self.REFERENCE_READINGS]
        readings = [(label, value) for label, value in readings if value > 0]

        self.reading_combo.blockSignals(True)
        self.reading_combo.clear()
        if not measurements.get("success") or not readings:
            self._last_scale = None
            self.last_part_lbl.setText("The last inspection has no measurements to calibrate from.")
            self.calibrate_btn.setEnabled(False)
            self.reading_combo.blockSignals(False)
            return

        self._last_scale = float(measurements.get("scale_mm_per_px") or db_instance.get_calibration("default"))
        for label, value in readings:
            self.reading_combo.addItem(f"{label} (app measured {value:.2f} mm)", value)
        # The longest reading gives the most accurate scale
        self.reading_combo.setCurrentIndex(max(range(len(readings)), key=lambda i: readings[i][1]))
        self.reading_combo.blockSignals(False)
        self._on_reading_selected()

        self.last_part_lbl.setText(
            f"Last inspected part: {result.get('category', 'part')}, measured at {self._last_scale:.4f} mm / pixel."
        )
        self.calibrate_btn.setEnabled(True)

    def _on_reading_selected(self, *_):
        measured = self.reading_combo.currentData()
        if measured:
            self.true_size_spin.setValue(float(measured))

    def _on_calibrate_from_part(self):
        measured = self.reading_combo.currentData()
        if not measured or not self._last_scale:
            return
        true_size = self.true_size_spin.value()
        new_scale = self._last_scale * true_size / float(measured)
        new_scale = min(max(new_scale, self.scale_spin.minimum()), self.scale_spin.maximum())

        self.scale_spin.setValue(new_scale)
        self.ref_spin.setValue(min(max(true_size, self.ref_spin.minimum()), self.ref_spin.maximum()))
        # The readings above were taken with the old scale, so they cannot be reused
        self.calibrate_btn.setEnabled(False)
        self.last_part_lbl.setText("Scale updated. Inspect the part again to check the new reading.")
        self._on_save_clicked()

    # ========================================================================
    # BUTTON ACTIONS
    # Save or reset the millimetres-per-pixel scale.
    # ========================================================================
    def _on_save_clicked(self):
        new_ratio = self.scale_spin.value()
        ref_mm = self.ref_spin.value()
        db_instance.set_calibration("default", new_ratio, ref_mm, "Manual/Reference calibrated")
        dimension_engine.reload_calibration()
        self.scale_lbl.setText(f"Current Calibrated Scale: <b>{new_ratio:.4f} mm / pixel</b>")
        self.calibration_updated.emit(new_ratio)
        log_session_step("CALIBRATION", f"Camera scale updated to {new_ratio:.4f} mm/px (Ref: {ref_mm}mm)")
        QMessageBox.information(self, "Calibration Saved", f"New scale ratio: {new_ratio:.4f} mm/pixel applied.")

    def _on_reset_clicked(self):
        self.scale_spin.setValue(0.125)
        self._on_save_clicked()
