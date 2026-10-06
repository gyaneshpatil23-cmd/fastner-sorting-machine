"""
Industrial Engineering Stylesheets for AI Fastener Inspection & Sorting System.
Clean, modern, professional instrumentation design with zero neon or sci-fi effects.
"""

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

MAIN_STYLESHEET = """
/* Global Application Style */
QWidget {
    font-family: "Segoe UI", "Segoe UI Semibold", "Arial", sans-serif;
    font-size: 12px;
    color: #0F172A;
    background-color: #F8FAFC;
}

QMainWindow {
    background-color: #F1F5F9;
}

/* Card Containers */
QFrame.workstationCard {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 12px;
}

QGroupBox {
    font-weight: 700;
    font-size: 12px;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    background-color: #FFFFFF;
}

/* Metric Display Tiles */
QFrame.metricTile {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 5px;
    padding: 8px;
}

/* Buttons */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 600;
    color: #334155;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

QPushButton:disabled {
    background-color: #F8FAFC;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Primary Workstation Action Button */
QPushButton#primaryActionBtn {
    background-color: #1D4ED8;
    color: #FFFFFF;
    border: 1px solid #1E40AF;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.5px;
    padding: 10px 20px;
    border-radius: 5px;
}

QPushButton#primaryActionBtn:hover {
    background-color: #1E40AF;
}

QPushButton#primaryActionBtn:pressed {
    background-color: #172554;
}

QPushButton#primaryActionBtn:disabled {
    background-color: #93C5FD;
    border-color: #93C5FD;
    color: #FFFFFF;
}

/* Camera Action Button */
QPushButton#cameraActionBtn {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 700;
}

QPushButton#cameraActionBtn:hover {
    background-color: #047857;
}

/* Danger / Reset Button */
QPushButton#dangerBtn {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FCA5A5;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#dangerBtn:hover {
    background-color: #FEE2E2;
    border-color: #F87171;
}

/* Inputs & Dropdowns */
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 5px 10px;
    color: #0F172A;
    font-weight: 500;
}

QComboBox:hover {
    border-color: #94A3B8;
}

QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 5px 8px;
    color: #0F172A;
}

QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1px solid #1D4ED8;
}

/* Spin box steppers: stacked on the right edge, with room reserved so they never cover the value */
QSpinBox, QDoubleSpinBox {
    padding-right: 24px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    background-color: #F1F5F9;
    border-left: 1px solid #CBD5E1;
    border-bottom: 1px solid #CBD5E1;
    border-top-right-radius: 3px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    background-color: #F1F5F9;
    border-left: 1px solid #CBD5E1;
    border-bottom-right-radius: 3px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #E2E8F0;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__ASSETS__/arrow_up.png");
    width: 8px;
    height: 5px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__ASSETS__/arrow_down.png");
    width: 8px;
    height: 5px;
}

/* Checkboxes: explicit box so the indicator is visible on the light theme */
QCheckBox {
    spacing: 8px;
    background: transparent;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #94A3B8;
    border-radius: 3px;
    background-color: #FFFFFF;
}

QCheckBox::indicator:hover {
    border-color: #1D4ED8;
}

QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #1D4ED8;
    image: url("__ASSETS__/check.png");
}

QCheckBox::indicator:disabled {
    background-color: #E2E8F0;
    border-color: #CBD5E1;
}

/* Tab Bar */
QTabWidget::pane {
    border: 1px solid #CBD5E1;
    background-color: #FFFFFF;
    border-radius: 4px;
}

QTabBar::tab {
    font-weight: 700;
    font-size: 11px;
    padding: 8px 16px;
    color: #475569;
    background: #E2E8F0;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #1D4ED8;
    border-top: 2px solid #1D4ED8;
    border-bottom: 1px solid #FFFFFF;
}

/* Table Widget */
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    gridline-color: #F1F5F9;
    selection-background-color: #EFF6FF;
    selection-color: #0F172A;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    padding: 6px;
    font-weight: 700;
    font-size: 11px;
    border: none;
    border-bottom: 1px solid #CBD5E1;
}

/* Progress Bars */
QProgressBar {
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    text-align: center;
    background-color: #F1F5F9;
    font-weight: 700;
    font-size: 11px;
    height: 18px;
}

/* Status Bar */
QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #CBD5E1;
    color: #64748B;
    font-size: 11px;
    padding: 3px;
}
""".replace("__ASSETS__", ASSETS_DIR.as_posix())
