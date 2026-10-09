"""
FILE: main.py

WHAT THIS FILE DOES
    The starting point of the application. Run this file to open the desktop app:
        python main.py

MAIN PARTS
    - Environment check: restarts under the project's own Python (.venv) when started with another one
    - Crash logging: any unexpected error is written to the log instead of vanishing
    - main(): creates the Qt application, applies the stylesheet and shows the main window
"""

import subprocess
import sys
import traceback
from pathlib import Path

# ============================================================================
# ENVIRONMENT CHECK
# The YOLO model needs the packages installed in the project's .venv folder. A plain
# "python main.py" may start a different Python that lacks them, so the app restarts itself there.
# ============================================================================
def use_project_environment():
    venv_dir = Path(__file__).resolve().parent.parent / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe"
    if venv_python.exists() and Path(sys.prefix).resolve() != venv_dir:
        sys.exit(subprocess.call([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]))

if __name__ == "__main__":
    use_project_environment()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from backend.app_config import APP_TITLE
from backend.app_logging import app_logger, log_session_step
from frontend.main_window import MainWindow

# ============================================================================
# CRASH LOGGING
# Sends any uncaught error to the application log.
# ============================================================================
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to capture unhandled exceptions in logs."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    app_logger.critical(f"Unhandled Exception:\n{err_msg}")
    log_session_step("CRITICAL_ERROR", f"Unhandled Exception: {exc_value}")

# ============================================================================
# START THE APP
# ============================================================================
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
    window.show_fitted()

    log_session_step("MAIN", "Desktop application GUI loop started.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
