"""
Settings Dialog for AI Fastener Inspection System.
Allows configuration of Gemini Model selection, API Key management, and API connection testing.
"""

import os
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QGroupBox, QFrame, QMessageBox,
    QCheckBox
)

from backend.config import (
    AVAILABLE_MODELS, DEFAULT_MODEL, ENV_FILE,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD,
    MODEL_LOCAL_OFFLINE, get_gemini_api_key
)
from dotenv import set_key

from backend.gemini_client import GeminiVisionClient
from backend.logger import app_logger, log_session_step


class ConnectionTestWorker(QThread):
    """Background worker for testing Gemini connection or validating Local Offline Engine."""
    result_ready = Signal(bool, str)

    def __init__(self, model_name: str, api_key: str = "", parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self.api_key = api_key

    def run(self):
        if self.model_name == MODEL_LOCAL_OFFLINE:
            self.result_ready.emit(True, "Local Offline Computer Vision Engine is active and ready (zero configuration required).")
            return
        client = GeminiVisionClient(model_name=self.model_name)
        is_ok, msg = client.test_connection(self.model_name, api_key=self.api_key)
        self.result_ready.emit(is_ok, msg)


class SettingsDialog(QDialog):
    """Modal dialog for application and AI settings."""
    settings_saved = Signal(str)  # Emits selected model name

    def __init__(self, current_model: str = DEFAULT_MODEL, parent=None):
        super().__init__(parent)
        self.current_model = current_model
        self._test_worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("System Settings & AI Configuration")
        self.setFixedWidth(520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        # ---------------- 1. AI Model Selection ----------------
        model_group = QGroupBox("GEMINI AI MODEL CONFIGURATION")
        model_layout = QVBoxLayout(model_group)
        model_layout.setContentsMargins(12, 14, 12, 12)
        model_layout.setSpacing(10)

        m_row = QHBoxLayout()
        m_lbl = QLabel("Active Vision Model:")
        m_lbl.setStyleSheet("font-weight: 600; color: #334155;")
        self.model_combo = QComboBox()
        self.model_combo.addItems(AVAILABLE_MODELS)
        if self.current_model in AVAILABLE_MODELS:
            self.model_combo.setCurrentText(self.current_model)
        else:
            self.model_combo.addItem(self.current_model)
            self.model_combo.setCurrentText(self.current_model)

        m_row.addWidget(m_lbl)
        m_row.addWidget(self.model_combo, 1)
        model_layout.addLayout(m_row)

        desc_lbl = QLabel("Select the Gemini vision-capable model to be used for fastener inspection.")
        desc_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        desc_lbl.setWordWrap(True)
        model_layout.addWidget(desc_lbl)

        layout.addWidget(model_group)

        # ---------------- 2. API Key Management ----------------
        api_group = QGroupBox("GEMINI API AUTHENTICATION")
        api_layout = QVBoxLayout(api_group)
        api_layout.setContentsMargins(12, 14, 12, 12)
        api_layout.setSpacing(10)

        key_lbl = QLabel("API Key (GEMINI_API_KEY):")
        key_lbl.setStyleSheet("font-weight: 600; color: #334155;")
        api_layout.addWidget(key_lbl)

        key_input_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your Gemini API key (AIzaSy...)")
        self.api_key_input.setText(get_gemini_api_key())

        self.show_key_cb = QCheckBox("Show")
        self.show_key_cb.stateChanged.connect(self._toggle_show_key)

        key_input_row.addWidget(self.api_key_input, 1)
        key_input_row.addWidget(self.show_key_cb)
        api_layout.addLayout(key_input_row)

        note_lbl = QLabel("Key is saved as plain text in the local .env file. Keep that file private.")
        note_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        api_layout.addWidget(note_lbl)

        # Connection Test Row
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Gemini Connection")
        self.test_btn.clicked.connect(self._run_connection_test)

        self.status_badge = QLabel("● Status Unknown")
        self.status_badge.setStyleSheet("color: #64748B; font-weight: 600; font-size: 12px;")

        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.status_badge, 1)
        api_layout.addLayout(test_row)

        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setStyleSheet("font-size: 11px; color: #334155;")
        self.test_result_lbl.setWordWrap(True)
        api_layout.addWidget(self.test_result_lbl)

        layout.addWidget(api_group)

        # ---------------- 3. Classification Thresholds Overview ----------------
        thresh_group = QGroupBox("CONFIDENCE THRESHOLDS (CONFIGURED)")
        thresh_layout = QVBoxLayout(thresh_group)
        thresh_layout.setContentsMargins(12, 14, 12, 12)
        thresh_layout.setSpacing(6)

        t_text = (
            f"• <b>HIGH CONFIDENCE:</b> &ge; {int(CONFIDENCE_HIGH_THRESHOLD*100)}% (Green)<br>"
            f"• <b>MEDIUM CONFIDENCE:</b> {int(CONFIDENCE_MEDIUM_THRESHOLD*100)}% - {int(CONFIDENCE_HIGH_THRESHOLD*100)-1}% (Amber)<br>"
            f"• <b>LOW CONFIDENCE:</b> &lt; {int(CONFIDENCE_MEDIUM_THRESHOLD*100)}% (Red)"
        )
        t_lbl = QLabel(t_text)
        t_lbl.setStyleSheet("font-size: 12px; color: #475569; line-height: 1.5;")
        thresh_layout.addWidget(t_lbl)
        layout.addWidget(thresh_group)

        # ---------------- Dialog Actions ----------------
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.save_btn = QPushButton("Save && Apply")
        self.save_btn.setStyleSheet("background-color: #2563EB; color: white; font-weight: 600; padding: 8px 20px;")
        self.save_btn.clicked.connect(self._on_save_applied)

        self.cancel_btn = QPushButton("Close")
        self.cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.save_btn)
        layout.addLayout(btn_box)

    def _toggle_show_key(self, state):
        if self.show_key_cb.isChecked():
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _run_connection_test(self):
        # Test the key as typed, even if it has not been saved yet
        new_key = self.api_key_input.text().strip()

        selected_model = self.model_combo.currentText().strip()
        self.test_btn.setEnabled(False)
        self.status_badge.setText("● Testing Connection...")
        self.status_badge.setStyleSheet("color: #2563EB; font-weight: 600;")
        self.test_result_lbl.setText("Sending validation request to Gemini API...")

        self._test_worker = ConnectionTestWorker(selected_model, api_key=new_key)
        self._test_worker.result_ready.connect(self._on_test_finished)
        self._test_worker.start()

    def _on_test_finished(self, is_connected: bool, msg: str):
        self.test_btn.setEnabled(True)
        if is_connected:
            self.status_badge.setText("● Connected")
            self.status_badge.setStyleSheet("color: #15803D; font-weight: 700;")
            self.test_result_lbl.setStyleSheet("font-size: 11px; color: #15803D;")
        else:
            self.status_badge.setText("● Not Connected")
            self.status_badge.setStyleSheet("color: #B91C1C; font-weight: 700;")
            self.test_result_lbl.setStyleSheet("font-size: 11px; color: #B91C1C;")
        self.test_result_lbl.setText(msg)

    def _on_save_applied(self):
        new_key = self.api_key_input.text().strip()
        selected_model = self.model_combo.currentText().strip()

        # Update environment variable
        os.environ["GEMINI_API_KEY"] = new_key
        os.environ["GEMINI_MODEL"] = selected_model

        # Update only these two keys so any other entries in .env are preserved
        try:
            ENV_FILE.touch(exist_ok=True)
            set_key(str(ENV_FILE), "GEMINI_API_KEY", new_key)
            set_key(str(ENV_FILE), "GEMINI_MODEL", selected_model)
            log_session_step("SETTINGS", f"Saved configuration: Model={selected_model}, Key Updated={'Yes' if new_key else 'No'}")
        except Exception as e:
            app_logger.error(f"Failed to write to .env file: {e}")
            QMessageBox.warning(
                self, "Settings Not Saved to Disk",
                f"The settings apply to this session, but could not be written to .env:\n{e}"
            )

        self.settings_saved.emit(selected_model)
        self.accept()
