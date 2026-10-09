"""
FILE: frontend/main_window.py

WHAT THIS FILE DOES
    The main application window: the header bar, the six tabs and the status bar.
    It also owns Tab 1 (Live Inspection) and connects the buttons to the backend.

MAIN PARTS
    - Header: bins summary, camera selector, Settings button, EMERGENCY STOP
    - Tab 1 Live Inspection: image view, Open File / Load Sample / Live Video, the INSPECT button,
      and the 'Sort by Type Only' option (bin chosen from the fastener type; size not judged)
    - 'Save Photo for Training': saves the camera picture, labelled, for retraining the YOLO model
    - Tabs 2-6 are built in their own files (tab_*.py)
    - Camera handling, running an inspection, showing the result, emergency stop

USED BY
    main.py
    run_all_tests.py
"""

import os
import glob
from datetime import datetime
from typing import Optional, List
import cv2
import numpy as np

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QAction, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSplitter, QFileDialog, QMessageBox,
    QStatusBar, QComboBox, QMenu, QToolButton, QTabWidget,
    QCheckBox, QScrollArea, QSizePolicy
)

from backend.app_config import (
    CATEGORY_UNKNOWN, APP_TITLE, APP_SUBTITLE, APP_VERSION, DEFAULT_MODEL,
    SAMPLE_IMAGES_DIR, SUPPORTED_IMAGE_EXTENSIONS, get_gemini_api_key,
    MODEL_LOCAL_OFFLINE, MODEL_YOLO, PREFER_BUILT_IN_CAMERA, get_startup_model,
    CAMERA_PHOTOS_DIR, TRAINING_CLASSES
)
from backend.app_logging import app_logger, log_session_step
from backend.camera_capture import CameraThread, scan_available_cameras, get_preferred_camera_index
from backend.inspection_pipeline import FastenerClassifierManager
from backend.opencv_measurement import dimension_engine
from backend.opencv_shape_classifier import LocalFastenerClassifier
from backend.tolerance_and_bin_decision import verification_engine
from backend.esp32_communication import hardware_manager
from backend.sqlite_database import db_instance
from backend.image_loading_and_overlays import (
    load_image, cv_to_qpixmap, generate_sample_dataset, draw_classification_overlay
)
from backend.yolo_classifier import yolo_classifier

from frontend.inspection_result_panel import ResultPanel
from frontend.tab_inspection_history import HistoryPanel
from frontend.tab_hardware_control import HardwareControlPanel
from frontend.tab_iso_specifications import SpecificationPanel
from frontend.tab_bins_and_chute_angles import TraysConfigurationPanel
from frontend.tab_camera_calibration import CameraCalibrationPanel
from frontend.ai_settings_dialog import SettingsDialog
from frontend.app_stylesheet import MAIN_STYLESHEET


# ============================================================================
# WINDOW CONSTANTS
# ============================================================================
# "&&" renders as a literal "&" on buttons (a single "&" would be read as a shortcut marker)
ANALYZE_BTN_TEXT = "🔬  INSPECT, MEASURE && SORT FASTENER"

# Window size used on displays large enough to hold it; smaller displays get a maximized window
PREFERRED_WINDOW_SIZE = QSize(1280, 880)

# ============================================================================
# MAIN WINDOW
# ============================================================================
class MainWindow(QMainWindow):
    """Main industrial inspection desktop workstation window."""

    # ========================================================================
    # STARTUP
    # Create the backend engines, build the UI and connect the signals.
    # ========================================================================
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} - {APP_VERSION}")
        self._fit_to_screen()

        # State
        self.current_model = get_startup_model()
        self.current_cv_image: Optional[np.ndarray] = None
        self.last_inspection_result: Optional[dict] = None
        self.multi_fastener_mode = False

        # Ensure sample dataset exists
        generate_sample_dataset(str(SAMPLE_IMAGES_DIR))

        # Core Engines
        self.classifier_manager = FastenerClassifierManager(self)
        self.classifier_manager.inspection_completed.connect(self._on_inspection_completed)
        self.classifier_manager.counters_updated.connect(self._on_counters_updated)
        hardware_manager.cycle_progress.connect(self._on_sort_cycle_progress)

        self.camera_thread: Optional[CameraThread] = None

        self.init_ui()
        self.setStyleSheet(MAIN_STYLESHEET)
        self.update_ai_status_indicator()
        self._update_bins_profile_header()

        # Load and display persistent batch statistics from SQLite
        self.result_panel.update_counters(self.classifier_manager.counters)

        log_session_step("STARTUP", "Industrial Fastener Inspection Workstation initialized.")

    # ========================================================================
    # WINDOW SIZING
    # ========================================================================
    def _fit_to_screen(self):
        """Sizes the window from the display's usable area (excluding the taskbar)."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(PREFERRED_WINDOW_SIZE)
            return
        avail = screen.availableGeometry()
        self.setMinimumSize(min(800, avail.width()), min(520, avail.height()))

        # Leave room for the title bar and window borders
        width = min(PREFERRED_WINDOW_SIZE.width(), int(avail.width() * 0.94))
        height = min(PREFERRED_WINDOW_SIZE.height(), int(avail.height() * 0.90))
        self.resize(width, height)
        self.move(
            avail.x() + (avail.width() - width) // 2,
            avail.y() + max(0, (avail.height() - height) // 3)
        )

    def show_fitted(self):
        """Shows the window maximized when the display is too small for the preferred size."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is not None and (
            avail.width() < PREFERRED_WINDOW_SIZE.width() + 80
            or avail.height() < PREFERRED_WINDOW_SIZE.height() + 80
        ):
            self.showMaximized()
        else:
            self.show()

    def showEvent(self, event):
        super().showEvent(event)
        # Child styles are only final once the window is shown
        self._lock_result_panel_width()

    def _lock_result_panel_width(self):
        """Keeps the result column wide enough for its readouts so it only scrolls vertically."""
        content = self.result_scroll.widget()
        scrollbar_width = self.result_scroll.verticalScrollBar().sizeHint().width()
        self.result_scroll.setMinimumWidth(content.minimumSizeHint().width() + scrollbar_width + 4)

    @staticmethod
    def _make_scrollable(content: QWidget) -> QScrollArea:
        """Wraps a panel so it scrolls instead of forcing the window past the screen edge."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    # ========================================================================
    # LAYOUT
    # Header bar, the six tabs and the status bar.
    # ========================================================================
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # ---------------- 1. Top Industrial Telemetry Header ----------------
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_frame.setStyleSheet(
            "#headerFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; }"
            "#headerFrame QLabel { background: transparent; border: none; }"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(12)

        # Title Block
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(1)
        title_lbl = QLabel(APP_TITLE.upper())
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #0F172A; letter-spacing: 0.5px;")
        subtitle_lbl = QLabel("Industrial Fastener Classification, Calibrated OpenCV Sizing & ESP32 Sorting")
        subtitle_lbl.setStyleSheet("font-size: 10px; color: #64748B; font-weight: 600;")
        # Shown in full when there is room, but allowed to shrink on narrow displays
        subtitle_lbl.setMinimumWidth(1)
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        # Dynamic Bins Profile Pill
        self.bins_profile_lbl = QLabel("📦 Active Bins: 4 Configured")
        self.bins_profile_lbl.setStyleSheet(
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; color: #1E293B; "
            "font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 4px;"
        )
        header_layout.addWidget(self.bins_profile_lbl)

        # Camera Device Selector Dropdown
        self.camera_caption_lbl = QLabel("Camera:")
        header_layout.addWidget(self.camera_caption_lbl)
        self.camera_combo = QComboBox()
        self._populate_camera_devices()
        header_layout.addWidget(self.camera_combo)

        cam_refresh_btn = QPushButton("🔄")
        cam_refresh_btn.setToolTip("Scan Video Capture Devices")
        cam_refresh_btn.clicked.connect(self._populate_camera_devices)
        header_layout.addWidget(cam_refresh_btn)

        # Settings button
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setStyleSheet("font-weight: 600; padding: 5px 12px;")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        header_layout.addWidget(self.settings_btn)

        # Prominent Emergency Stop (E-STOP) Button
        self.estop_btn = QPushButton("🛑 EMERGENCY STOP")
        self.estop_btn.setStyleSheet(
            "background-color: #DC2626; color: #FFFFFF; font-weight: 900; font-size: 12px; "
            "padding: 6px 16px; border: 2px solid #991B1B; border-radius: 4px;"
        )
        self.estop_btn.clicked.connect(self._toggle_emergency_stop)
        header_layout.addWidget(self.estop_btn)

        main_layout.addWidget(header_frame)

        # Emergency Warning Banner (Hidden by default)
        self.estop_banner = QFrame()
        self.estop_banner.setVisible(False)
        self.estop_banner.setObjectName("estopBanner")
        self.estop_banner.setStyleSheet(
            "#estopBanner { background-color: #FEF2F2; border: 2px solid #DC2626; border-radius: 4px; }"
            "#estopBanner QLabel { background: transparent; border: none; }"
        )
        eb_layout = QHBoxLayout(self.estop_banner)
        eb_layout.setContentsMargins(12, 6, 12, 6)
        eb_lbl = QLabel("⚠️ EMERGENCY STOP ACTIVATED — All hardware motion halted. Clear obstructions before reset.")
        eb_lbl.setStyleSheet("color: #DC2626; font-weight: 800; font-size: 12px;")
        eb_layout.addWidget(eb_lbl)
        eb_layout.addStretch()
        self.reset_estop_btn = QPushButton("✅ RESET E-STOP (RECOVER)")
        self.reset_estop_btn.setStyleSheet("background-color: #15803D; color: white; font-weight: 800; padding: 4px 12px;")
        self.reset_estop_btn.clicked.connect(self._reset_emergency_stop)
        eb_layout.addWidget(self.reset_estop_btn)
        main_layout.addWidget(self.estop_banner)

        # ---------------- 2. Master Multi-Tab Workstation ----------------
        self.tabs = QTabWidget()

        # Tab 1: Vision Inspection & Dimensional Workstation
        self.tab_inspection = self._build_inspection_tab()
        self.tabs.addTab(self.tab_inspection, "🔬 Live Inspection Workstation")

        # Tab 2: Customizable Sorting Bins & Chute Angles
        self.tab_trays = TraysConfigurationPanel()
        self.tab_trays.bins_configuration_changed.connect(self._update_bins_profile_header)
        self.tabs.addTab(self._make_scrollable(self.tab_trays), "📦 Custom Bins && Chute Angles")

        # Tab 3: Hardware & Motion Controller (ESP32)
        self.tab_hardware = HardwareControlPanel()
        self.tabs.addTab(self._make_scrollable(self.tab_hardware), "⚙ Hardware && Sorting Chute")

        # Tab 4: Fastener Specifications Database
        self.tab_specs = SpecificationPanel()
        self.tabs.addTab(self._make_scrollable(self.tab_specs), "📐 ISO Specifications")

        # Tab 5: Camera Scale Calibration
        self.tab_calib = CameraCalibrationPanel()
        self.tabs.addTab(self._make_scrollable(self.tab_calib), "🎯 Camera Calibration")

        # Tab 6: Inspection History Audit
        self.tab_history = HistoryPanel()
        self.tab_history.clear_history_requested.connect(self.classifier_manager.clear_history)
        self.tabs.addTab(self._make_scrollable(self.tab_history), "📋 Quality Audit History")

        main_layout.addWidget(self.tabs, 1)

        # ---------------- 3. Status Bar ----------------
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.cam_status_lbl = QLabel("Camera: ● Off")
        self.cam_status_lbl.setStyleSheet("color: #64748B; margin-right: 16px;")

        self.hw_status_lbl = QLabel("ESP32: ● Simulator Ready")
        self.hw_status_lbl.setStyleSheet("color: #15803D; font-weight: 600; margin-right: 16px;")

        self.ai_status_lbl = QLabel("AI: ● Local Offline Vision Engine")
        self.ai_status_lbl.setStyleSheet("color: #1D4ED8; font-weight: 600; margin-right: 16px;")

        self.sys_status_lbl = QLabel("System: ● Ready")
        self.sys_status_lbl.setStyleSheet("color: #15803D; font-weight: 600;")

        self.status_bar.addWidget(self.cam_status_lbl)
        self.status_bar.addWidget(self.hw_status_lbl)
        self.status_bar.addWidget(self.ai_status_lbl)
        self.status_bar.addPermanentWidget(self.sys_status_lbl)

    # ========================================================================
    # TAB 1 LAYOUT
    # Image view, toolbar buttons and the result panel.
    # ========================================================================
    def _build_inspection_tab(self) -> QWidget:
        """Constructs Tab 1: Clean workstation with viewport, action toolbar, and dimensional card."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Column (Inspection Viewport + Toolbar)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Viewport Card (Solid Dark Matte Bezel)
        viewport_card = QFrame()
        viewport_card.setStyleSheet("background-color: #0B1120; border: 1px solid #334155; border-radius: 6px;")
        vp_layout = QVBoxLayout(viewport_card)
        vp_layout.setContentsMargins(4, 4, 4, 4)

        self.image_viewport = QLabel("NO IMAGE LOADED\n\nOpen an image file, load a fastener sample, or start camera capture.")
        self.image_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_viewport.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: 500;")
        self.image_viewport.setMinimumSize(320, 200)
        vp_layout.addWidget(self.image_viewport)
        left_layout.addWidget(viewport_card, 1)

        # Action Toolbar Row
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(6)

        self.open_img_btn = QPushButton("📁 Open File")
        self.open_img_btn.clicked.connect(self._open_image_file)
        ctrl_bar.addWidget(self.open_img_btn)

        self.sample_btn = QToolButton()
        self.sample_btn.setText("⚡ Load Sample ▾")
        self.sample_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._build_sample_menu()
        ctrl_bar.addWidget(self.sample_btn)

        self.start_cam_btn = QPushButton("🎥 Live Video")
        self.start_cam_btn.setObjectName("cameraActionBtn")
        self.start_cam_btn.clicked.connect(self._start_camera)
        ctrl_bar.addWidget(self.start_cam_btn)

        self.capture_btn = QPushButton("📸 Freeze / Capture")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_camera_frame)
        ctrl_bar.addWidget(self.capture_btn)

        self.stop_cam_btn = QPushButton("⏹ Stop")
        self.stop_cam_btn.setEnabled(False)
        self.stop_cam_btn.clicked.connect(self._stop_camera)
        ctrl_bar.addWidget(self.stop_cam_btn)

        left_layout.addLayout(ctrl_bar)

        # Options Row
        opt_bar = QHBoxLayout()
        self.auto_sort_cb = QCheckBox("Auto Physical Sort Cycle (Tilt Pad -> Conveyor -> Chute)")
        self.auto_sort_cb.setChecked(True)
        self.auto_sort_cb.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px;")

        # Sort by type only: the part is named, measured and sent to the bin for its type, but its size
        # is not judged against tolerances. Use it while the camera is uncalibrated (laptop camera).
        self.identify_only_cb = QCheckBox("Sort by Type Only (skip size check)")
        self.identify_only_cb.setToolTip(
            "Ticked: the bin is chosen from the fastener type and sizes are shown as approximate.\n"
            "Unticked: sizes are checked against the ISO tolerances (needs a calibrated camera)."
        )
        self.identify_only_cb.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px;")
        self.identify_only_cb.setChecked(db_instance.get_setting("identify_only", "1") == "1")
        self.identify_only_cb.stateChanged.connect(self._on_identify_only_changed)

        self.multi_obj_cb = QCheckBox("Multi-Fastener Area Scan")
        self.multi_obj_cb.stateChanged.connect(self._on_multi_mode_changed)
        self.multi_obj_cb.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px;")

        opt_bar.addWidget(self.identify_only_cb)
        opt_bar.addWidget(self.auto_sort_cb)
        opt_bar.addStretch()
        opt_bar.addWidget(self.multi_obj_cb)
        left_layout.addLayout(opt_bar)

        # Training Photo Row: save what the camera sees, labelled with what it really is,
        # so the YOLO model can be retrained on this camera, these parts and this lighting
        teach_bar = QHBoxLayout()
        teach_lbl = QLabel("Teach the model - this picture shows:")
        teach_lbl.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px;")
        self.teach_class_combo = QComboBox()
        self.teach_class_combo.addItems(TRAINING_CLASSES)
        self.teach_class_combo.currentTextChanged.connect(self._update_training_photo_count)

        self.teach_save_btn = QPushButton("💾 Save Photo for Training")
        self.teach_save_btn.setToolTip("Hold the button down during live video to save several photos per second.")
        self.teach_save_btn.setAutoRepeat(True)
        self.teach_save_btn.setAutoRepeatDelay(500)
        self.teach_save_btn.setAutoRepeatInterval(350)
        self.teach_save_btn.clicked.connect(self._save_training_photo)

        self.teach_count_lbl = QLabel()
        self.teach_count_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        self._last_saved_frame = None
        self._update_training_photo_count()

        teach_bar.addWidget(teach_lbl)
        teach_bar.addWidget(self.teach_class_combo)
        teach_bar.addWidget(self.teach_save_btn)
        teach_bar.addWidget(self.teach_count_lbl)
        teach_bar.addStretch()
        left_layout.addLayout(teach_bar)

        # Prominent Primary Action Button
        self.analyze_btn = QPushButton(ANALYZE_BTN_TEXT)
        self.analyze_btn.setObjectName("primaryActionBtn")
        self.analyze_btn.setMinimumHeight(42)
        self.analyze_btn.clicked.connect(self._analyze_current_image)
        left_layout.addWidget(self.analyze_btn)

        splitter.addWidget(left_widget)

        # Right Column (Dimensional Result & Machine Routing Card)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.result_panel = ResultPanel()
        self.result_panel.reset_counters_requested.connect(self.classifier_manager.reset_counters)
        right_layout.addWidget(self.result_panel)
        right_layout.addStretch()

        self.result_scroll = self._make_scrollable(right_widget)
        splitter.addWidget(self.result_scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        return widget

    # ========================================================================
    # HEADER HELPERS
    # Bins summary, camera list and the sample menu.
    # ========================================================================
    def _update_bins_profile_header(self):
        """Updates top header pill with current active bin count and span."""
        trays = db_instance.get_trays(enabled_only=True)
        if not trays:
            trays = db_instance.get_trays()[:4]
        min_a = min([t["servo_angle"] for t in trays]) if trays else 0
        max_a = max([t["servo_angle"] for t in trays]) if trays else 180
        self.bins_profile_lbl.setText(f"📦 Active Bins: {len(trays)} Configured ({min_a}° - {max_a}°)")

    def _populate_camera_devices(self):
        self.camera_combo.clear()
        cams = scan_available_cameras()
        # Start on the built-in camera while PREFER_BUILT_IN_CAMERA is set,
        # otherwise on the highest-numbered external camera when one is plugged in
        external = [c["index"] for c in cams if c.get("is_external")]
        preferred_idx = external[-1] if external and not PREFER_BUILT_IN_CAMERA else 0
        select_idx = 0

        for i, c in enumerate(cams):
            self.camera_combo.addItem(c["name"], c["index"])
            if c["index"] == preferred_idx:
                select_idx = i

        self.camera_combo.setCurrentIndex(select_idx)

    def _build_sample_menu(self):
        menu = QMenu(self)
        samples = [
            ("Hex Bolt Sample (M8 x 40)", "sample_02_hex_bolt.png"),
            ("Hex Nut Sample (M8 Nut)", "sample_01_hex_nut.png"),
            ("Wood Screw Sample (M4 x 20)", "sample_03_wood_screw.png"),
            ("Flat Washer Sample (M8 Washer)", "sample_04_flat_washer.png"),
        ]
        for name, filename in samples:
            filepath = SAMPLE_IMAGES_DIR / filename
            action = QAction(name, self)
            action.triggered.connect(lambda ch=False, p=str(filepath): self._load_image_from_path(p))
            menu.addAction(action)

        custom_files = []
        for ext in SUPPORTED_IMAGE_EXTENSIONS:
            custom_files.extend(glob.glob(str(SAMPLE_IMAGES_DIR / f"*{ext}")))
        sample_basenames = [s[1] for s in samples]
        extras = [f for f in custom_files if os.path.basename(f) not in sample_basenames]
        if extras:
            menu.addSeparator()
            for ext_file in extras:
                action = QAction(f"Custom: {os.path.basename(ext_file)}", self)
                action.triggered.connect(lambda ch=False, p=ext_file: self._load_image_from_path(p))
                menu.addAction(action)

        self.sample_btn.setMenu(menu)

    # ========================================================================
    # IMAGE SOURCE
    # Open an image file or load a built-in sample.
    # ========================================================================
    def _open_image_file(self):
        ext_filter = "Images (*.jpg *.jpeg *.png *.bmp *.webp);;All Files (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Fastener Image", "", ext_filter)
        if filepath:
            self._load_image_from_path(filepath)

    def _load_image_from_path(self, filepath: str):
        self._stop_camera()
        img = load_image(filepath)
        if img is None:
            QMessageBox.warning(self, "Image Error", f"Could not load image:\n{filepath}")
            return

        self.current_cv_image = img
        self.last_inspection_result = None
        self._display_cv_image(self.current_cv_image)
        self.sys_status_lbl.setText(f"System: ● Loaded {os.path.basename(filepath)}")
        log_session_step("IMAGE", f"Loaded image file: {os.path.basename(filepath)}")

    # ========================================================================
    # LIVE CAMERA
    # Start video, receive frames, freeze a frame, stop.
    # ========================================================================
    def _start_camera(self):
        if hardware_manager.is_estopped:
            return
        if self.camera_thread and self.camera_thread.isRunning():
            return

        cam_idx = self.camera_combo.currentData() or 0
        self.camera_thread = CameraThread(camera_index=cam_idx, parent=self)
        self.camera_thread.frame_received.connect(self._on_camera_frame)
        self.camera_thread.camera_started.connect(self._on_camera_started)
        self.camera_thread.camera_stopped.connect(self._on_camera_stopped)
        self.camera_thread.error_occurred.connect(self._on_camera_error)
        self.camera_thread.start()

    def _on_camera_started(self, active_index: int):
        self.start_cam_btn.setEnabled(False)
        self.capture_btn.setEnabled(True)
        self.stop_cam_btn.setEnabled(True)
        self.cam_status_lbl.setText(f"Camera #{active_index}: ● Streaming Live")
        self.cam_status_lbl.setStyleSheet("color: #059669; font-weight: 600; margin-right: 16px;")
        self.sys_status_lbl.setText(f"System: ● Camera #{active_index} active")

    def _on_camera_stopped(self):
        self.start_cam_btn.setEnabled(True)
        self.capture_btn.setEnabled(False)
        self.stop_cam_btn.setEnabled(False)
        self.cam_status_lbl.setText("Camera: ● Off")
        self.cam_status_lbl.setStyleSheet("color: #64748B; margin-right: 16px;")

    def _on_camera_error(self, err_msg: str):
        self._stop_camera()
        QMessageBox.warning(self, "Camera Warning", f"{err_msg}\n\nYou can still use 'Open File' or 'Load Sample'.")

    def _on_camera_frame(self, frame: np.ndarray):
        if self.camera_thread is None:
            # A frame that was already queued when the camera was stopped
            return
        self.current_cv_image = frame
        self.last_inspection_result = None
        self._display_cv_image(frame)

    def _capture_camera_frame(self):
        if self.camera_thread and self.camera_thread.is_streaming():
            frame = self.camera_thread.get_latest_frame()
            self._stop_camera()
            if frame is not None:
                self.current_cv_image = frame
                self.last_inspection_result = None
                self._display_cv_image(self.current_cv_image)
                self.sys_status_lbl.setText("System: ● Frame captured")

    def _stop_camera(self):
        # isRunning() also covers a thread that is still opening the device
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.stop()
        self.camera_thread = None

    # ========================================================================
    # TRAINING PHOTOS
    # Save the current camera picture into my_camera_photos/<CLASS>/ for retraining the YOLO model.
    # ========================================================================
    def _update_training_photo_count(self, *_):
        folder = CAMERA_PHOTOS_DIR / self.teach_class_combo.currentText()
        count = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
        self.teach_count_lbl.setText(f"{count} saved for {self.teach_class_combo.currentText()}")

    def _save_training_photo(self):
        frame = self.current_cv_image
        if frame is None or frame.size == 0:
            QMessageBox.information(self, "No Picture", "Start Live Video or open an image first.")
            return
        if frame is self._last_saved_frame:
            # A still picture is saved once; during live video every frame is a new picture
            self.sys_status_lbl.setText("System: ● This picture is already saved")
            return

        label = self.teach_class_combo.currentText()
        folder = CAMERA_PHOTOS_DIR / label
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            self.sys_status_lbl.setText("System: ● Could not save the training photo")
            return
        encoded.tofile(str(target))  # handles spaces and non-English characters in the path

        self._last_saved_frame = frame
        self._update_training_photo_count()
        self.sys_status_lbl.setText(f"System: ● Training photo saved as {label}")

    # ========================================================================
    # IMAGE DISPLAY
    # ========================================================================
    def _display_cv_image(self, cv_img: np.ndarray):
        if cv_img is None or cv_img.size == 0:
            return
        pixmap = cv_to_qpixmap(cv_img)
        scaled_pixmap = pixmap.scaled(
            self.image_viewport.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_viewport.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Drop secondary header items on narrow displays so the title and E-STOP stay readable
        self.camera_caption_lbl.setVisible(self.width() >= 1260)
        self.bins_profile_lbl.setVisible(self.width() >= 1120)
        if self.last_inspection_result:
            self._show_inspection_overlay(self.last_inspection_result)
        elif self.current_cv_image is not None:
            self._display_cv_image(self.current_cv_image)

    def _show_inspection_overlay(self, result: dict):
        """Draws the measurement overlay on the exact frame that was inspected."""
        inspected = result.get("raw_image")
        if inspected is None:
            inspected = self.current_cv_image
        if not result.get("measurements", {}).get("success"):
            # Nothing could be measured, so only the box and the category label are drawn
            self._display_cv_image(draw_classification_overlay(
                inspected, result.get("category", CATEGORY_UNKNOWN), float(result.get("confidence", 0.0)),
                roi=result.get("measurements", {}).get("bbox")
            ))
            return
        annotated = dimension_engine.draw_calibrated_overlay(
            inspected,
            result.get("measurements", {}),
            decision=result.get("decision", "REJECT"),
            target_tray=result.get("assigned_tray", 0)
        )
        self._display_cv_image(annotated)

    # ========================================================================
    # RUN AN INSPECTION
    # What happens when the big INSPECT button is pressed.
    # ========================================================================
    def _on_identify_only_changed(self, state):
        identify_only = self.identify_only_cb.isChecked()
        db_instance.set_setting("identify_only", "1" if identify_only else "0")
        log_session_step("CONFIG", f"Sort-by-type-only mode: {identify_only}")

    def _on_multi_mode_changed(self, state):
        self.multi_fastener_mode = (state == Qt.CheckState.Checked.value or state == 2)
        log_session_step("CONFIG", f"Multi-fastener inspection mode: {self.multi_fastener_mode}")

    def _analyze_current_image(self):
        if self.current_cv_image is None or self.current_cv_image.size == 0:
            QMessageBox.information(self, "No Image", "Please load an image or start camera capture first.")
            return

        if hardware_manager.is_estopped:
            QMessageBox.warning(self, "E-STOP Active", "Reset the emergency stop before inspecting.")
            return

        # Inspecting from live video freezes the current frame, so the result stays on screen
        if self.camera_thread and self.camera_thread.isRunning():
            self._capture_camera_frame()

        identify_only = self.identify_only_cb.isChecked()
        if self.multi_fastener_mode and not identify_only:
            self._process_multi_fasteners()
            return

        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("⏳ INSPECTING && MEASURING...")
        self.result_panel.set_analyzing_state()
        self.sys_status_lbl.setText(
            "System: ● Identifying type, measuring & choosing bin..." if identify_only
            else "System: ● Measuring dimensions & verifying tolerances..."
        )

        auto_sort = self.auto_sort_cb.isChecked()
        worker = self.classifier_manager.start_classification(
            self.current_cv_image,
            self.current_model,
            auto_sort=auto_sort,
            identify_only=identify_only
        )
        if worker:
            worker.error.connect(self._on_inspection_error)
        else:
            # A previous inspection is still running; don't leave the button stuck
            self._restore_analyze_button()
            self.sys_status_lbl.setText("System: ● Previous inspection still running")

    def _restore_analyze_button(self):
        self.analyze_btn.setText(ANALYZE_BTN_TEXT)
        # Stay locked out while the emergency stop is latched
        self.analyze_btn.setEnabled(not hardware_manager.is_estopped)

    def _process_multi_fasteners(self):
        """Classifies, measures and verifies every object in view. Display only: nothing is logged or sorted."""
        image = self.current_cv_image
        objects = dimension_engine.detect_multiple_fasteners(image)
        if not objects:
            QMessageBox.information(self, "Multi Inspection", "No distinct fastener objects found in inspection area.")
            return

        classifier = LocalFastenerClassifier()
        annotated = image.copy()
        tally = {"ACCEPT": 0, "REINSPECT": 0, "REJECT": 0}

        for obj in objects:
            rx, ry, rw, rh = obj["roi_bbox"]
            class_res = classifier.classify(image[ry:ry + rh, rx:rx + rw])
            category = class_res.get("category", CATEGORY_UNKNOWN)
            meas = dimension_engine.measure_fastener(image, category, roi_bbox=obj["roi_bbox"])
            verif = verification_engine.verify_and_decide(category, float(class_res.get("confidence", 0.0)), meas)
            if verif.get("unrecognized"):
                meas["category"] = CATEGORY_UNKNOWN

            decision = verif.get("decision", "REJECT")
            tally[decision] = tally.get(decision, 0) + 1
            if meas.get("success"):
                annotated = dimension_engine.draw_calibrated_overlay(
                    annotated, meas, decision=decision, target_tray=verif.get("assigned_tray", 0)
                )

        self.last_inspection_result = None
        self._display_cv_image(annotated)
        self.sys_status_lbl.setText(f"System: ● Multi-inspection complete ({len(objects)} objects)")
        QMessageBox.information(
            self,
            "Multi-Fastener Inspection Complete",
            f"Inspected {len(objects)} objects in the inspection area:\n\n"
            f"Accepted: {tally['ACCEPT']}\nReinspect: {tally['REINSPECT']}\nRejected: {tally['REJECT']}\n\n"
            "Area scan is a preview: parts are not logged or physically sorted. "
            "Inspect parts one at a time to sort them."
        )

    # ========================================================================
    # INSPECTION RESULTS
    # Update the result panel, history, bin fill levels and counters.
    # ========================================================================
    def _on_inspection_completed(self, result: dict):
        self._restore_analyze_button()
        if not hardware_manager.is_estopped:
            self.sys_status_lbl.setText(f"System: ● Inspection Complete ({result.get('decision')})")

        self.last_inspection_result = result
        self.update_ai_status_indicator()  # shows it in the status bar if the YOLO model failed to load
        self.result_panel.display_result(result)
        self._lock_result_panel_width()
        self.tab_history.add_inspection_entry(result)
        self.tab_calib.set_last_measurement(result)  # lets the Calibration tab use this part as its reference
        self.tab_trays.refresh_fill_levels()
        self._show_inspection_overlay(result)

    def _on_inspection_error(self, error_msg: str):
        self._restore_analyze_button()
        self.sys_status_lbl.setText("System: ● Inspection Failed")
        QMessageBox.critical(self, "Inspection Error", f"Error:\n{error_msg}")

    def _on_sort_cycle_progress(self, step_name: str, percent: int):
        # The bin count only changes once the part has physically been released
        if percent == 0:
            self.tab_trays.refresh_fill_levels()

    def _on_counters_updated(self, counters: dict):
        self.result_panel.update_counters(counters)

    # ========================================================================
    # AI SETTINGS
    # ========================================================================
    def _open_settings_dialog(self):
        dlg = SettingsDialog(current_model=self.current_model, parent=self)
        dlg.settings_saved.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self, new_model: str):
        self.current_model = new_model
        self.update_ai_status_indicator()

    def update_ai_status_indicator(self):
        key = get_gemini_api_key()
        if self.current_model == MODEL_YOLO:
            if yolo_classifier.is_available():
                self.ai_status_lbl.setText("AI: ● YOLO11n Trained Classifier (Offline)")
                self.ai_status_lbl.setStyleSheet("color: #15803D; font-weight: 600; margin-right: 16px;")
            else:
                self.ai_status_lbl.setText("AI: ● YOLO model missing - using OpenCV rules")
                self.ai_status_lbl.setStyleSheet("color: #B45309; font-weight: 600; margin-right: 16px;")
        elif self.current_model == MODEL_LOCAL_OFFLINE:
            self.ai_status_lbl.setText("AI: ● Local Offline Vision Engine (Zero-Config)")
            self.ai_status_lbl.setStyleSheet("color: #1D4ED8; font-weight: 600; margin-right: 16px;")
        elif key:
            self.ai_status_lbl.setText(f"AI: ● Cloud Vision ({self.current_model})")
            self.ai_status_lbl.setStyleSheet("color: #15803D; font-weight: 600; margin-right: 16px;")
        else:
            self.ai_status_lbl.setText("AI: ● Local Offline Mode (API Key Optional)")
            self.ai_status_lbl.setStyleSheet("color: #1D4ED8; font-weight: 600; margin-right: 16px;")

    # ========================================================================
    # EMERGENCY STOP BUTTON
    # ========================================================================
    def _toggle_emergency_stop(self):
        """Triggers emergency stop kill switch."""
        self._stop_camera()
        hardware_manager.emergency_stop()
        self.estop_banner.setVisible(True)
        self.sys_status_lbl.setText("System: 🛑 EMERGENCY STOP ACTIVE")
        self.sys_status_lbl.setStyleSheet("color: #DC2626; font-weight: 900;")
        self.analyze_btn.setEnabled(False)
        QMessageBox.critical(
            self,
            "EMERGENCY STOP ACTIVATED",
            "Emergency Stop Triggered!\n\nAll conveyor stepper and servo motion has been killed.\nEnsure physical mechanism is clear before clicking 'RESET E-STOP'."
        )

    def _reset_emergency_stop(self):
        """Recovers from emergency stop state."""
        hardware_manager.reset_estop()
        self.estop_banner.setVisible(False)
        self.sys_status_lbl.setText("System: ● Ready (E-Stop Cleared)")
        self.sys_status_lbl.setStyleSheet("color: #15803D; font-weight: 600;")
        self.analyze_btn.setEnabled(True)
        QMessageBox.information(self, "E-STOP Cleared", "Hardware motion re-enabled. System returned to READY state.")

    # ========================================================================
    # SHUTDOWN
    # ========================================================================
    def closeEvent(self, event):
        self._stop_camera()
        hardware_manager.disconnect_hardware()
        log_session_step("SHUTDOWN", "Application closed cleanly.")
        event.accept()
