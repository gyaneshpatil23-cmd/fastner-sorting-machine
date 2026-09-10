"""
Main Application Window for AI Fastener Inspection System.
Integrates live camera feeds, real-time Live Detection Mode, image loading, synthetic sample generation,
asynchronous Gemini classification, visual overlays, result statistics, and history.
"""

import os
import glob
from typing import Optional
import cv2
import numpy as np

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSplitter, QFileDialog, QMessageBox,
    QStatusBar, QComboBox, QMenu, QToolButton
)

from config import (
    APP_TITLE, APP_SUBTITLE, APP_VERSION, DEFAULT_MODEL,
    SAMPLE_IMAGES_DIR, SUPPORTED_IMAGE_EXTENSIONS, get_gemini_api_key,
    MODEL_LOCAL_OFFLINE, CATEGORY_UNKNOWN
)
from logger import app_logger, log_session_step
from camera import CameraThread
from classifier import FastenerClassifierManager
from local_classifier import LocalFastenerClassifier
from image_utils import (
    load_image, cv_to_qpixmap, draw_classification_overlay,
    draw_live_scanning_hud, generate_sample_dataset
)
from ui.result_panel import ResultPanel
from ui.history_panel import HistoryPanel
from ui.settings_dialog import SettingsDialog
from ui.styles import MAIN_STYLESHEET


class MainWindow(QMainWindow):
    """Main desktop application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} - {APP_VERSION}")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)

        # State
        self.current_model = DEFAULT_MODEL
        self.current_cv_image: Optional[np.ndarray] = None
        self.last_analysis_result: Optional[dict] = None
        self.overlay_enabled = True
        self.is_live_mode = False

        # Ensure sample dataset exists for client demo
        generate_sample_dataset(str(SAMPLE_IMAGES_DIR))

        # Core Engines
        self.classifier_manager = FastenerClassifierManager(self)
        self.classifier_manager.inspection_completed.connect(self._on_inspection_completed)
        self.classifier_manager.counters_updated.connect(self._on_counters_updated)
        self.local_classifier = LocalFastenerClassifier()

        self.camera_thread: Optional[CameraThread] = None

        self.init_ui()
        self.setStyleSheet(MAIN_STYLESHEET)
        self.update_ai_status_indicator()

        log_session_step("STARTUP", "Application initialized and UI ready.")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 14, 16, 12)
        main_layout.setSpacing(12)

        # ---------------- 1. Top Header Bar ----------------
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_frame.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 6px; padding: 10px 16px;"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel(APP_TITLE.upper())
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #0F172A; letter-spacing: 0.5px;")
        subtitle_lbl = QLabel(APP_SUBTITLE)
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        # Settings button
        self.settings_btn = QPushButton("⚙ System Settings")
        self.settings_btn.setStyleSheet("font-weight: 600; padding: 8px 16px;")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        header_layout.addWidget(self.settings_btn)

        main_layout.addWidget(header_frame)

        # ---------------- 2. Splitter Layout: Viewport + Dashboard ----------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        # Left Panel (Viewport + Controls)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Viewport Card Frame
        viewport_card = QFrame()
        viewport_card.setProperty("class", "cardFrame")
        viewport_card.setStyleSheet(
            "background-color: #0F172A; border: 1px solid #334155; border-radius: 6px;"
        )
        viewport_layout = QVBoxLayout(viewport_card)
        viewport_layout.setContentsMargins(4, 4, 4, 4)

        self.image_viewport = QLabel("NO IMAGE LOADED\n\nOpen an image, load a sample, or switch to Live Mode.")
        self.image_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_viewport.setStyleSheet(
            "color: #94A3B8; font-size: 14px; font-weight: 500; background-color: #0F172A; border-radius: 4px;"
        )
        self.image_viewport.setMinimumSize(540, 400)
        viewport_layout.addWidget(self.image_viewport)
        left_layout.addWidget(viewport_card, 1)

        # Controls Row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.open_img_btn = QPushButton("📁 Open Image")
        self.open_img_btn.clicked.connect(self._open_image_file)
        controls_layout.addWidget(self.open_img_btn)

        # Sample dropdown menu button
        self.sample_btn = QToolButton()
        self.sample_btn.setText("⚡ Load Sample ▾")
        self.sample_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._build_sample_menu()
        controls_layout.addWidget(self.sample_btn)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #CBD5E1;")
        controls_layout.addWidget(sep)

        # Live Mode Toggle Button
        self.live_mode_btn = QPushButton("⚡ Live Mode")
        self.live_mode_btn.setObjectName("liveModeBtn")
        self.live_mode_btn.setCheckable(True)
        self.live_mode_btn.toggled.connect(self._toggle_live_mode)
        controls_layout.addWidget(self.live_mode_btn)

        self.start_cam_btn = QPushButton("🎥 Start Camera")
        self.start_cam_btn.setObjectName("cameraActionBtn")
        self.start_cam_btn.clicked.connect(self._start_camera)
        controls_layout.addWidget(self.start_cam_btn)

        self.capture_btn = QPushButton("📸 Capture Frame")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_camera_frame)
        controls_layout.addWidget(self.capture_btn)

        self.stop_cam_btn = QPushButton("⏹ Stop Camera")
        self.stop_cam_btn.setEnabled(False)
        self.stop_cam_btn.clicked.connect(self._stop_camera)
        controls_layout.addWidget(self.stop_cam_btn)

        left_layout.addLayout(controls_layout)

        # Prominent Analyze Button
        self.analyze_btn = QPushButton("🔍  ANALYZE FASTENER")
        self.analyze_btn.setObjectName("primaryActionBtn")
        self.analyze_btn.setMinimumHeight(44)
        self.analyze_btn.clicked.connect(self._analyze_current_image)
        left_layout.addWidget(self.analyze_btn)

        splitter.addWidget(left_widget)

        # Right Panel (Results, Counters & History)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.result_panel = ResultPanel()
        self.result_panel.reset_counters_requested.connect(self.classifier_manager.reset_counters)
        right_layout.addWidget(self.result_panel)

        self.history_panel = HistoryPanel()
        self.history_panel.clear_history_requested.connect(self.classifier_manager.clear_history)
        right_layout.addWidget(self.history_panel, 1)

        splitter.addWidget(right_widget)

        # Splitter ratio: 60% Left, 40% Right
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

        # ---------------- 3. Status Bar ----------------
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.cam_status_lbl = QLabel("Camera: ● Off")
        self.cam_status_lbl.setStyleSheet("color: #64748B; margin-right: 16px;")
        
        self.ai_status_lbl = QLabel("AI: ● Checking...")
        self.ai_status_lbl.setStyleSheet("color: #64748B; margin-right: 16px;")
        
        self.sys_status_lbl = QLabel("System: ● Ready")
        self.sys_status_lbl.setStyleSheet("color: #15803D; font-weight: 600;")

        self.status_bar.addWidget(self.cam_status_lbl)
        self.status_bar.addWidget(self.ai_status_lbl)
        self.status_bar.addPermanentWidget(self.sys_status_lbl)

    def _build_sample_menu(self):
        """Constructs sample images dropdown menu."""
        menu = QMenu(self)
        samples = [
            ("Hex Nut Sample", "sample_01_hex_nut.png"),
            ("Hex Bolt Sample", "sample_02_hex_bolt.png"),
            ("Wood Screw Sample", "sample_03_wood_screw.png"),
            ("Flat Washer Sample", "sample_04_flat_washer.png"),
        ]
        
        for name, filename in samples:
            filepath = SAMPLE_IMAGES_DIR / filename
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, p=str(filepath): self._load_image_from_path(p))
            menu.addAction(action)

        # Scan for any additional custom user images in sample_images/
        custom_files = []
        for ext in SUPPORTED_IMAGE_EXTENSIONS:
            custom_files.extend(glob.glob(str(SAMPLE_IMAGES_DIR / f"*{ext}")))
        
        sample_basenames = [s[1] for s in samples]
        extras = [f for f in custom_files if os.path.basename(f) not in sample_basenames]
        if extras:
            menu.addSeparator()
            for ext_file in extras:
                action = QAction(f"Custom: {os.path.basename(ext_file)}", self)
                action.triggered.connect(lambda checked=False, p=ext_file: self._load_image_from_path(p))
                menu.addAction(action)

        self.sample_btn.setMenu(menu)

    def _open_image_file(self):
        """Opens file dialog for user to select an image from disk."""
        ext_filter = "Images (*.jpg *.jpeg *.png *.bmp *.webp);;All Files (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Fastener Image", "", ext_filter)
        if filepath:
            self._load_image_from_path(filepath)

    def _load_image_from_path(self, filepath: str):
        """Loads and displays image from file path."""
        # Stop live camera if running
        if self.is_live_mode:
            self.live_mode_btn.setChecked(False)
        self._stop_camera()

        img = load_image(filepath)
        if img is None:
            QMessageBox.warning(self, "Image Error", f"Could not load image:\n{filepath}")
            return

        self.current_cv_image = img
        self.last_analysis_result = None
        self._display_cv_image(self.current_cv_image)
        self.sys_status_lbl.setText(f"System: ● Loaded {os.path.basename(filepath)}")
        log_session_step("IMAGE", f"Loaded image file: {os.path.basename(filepath)}")

    def _toggle_live_mode(self, enabled: bool):
        """Toggles real-time continuous fastener classification mode."""
        self.is_live_mode = enabled
        if enabled:
            self.live_mode_btn.setText("⚡ Live Mode: ON")
            self.sys_status_lbl.setText("System: ● Live AI Detection Active")
            self.sys_status_lbl.setStyleSheet("color: #059669; font-weight: 600;")
            log_session_step("LIVE_MODE", "Live fastener AI detection mode started.")
            # Automatically start camera if not already streaming
            if not self.camera_thread or not self.camera_thread.is_streaming():
                self._start_camera()
        else:
            self.live_mode_btn.setText("⚡ Live Mode")
            self.sys_status_lbl.setText("System: ● Live Mode Paused")
            self.sys_status_lbl.setStyleSheet("color: #64748B; font-weight: 600;")
            log_session_step("LIVE_MODE", "Live fastener AI detection mode stopped.")

    def _start_camera(self):
        """Initializes and starts background camera capture thread."""
        if self.camera_thread and self.camera_thread.is_streaming():
            return

        self.camera_thread = CameraThread(camera_index=0, parent=self)
        self.camera_thread.frame_received.connect(self._on_camera_frame)
        self.camera_thread.camera_started.connect(self._on_camera_started)
        self.camera_thread.camera_stopped.connect(self._on_camera_stopped)
        self.camera_thread.error_occurred.connect(self._on_camera_error)
        self.camera_thread.start()

    def _on_camera_started(self):
        self.start_cam_btn.setEnabled(False)
        self.capture_btn.setEnabled(True)
        self.stop_cam_btn.setEnabled(True)
        self.cam_status_lbl.setText("Camera: ● Streaming Live")
        self.cam_status_lbl.setStyleSheet("color: #059669; font-weight: 600; margin-right: 16px;")
        self.sys_status_lbl.setText("System: ● Camera active")
        log_session_step("CAMERA", "Camera stream started.")

    def _on_camera_stopped(self):
        self.start_cam_btn.setEnabled(True)
        self.capture_btn.setEnabled(False)
        self.stop_cam_btn.setEnabled(False)
        if self.is_live_mode:
            self.live_mode_btn.setChecked(False)
        self.cam_status_lbl.setText("Camera: ● Off")
        self.cam_status_lbl.setStyleSheet("color: #64748B; margin-right: 16px;")
        log_session_step("CAMERA", "Camera stream stopped.")

    def _on_camera_error(self, err_msg: str):
        self._stop_camera()
        QMessageBox.warning(self, "Camera Warning", f"{err_msg}\n\nYou can still use 'Open Image' or 'Load Sample'.")
        log_session_step("CAMERA_ERROR", err_msg)

    def _on_camera_frame(self, frame: np.ndarray):
        """Handles live camera frame. Performs real-time inference when in Live Mode."""
        self.current_cv_image = frame

        if self.is_live_mode:
            # Real-time local offline vision classification
            res = self.local_classifier.classify(frame)
            cat = res.get("category", CATEGORY_UNKNOWN)
            conf = float(res.get("confidence", 0.0))
            roi = res.get("roi")

            if res.get("success", False) and cat != CATEGORY_UNKNOWN and conf >= 0.65:
                # Fastener localized and classified in live stream
                annotated = draw_classification_overlay(frame, cat, conf, roi=roi)
                self._display_cv_image(annotated)
                self.result_panel.display_result(res)
                self.last_analysis_result = res
                self.sys_status_lbl.setText(f"System: ● Live Detected: {cat} ({int(conf*100)}%)")
                self.sys_status_lbl.setStyleSheet("color: #059669; font-weight: 600;")
            else:
                # No fastener in view - show live scanning HUD
                annotated = draw_live_scanning_hud(frame)
                self._display_cv_image(annotated)
                self.result_panel.set_live_scanning_state()
                self.sys_status_lbl.setText("System: ● Live AI Scanning for Fasteners...")
                self.sys_status_lbl.setStyleSheet("color: #059669; font-weight: 600;")
        else:
            self._display_cv_image(frame)

    def _capture_camera_frame(self):
        """Freezes current camera frame for classification."""
        if self.camera_thread and self.camera_thread.is_streaming():
            frame = self.camera_thread.get_latest_frame()
            if self.is_live_mode:
                self.live_mode_btn.setChecked(False)
            self._stop_camera()
            if frame is not None:
                self.current_cv_image = frame
                self._display_cv_image(self.current_cv_image)
                self.sys_status_lbl.setText("System: ● Frame captured")
                log_session_step("CAMERA", "Captured frame from live camera.")

    def _stop_camera(self):
        """Safely stops active camera thread."""
        if self.is_live_mode:
            self.live_mode_btn.setChecked(False)
        if self.camera_thread and self.camera_thread.is_streaming():
            self.camera_thread.stop()
            self.camera_thread = None

    def _display_cv_image(self, cv_img: np.ndarray):
        """Scales and sets OpenCV image onto image viewport QLabel maintaining aspect ratio."""
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
        """Rescales image when window is resized."""
        super().resizeEvent(event)
        if self.current_cv_image is not None and not (self.camera_thread and self.camera_thread.is_streaming()):
            # If we have an annotated overlay result, show annotated, else raw
            if self.last_analysis_result and self.overlay_enabled:
                cat = self.last_analysis_result.get("category", "UNKNOWN")
                conf = self.last_analysis_result.get("confidence", 0.0)
                roi = self.last_analysis_result.get("roi")
                annotated = draw_classification_overlay(self.current_cv_image, cat, conf, roi=roi)
                self._display_cv_image(annotated)
            else:
                self._display_cv_image(self.current_cv_image)

    def _analyze_current_image(self):
        """Triggers AI vision classification on currently displayed frame."""
        if self.current_cv_image is None or self.current_cv_image.size == 0:
            QMessageBox.information(
                self,
                "No Image",
                "Please select an image first using 'Open Image', 'Load Sample', or capture a frame from the camera."
            )
            return

        # Determine active engine
        api_key = get_gemini_api_key()
        using_local = (self.current_model == MODEL_LOCAL_OFFLINE) or (not api_key)
        engine_name = "Local Offline Vision Engine" if using_local else f"Gemini Cloud ({self.current_model})"

        # Disable analyze button & indicate progress
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("⏳ ANALYZING...")
        self.result_panel.set_analyzing_state()
        self.sys_status_lbl.setText(f"System: ● Analyzing via {engine_name}...")
        self.sys_status_lbl.setStyleSheet("color: #2563EB; font-weight: 600;")

        log_session_step("INFERENCE", f"Analyzing fastener image via {engine_name}...")

        # Spawn asynchronous classification worker
        worker = self.classifier_manager.start_classification(self.current_cv_image, self.current_model)
        if worker:
            worker.error.connect(self._on_classification_error)

    def _on_inspection_completed(self, result: dict):
        """Handles finished AI classification result."""
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍  ANALYZE FASTENER")
        self.sys_status_lbl.setText("System: ● Inspection Complete")
        self.sys_status_lbl.setStyleSheet("color: #15803D; font-weight: 600;")

        self.last_analysis_result = result
        self.result_panel.display_result(result)
        self.history_panel.add_inspection_entry(result)

        # Draw visual overlay on image viewport
        category = result.get("category", "UNKNOWN")
        confidence = float(result.get("confidence", 0.0))
        roi = result.get("roi")
        if self.current_cv_image is not None and self.overlay_enabled:
            annotated = draw_classification_overlay(self.current_cv_image, category, confidence, roi=roi)
            self._display_cv_image(annotated)

        # If analysis failed or returned unexpected category warning
        if not result.get("success", True):
            QMessageBox.warning(self, "AI Notice", result.get("reason", "Classification returned an alert."))

    def _on_classification_error(self, error_msg: str):
        """Handles worker thread errors."""
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍  ANALYZE FASTENER")
        self.sys_status_lbl.setText("System: ● Analysis Failed")
        self.sys_status_lbl.setStyleSheet("color: #B91C1C; font-weight: 600;")
        QMessageBox.critical(self, "Analysis Failed", f"Classification error:\n{error_msg}")

    def _on_counters_updated(self, counters: dict):
        """Updates category counter values in results panel."""
        self.result_panel.update_counters(counters)

    def _open_settings_dialog(self):
        """Opens settings modal dialog."""
        dlg = SettingsDialog(current_model=self.current_model, parent=self)
        dlg.settings_saved.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self, new_model: str):
        """Updates runtime model and refresh AI status indicator."""
        self.current_model = new_model
        self.update_ai_status_indicator()
        log_session_step("SETTINGS", f"Active model updated to: {self.current_model}")

    def update_ai_status_indicator(self):
        """Checks API key existence and updates bottom status bar."""
        key = get_gemini_api_key()
        if self.current_model == MODEL_LOCAL_OFFLINE:
            self.ai_status_lbl.setText("AI: ● Local Offline Vision Engine (Zero-Config)")
            self.ai_status_lbl.setStyleSheet("color: #2563EB; font-weight: 600; margin-right: 16px;")
        elif key:
            self.ai_status_lbl.setText(f"AI: ● Cloud Connected ({self.current_model})")
            self.ai_status_lbl.setStyleSheet("color: #15803D; font-weight: 600; margin-right: 16px;")
        else:
            self.ai_status_lbl.setText("AI: ● Local Offline Mode (API Key Optional)")
            self.ai_status_lbl.setStyleSheet("color: #2563EB; font-weight: 600; margin-right: 16px;")

    def closeEvent(self, event):
        """Ensures camera thread and background workers are safely released on window close."""
        self._stop_camera()
        log_session_step("SHUTDOWN", "Application closed cleanly.")
        event.accept()
