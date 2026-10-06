"""
Stylesheets and theme definitions for AI Fastener Inspection System.
Designed for a clean, professional, industrial engineering look.
"""

MAIN_STYLESHEET = """
/* Global Application Style */
QWidget {
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    color: #1E293B;
    background-color: #F8FAFC;
}

/* Main Window */
QMainWindow {
    background-color: #F1F5F9;
}

/* Card Containers */
QFrame.cardFrame {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 12px;
}

QGroupBox {
    font-weight: 600;
    font-size: 13px;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 14px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    background-color: #FFFFFF;
}

/* Buttons */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 7px 16px;
    font-weight: 500;
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

/* Primary Action Button (Analyze Fastener) */
QPushButton#primaryActionBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 24px;
    border-radius: 6px;
}

QPushButton#primaryActionBtn:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
}

QPushButton#primaryActionBtn:pressed {
    background-color: #1E40AF;
}

QPushButton#primaryActionBtn:disabled {
    background-color: #93C5FD;
    border-color: #93C5FD;
    color: #FFFFFF;
}

/* Danger / Reset Button */
QPushButton#dangerBtn {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FCA5A5;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
}

QPushButton#dangerBtn:hover {
    background-color: #FEE2E2;
    border-color: #F87171;
}

/* Camera Action Button */
QPushButton#cameraActionBtn {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 600;
}

QPushButton#cameraActionBtn:hover {
    background-color: #047857;
}

/* Live Mode Toggle Button */
QPushButton#liveModeBtn {
    background-color: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    font-weight: 600;
    padding: 7px 14px;
    border-radius: 4px;
}

QPushButton#liveModeBtn:hover {
    background-color: #F8FAFC;
    border-color: #059669;
    color: #059669;
}

QPushButton#liveModeBtn:checked {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 700;
}

/* Combo Box */
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 140px;
    color: #1E293B;
}

QComboBox:hover {
    border-color: #94A3B8;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #CBD5E1;
}

/* Line Edit / Inputs */
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 6px 10px;
    color: #1E293B;
}

QLineEdit:focus {
    border: 1px solid #2563EB;
}

/* Table View */
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    gridline-color: #F1F5F9;
    selection-background-color: #EFF6FF;
    selection-color: #1E293B;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    padding: 6px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid #CBD5E1;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #F1F5F9;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

/* Status Bar */
QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 12px;
    padding: 4px;
}
"""
