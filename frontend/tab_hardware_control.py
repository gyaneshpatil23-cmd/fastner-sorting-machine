"""
FILE: frontend/tab_hardware_control.py

WHAT THIS FILE DOES
    Tab 3 'Hardware & Sorting Chute': choose how to connect to the ESP32, watch its live status,
    and move each motor by hand for testing.

MAIN PARTS
    - Connection bar: Simulator / USB Serial / Wi-Fi
    - Live telemetry: state, servo angles, conveyor, battery
    - Manual tests: tilt pad, run conveyor, move chute

USED BY
    frontend/main_window.py
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QPushButton, QGroupBox, QComboBox, QSpinBox,
    QProgressBar, QMessageBox
)

from backend.esp32_communication import hardware_manager
from backend.sqlite_database import db_instance
from backend.app_logging import log_session_step

# ============================================================================
# HARDWARE TAB
# ============================================================================
class HardwareControlPanel(QWidget):
    """Interactive hardware dashboard and manual testing controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

        # Connect signals
        hardware_manager.telemetry_updated.connect(self._on_telemetry_updated)
        hardware_manager.cycle_progress.connect(self._on_cycle_progress)
        hardware_manager.connection_status_changed.connect(self._on_connection_status_changed)

        # Initial connect
        hardware_manager.connect_hardware()

    # ========================================================================
    # LAYOUT
    # Connection bar, live telemetry grid and manual test buttons.
    # ========================================================================
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ---------------- 1. Communication Link & Mode Bar ----------------
        link_group = QGroupBox("ESP32 HARDWARE COMMUNICATION LINK")
        link_layout = QHBoxLayout(link_group)
        link_layout.setContentsMargins(12, 12, 12, 12)
        link_layout.setSpacing(10)

        link_layout.addWidget(QLabel("Communication Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["SIMULATOR (Virtual ESP32)", "USB_SERIAL (pyserial)", "WIFI (TCP Socket)"])

        current_mode = db_instance.get_setting("comm_mode", "SIMULATOR")
        if current_mode == "USB_SERIAL":
            self.mode_combo.setCurrentIndex(1)
        elif current_mode == "WIFI":
            self.mode_combo.setCurrentIndex(2)
        else:
            self.mode_combo.setCurrentIndex(0)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        link_layout.addWidget(self.mode_combo)

        self.connect_btn = QPushButton("Reconnect Link")
        self.connect_btn.clicked.connect(hardware_manager.connect_hardware)
        link_layout.addWidget(self.connect_btn)

        link_layout.addStretch()

        self.link_status_lbl = QLabel("● Simulator Connected")
        self.link_status_lbl.setStyleSheet("font-weight: 700; color: #15803D;")
        link_layout.addWidget(self.link_status_lbl)

        layout.addWidget(link_group)

        # ---------------- 2. Live Telemetry & System Status Grid ----------------
        telem_group = QGroupBox("LIVE ESP32 TELEMETRY && SENSOR STATUS")
        telem_layout = QGridLayout(telem_group)
        telem_layout.setContentsMargins(12, 14, 12, 12)
        telem_layout.setHorizontalSpacing(14)
        telem_layout.setVerticalSpacing(8)

        # Telemetry Labels
        self.lbl_state = self._add_telem_item(telem_layout, "System State:", "READY", 0, 0, color="#15803D")
        self.lbl_chute_angle = self._add_telem_item(telem_layout, "Chute Servo Angle:", "0°", 0, 2)
        self.lbl_pad_angle = self._add_telem_item(telem_layout, "Pad Tilt Servo:", "0° (Flat)", 1, 0)
        self.lbl_conveyor = self._add_telem_item(telem_layout, "Conveyor Motor:", "STOPPED", 1, 2)
        self.lbl_battery = self._add_telem_item(telem_layout, "3S2P Battery Pack:", "12.4 V (95%)", 2, 0, color="#059669")
        self.lbl_active_tray = self._add_telem_item(telem_layout, "Target Sorting Tray:", "Tray 1", 2, 2)

        layout.addWidget(telem_group)

        # Sequence Progress Bar
        self.progress_group = QGroupBox("AUTOMATED SORTING CYCLE PROGRESS")
        p_layout = QVBoxLayout(self.progress_group)
        self.progress_label = QLabel("Inspection Pad & Chute Ready")
        self.progress_label.setStyleSheet("font-weight: 600; color: #334155;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #2563EB; border-radius: 3px; }")
        p_layout.addWidget(self.progress_label)
        p_layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_group)

        # ---------------- 3. Manual Actuator Testing Controls ----------------
        actuator_group = QGroupBox("MANUAL ACTUATOR && MECHANISM TEST CONTROLS")
        act_layout = QGridLayout(actuator_group)
        act_layout.setContentsMargins(12, 14, 12, 12)
        act_layout.setHorizontalSpacing(12)
        act_layout.setVerticalSpacing(10)

        # Pad Tilt Test
        act_layout.addWidget(QLabel("Inspection Pad Tilt (MG996R):"), 0, 0)
        tilt_btn_45 = QPushButton("Tilt to 45°")
        tilt_btn_45.clicked.connect(lambda: hardware_manager.send_command({"command": "TILT_PAD", "angle": 45}))
        tilt_btn_0 = QPushButton("Return Home (0°)")
        tilt_btn_0.clicked.connect(lambda: hardware_manager.send_command({"command": "TILT_PAD", "angle": 0}))
        act_layout.addWidget(tilt_btn_45, 0, 1)
        act_layout.addWidget(tilt_btn_0, 0, 2)

        # Conveyor Stepper Test
        act_layout.addWidget(QLabel("Conveyor Belt (NEMA 17 + TB6600):"), 1, 0)
        conv_run_btn = QPushButton("Run Conveyor (1.5s)")
        conv_run_btn.clicked.connect(lambda: hardware_manager.send_command({"command": "CONVEYOR", "action": "RUN", "duration_ms": 1500}))
        conv_stop_btn = QPushButton("Stop Conveyor")
        conv_stop_btn.clicked.connect(lambda: hardware_manager.send_command({"command": "CONVEYOR", "action": "STOP"}))
        act_layout.addWidget(conv_run_btn, 1, 1)
        act_layout.addWidget(conv_stop_btn, 1, 2)

        # Rotating Chute Angle Test
        act_layout.addWidget(QLabel("Rotating Chute Angle (18° - 180°):"), 2, 0)
        self.chute_angle_spin = QSpinBox()
        self.chute_angle_spin.setRange(0, 180)
        self.chute_angle_spin.setValue(45)
        self.chute_angle_spin.setSuffix("°")
        rotate_btn = QPushButton("Move Chute to Angle")
        rotate_btn.clicked.connect(self._on_move_chute_clicked)
        act_layout.addWidget(self.chute_angle_spin, 2, 1)
        act_layout.addWidget(rotate_btn, 2, 2)

        layout.addWidget(actuator_group)
        layout.addStretch()

    def _add_telem_item(self, grid, title, default_val, r, c, color="#0F172A"):
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        v_lbl = QLabel(default_val)
        v_lbl.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {color};")
        grid.addWidget(t_lbl, r, c)
        grid.addWidget(v_lbl, r, c + 1)
        return v_lbl

    # ========================================================================
    # BUTTON ACTIONS
    # ========================================================================
    def _on_mode_changed(self, index: int):
        modes = ["SIMULATOR", "USB_SERIAL", "WIFI"]
        selected = modes[index]
        hardware_manager.set_mode(selected)

    def _on_move_chute_clicked(self):
        angle = self.chute_angle_spin.value()
        hardware_manager.send_command({"command": "SORT", "tray": 0, "angle": angle})

    # ========================================================================
    # LIVE UPDATES
    # Called whenever the hardware manager reports new status.
    # ========================================================================
    def _on_telemetry_updated(self, telem: dict):
        self.lbl_state.setText(telem.get("state", "READY"))
        self.lbl_chute_angle.setText(f"{telem.get('chute_angle', 0)}°")
        self.lbl_pad_angle.setText(f"{telem.get('pad_angle', 0)}°")
        self.lbl_conveyor.setText("RUNNING" if telem.get("conveyor") else "STOPPED")
        self.lbl_battery.setText(f"{telem.get('battery_voltage', 12.4):.1f} V ({telem.get('battery_percent', 95)}%)")
        self.lbl_active_tray.setText(f"Tray {telem.get('active_tray', 0)}")

    def _on_cycle_progress(self, step_name: str, percent: int):
        self.progress_label.setText(step_name)
        self.progress_bar.setValue(percent)

    def _on_connection_status_changed(self, connected: bool, message: str):
        if connected:
            self.link_status_lbl.setText(f"● {message}")
            self.link_status_lbl.setStyleSheet("font-weight: 700; color: #15803D;")
        else:
            self.link_status_lbl.setText(f"● {message}")
            self.link_status_lbl.setStyleSheet("font-weight: 700; color: #DC2626;")
