"""
Pixel-to-Millimeter Camera Calibration Panel for AI Fastener Inspection System.
Allows interactive calibration of overhead camera scale using known reference objects.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QDoubleSpinBox, QGroupBox, QMessageBox
)

from backend.database import db_instance
from backend.dimensional_measurement import dimension_engine
from backend.logger import log_session_step

class CameraCalibrationPanel(QWidget):
    """Interactive camera calibration interface."""
    calibration_updated = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        group = QGroupBox("CAMERA PIXEL-TO-MILLIMETER SCALE CALIBRATION")
        g_layout = QVBoxLayout(group)
        g_layout.setContentsMargins(14, 16, 14, 14)
        g_layout.setSpacing(12)

        desc = QLabel(
            "<b>Calibration Procedure:</b><br>"
            "1. Place a certified reference object (e.g. 25.0 mm calibration coin or gauge block) on the inspection pad.<br>"
            "2. Enter the known physical diameter/length below.<br>"
            "3. The system computes the optical magnification factor (mm/pixel) for all geometric measurements."
        )
        desc.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.5;")
        desc.setWordWrap(True)
        g_layout.addWidget(desc)

        # Reference Input
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Known Reference Size (mm):"))
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
