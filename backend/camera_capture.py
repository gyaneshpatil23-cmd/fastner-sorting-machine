"""
FILE: backend/camera_capture.py

WHAT THIS FILE DOES
    Reads live video from the inspection camera without freezing the window.

MAIN PARTS
    - CameraThread: background thread that grabs frames and hands them to the UI
    - scan_available_cameras(): lists the cameras plugged into the PC
    - get_preferred_camera_index(): picks an external USB camera before the laptop webcam

USED BY
    frontend/main_window.py
"""

import time
from typing import Optional, List, Dict, Any
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from backend.app_config import (
    DEFAULT_CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, PREFER_BUILT_IN_CAMERA
)
from backend.app_logging import app_logger, log_session_step

# ============================================================================
# LIVE CAMERA THREAD
# Grabs frames in the background and sends each one to the UI.
# ============================================================================
class CameraThread(QThread):
    """
    Background worker thread capturing frames from OpenCV VideoCapture
    without blocking the PySide6 UI event loop.
    """
    frame_received = Signal(np.ndarray)
    error_occurred = Signal(str)
    camera_started = Signal(int)  # Emits active camera index
    camera_stopped = Signal()

    def __init__(self, camera_index: Optional[int] = None, parent=None):
        super().__init__(parent)
        # If no camera index passed, pick best camera (external preferred)
        self.camera_index = camera_index if camera_index is not None else get_preferred_camera_index()
        self._is_running = False
        self._stop_requested = False
        self._mutex = QMutex()
        self._last_frame: Optional[np.ndarray] = None
        self._cap: Optional[cv2.VideoCapture] = None

    def set_camera_index(self, index: int):
        with QMutexLocker(self._mutex):
            self.camera_index = index

    def run(self):
        """Worker loop reading frames continuously."""
        app_logger.info(f"Opening camera index {self.camera_index}...")
        
        # On Windows, DirectShow provides low-latency capture
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap or not self._cap.isOpened():
            # Fallback to standard backend
            self._cap = cv2.VideoCapture(self.camera_index)

        # If chosen external index failed, try index 0 fallback
        if not self._cap or not self._cap.isOpened():
            if self.camera_index != 0:
                app_logger.warning(f"Camera #{self.camera_index} failed, attempting fallback to Camera #0...")
                self._cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if self._cap.isOpened():
                    self.camera_index = 0

        if not self._cap or not self._cap.isOpened():
            err_msg = f"Failed to initialize camera device #{self.camera_index}."
            app_logger.error(err_msg)
            self.error_occurred.emit(err_msg)
            return

        # Configure camera resolution
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

        with QMutexLocker(self._mutex):
            # stop() may have been called while the device was still opening
            self._is_running = not self._stop_requested
        if self._is_running:
            self.camera_started.emit(self.camera_index)
            app_logger.info(f"Camera #{self.camera_index} streaming active.")

        target_interval = 1.0 / max(1, CAMERA_FPS)

        while self._is_running:
            start_time = time.time()
            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.04)
                continue

            with QMutexLocker(self._mutex):
                self._last_frame = frame.copy()

            self.frame_received.emit(frame)

            elapsed = time.time() - start_time
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Release resource
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        app_logger.info("Camera stream closed.")
        self.camera_stopped.emit()

    def stop(self):
        """Stops streaming and waits for thread termination."""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
            self._is_running = False
        self.wait(1500)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with QMutexLocker(self._mutex):
            if self._last_frame is not None:
                return self._last_frame.copy()
            return None

    def is_streaming(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._is_running


# ============================================================================
# CAMERA DISCOVERY
# Find which cameras are plugged in and choose the best one.
# ============================================================================
def scan_available_cameras(max_tested: int = 4) -> List[Dict[str, Any]]:
    """
    Scans system video devices.
    Returns list of camera info dictionaries e.g. [{"index": 1, "name": "Camera 1 (External USB)", "is_external": True}]
    """
    available = []
    for i in range(max_tested):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            is_ext = (i > 0)
            name = f"Camera {i} (External USB Inspection Cam)" if is_ext else f"Camera {i} (Integrated Laptop Cam)"
            available.append({
                "index": i,
                "name": name,
                "is_external": is_ext
            })
            cap.release()

    if not available:
        # Virtual fallback for demo if no physical cameras attached
        available.append({"index": 0, "name": "Camera 0 (Default Video Source)", "is_external": False})

    return available


def get_preferred_camera_index() -> int:
    """
    Returns the camera to start with: the built-in camera (index 0) while PREFER_BUILT_IN_CAMERA
    is set, otherwise the external USB camera if one is present.
    """
    if PREFER_BUILT_IN_CAMERA:
        return 0
    cameras = scan_available_cameras()
    # Find highest external camera index
    external_cams = [c for c in cameras if c.get("is_external", False)]
    if external_cams:
        return external_cams[-1]["index"]
    return 0
