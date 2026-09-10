"""
Main Entry Point for AI Fastener Inspection System.
Initializes PySide6 application, sets up exception logging, and launches desktop window.
"""

import sys
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from config import APP_TITLE
from logger import app_logger, log_session_step
from ui.main_window import MainWindow

def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to capture unhandled exceptions in logs."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    app_logger.critical(f"Unhandled Exception:\n{err_msg}")
    log_session_step("CRITICAL_ERROR", f"Unhandled Exception: {exc_value}")

def main():
    # Setup global exception handler
    sys.excepthook = handle_exception

    # High DPI Support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("Industrial Fastener AI")

    # Instantiate and display main window
    window = MainWindow()
    window.show()

    log_session_step("MAIN", "Desktop application GUI loop started.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
