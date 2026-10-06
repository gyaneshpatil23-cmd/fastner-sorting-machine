"""
Camera management module for AI Fastener Inspection System.
Provides thread-safe OpenCV VideoCapture streaming and single-frame capture for PySide6.
"""

import time
from typing import Optional, List
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from config import DEFAULT_CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS
from logger import app_logger

class CameraThread(QThread):
    """
    Background worker thread that captures frames from OpenCV VideoCapture
    and emits them for the GUI without freezing the application.
    """
    frame_received = Signal(np.ndarray)
    error_occurred = Signal(str)
    camera_started = Signal()
    camera_stopped = Signal()

    def __init__(self, camera_index: int = DEFAULT_CAMERA_INDEX, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._is_running = False
        self._mutex = QMutex()
        self._last_frame: Optional[np.ndarray] = None
        self._cap: Optional[cv2.VideoCapture] = None

    def set_camera_index(self, index: int):
        with QMutexLocker(self._mutex):
            self.camera_index = index

    def run(self):
        """Worker loop reading frames continuously."""
        app_logger.info(f"Opening camera index {self.camera_index}...")
        
        # On Windows, cv2.CAP_DSHOW provides fast startup and reliable directshow capture
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            # Fallback to default backend
            self._cap = cv2.VideoCapture(self.camera_index)

        if not self._cap or not self._cap.isOpened():
            err_msg = f"Failed to open camera (Device #{self.camera_index}). Please verify webcam connection."
            app_logger.error(err_msg)
            self.error_occurred.emit(err_msg)
            return

        # Configure resolution
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

        self._is_running = True
        self.camera_started.emit()
        app_logger.info("Camera stream initialized successfully.")

        target_interval = 1.0 / max(1, CAMERA_FPS)

        while self._is_running:
            start_time = time.time()
            ret, frame = self._cap.read()
            if not ret or frame is None:
                app_logger.warning("Failed to grab camera frame.")
                time.sleep(0.05)
                continue

            # Store last frame safely
            with QMutexLocker(self._mutex):
                self._last_frame = frame.copy()

            self.frame_received.emit(frame)

            # Cap frame rate
            elapsed = time.time() - start_time
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Cleanup
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        app_logger.info("Camera stream stopped and hardware resource released.")
        self.camera_stopped.emit()

    def stop(self):
        """Signals the thread to stop and waits for termination."""
        with QMutexLocker(self._mutex):
            self._is_running = False
        self.wait(2000)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Returns the most recent captured frame copy."""
        with QMutexLocker(self._mutex):
            if self._last_frame is not None:
                return self._last_frame.copy()
            return None

    def is_streaming(self) -> bool:
        """Returns True if the camera stream is actively running."""
        with QMutexLocker(self._mutex):
            return self._is_running


def scan_available_cameras(max_cameras: int = 3) -> List[int]:
    """Scans system for available OpenCV camera device indices."""
    available = []
    for i in range(max_cameras):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available
