"""
FILE: backend/image_loading_and_overlays.py

WHAT THIS FILE DOES
    Helper functions for working with images: loading files, converting them for display in the
    window, finding the part in the picture, drawing boxes and labels, and drawing the demo samples.

MAIN PARTS
    - load_image(), cv_to_qimage(), cv_to_qpixmap(): load files and convert OpenCV images for Qt
    - detect_fastener_roi(), centre_guide_box(): find the part, and the guide box shown on live video
    - draw_classification_overlay(), draw_live_scanning_hud(): drawings on top of the image
    - generate_sample_dataset(), render_synthetic_fastener(): the four built-in 'Load Sample' images

USED BY
    frontend/main_window.py
    run_all_tests.py
"""

import os
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap

from backend.app_config import CATEGORY_COLORS, CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER
from backend.app_logging import app_logger

# ============================================================================
# LOADING AND QT CONVERSION
# Read image files and convert OpenCV images so the window can show them.
# ============================================================================
def load_image(filepath: str) -> Optional[np.ndarray]:
    """
    Safely loads an image from filesystem using OpenCV.
    Supports Unicode paths on Windows via cv2.imdecode.
    """
    if not os.path.exists(filepath):
        app_logger.error(f"Image path does not exist: {filepath}")
        return None
    try:
        # cv2.imdecode handles Unicode/spaces in Windows paths safely
        with open(filepath, "rb") as f:
            bytes_data = bytearray(f.read())
            np_arr = np.asarray(bytes_data, dtype=np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return img
    except Exception as e:
        app_logger.error(f"Error loading image {filepath}: {e}")
        return None

def cv_to_qimage(cv_img: np.ndarray) -> QImage:
    """Converts an OpenCV BGR image to PySide6 QImage."""
    if cv_img is None or cv_img.size == 0:
        return QImage()

    if len(cv_img.shape) == 2:
        # Grayscale
        h, w = cv_img.shape
        bytes_per_line = w
        return QImage(cv_img.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8).copy()

    h, w, ch = cv_img.shape
    bytes_per_line = ch * w
    # Convert BGR to RGB for Qt
    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    return QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

def cv_to_qpixmap(cv_img: np.ndarray) -> QPixmap:
    """Converts an OpenCV BGR image to PySide6 QPixmap."""
    qimg = cv_to_qimage(cv_img)
    if qimg.isNull():
        return QPixmap()
    return QPixmap.fromImage(qimg)

# ============================================================================
# FIND THE PART
# Locate the fastener's bounding box in the image.
# ============================================================================
def detect_fastener_roi(cv_img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """
    Locates primary fastener object using OpenCV thresholding and contour extraction.
    Returns (x, y, w, h) bounding box or None.
    """
    if cv_img is None or cv_img.size == 0:
        return None

    try:
        h, w = cv_img.shape[:2]
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # Apply gentle blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Determine background vs foreground: Otsu thresholding
        _, thresh1 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, thresh2 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Evaluate both threshold polarities for dark-on-light or light-on-dark backgrounds
        contours1, _ = cv2.findContours(thresh1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours2, _ = cv2.findContours(thresh2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for c in contours1 + contours2:
            area = cv2.contourArea(c)
            # Filter out tiny noise and full frame borders
            if (0.01 * w * h) < area < (0.90 * w * h):
                candidates.append((area, c))

        if not candidates:
            # Fallback: centered default bounding box
            pad_w = int(w * 0.15)
            pad_h = int(h * 0.15)
            return (pad_w, pad_h, w - 2 * pad_w, h - 2 * pad_h)

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_contour = candidates[0][1]
        x, y, bw, bh = cv2.boundingRect(best_contour)

        # Add slight padding around detected object
        pad = 12
        x = max(0, x - pad)
        y = max(0, y - pad)
        bw = min(w - x, bw + 2 * pad)
        bh = min(h - y, bh + 2 * pad)

        return (x, y, bw, bh)
    except Exception as e:
        app_logger.warning(f"Fastener ROI detection fallback: {e}")
        return None

def centre_guide_box(width: int, height: int) -> Tuple[int, int, int, int]:
    """The box drawn in the middle of live video where the operator presents the part: (x, y, w, h)."""
    box_w, box_h = int(width * 0.45), int(height * 0.50)
    return width // 2 - box_w // 2, height // 2 - box_h // 2, box_w, box_h

# ============================================================================
# DRAWING ON THE IMAGE
# Result box and label, and the guide shown over live video.
# ============================================================================
def draw_classification_overlay(
    cv_img: np.ndarray,
    category: str,
    confidence: float,
    roi: Optional[Tuple[int, int, int, int]] = None
) -> np.ndarray:
    """
    Draws engineering overlay with bounding box, category badge, and crosshairs.
    """
    if cv_img is None:
        return cv_img

    annotated = cv_img.copy()
    h, w = annotated.shape[:2]

    if roi is None:
        roi = detect_fastener_roi(annotated)

    if roi is not None:
        x, y, bw, bh = roi
    else:
        x, y, bw, bh = int(w * 0.1), int(h * 0.1), int(w * 0.8), int(h * 0.8)

    # Pick color based on category
    hex_color = CATEGORY_COLORS.get(category.upper(), "#2563EB").lstrip("#")
    # Convert HEX RGB to OpenCV BGR
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    bgr_color = (b, g, r)

    # 1. Draw Corner Brackets (Precision engineering style)
    corner_len = min(25, bw // 4, bh // 4)
    line_thickness = 2

    # Top-Left
    cv2.line(annotated, (x, y), (x + corner_len, y), bgr_color, line_thickness)
    cv2.line(annotated, (x, y), (x, y + corner_len), bgr_color, line_thickness)

    # Top-Right
    cv2.line(annotated, (x + bw, y), (x + bw - corner_len, y), bgr_color, line_thickness)
    cv2.line(annotated, (x + bw, y), (x + bw, y + corner_len), bgr_color, line_thickness)

    # Bottom-Left
    cv2.line(annotated, (x, y + bh), (x + corner_len, y + bh), bgr_color, line_thickness)
    cv2.line(annotated, (x, y + bh), (x, y + bh - corner_len), bgr_color, line_thickness)

    # Bottom-Right
    cv2.line(annotated, (x + bw, y + bh), (x + bw - corner_len, y + bh), bgr_color, line_thickness)
    cv2.line(annotated, (x + bw, y + bh), (x + bw, y + bh - corner_len), bgr_color, line_thickness)

    # Thin dashed/solid main bounding box
    cv2.rectangle(annotated, (x, y), (x + bw, y + bh), bgr_color, 1, cv2.LINE_AA)

    # 2. Draw Label Header Banner
    conf_pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
    label_text = f"{category.upper()} | {conf_pct}%"

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.55
    font_thickness = 1
    (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, font_thickness)

    banner_y1 = max(0, y - text_h - 10)
    banner_y2 = y
    banner_x1 = x
    banner_x2 = min(w, x + text_w + 16)

    # Filled banner
    cv2.rectangle(annotated, (banner_x1, banner_y1), (banner_x2, banner_y2), bgr_color, -1)
    # Text in white
    cv2.putText(
        annotated,
        label_text,
        (banner_x1 + 8, banner_y2 - 6),
        font,
        font_scale,
        (255, 255, 255),
        font_thickness,
        cv2.LINE_AA
    )

    # 3. Center Crosshair
    cx, cy = x + bw // 2, y + bh // 2
    cv2.line(annotated, (cx - 8, cy), (cx + 8, cy), (0, 255, 255), 1)
    cv2.line(annotated, (cx, cy - 8), (cx, cy + 8), (0, 255, 255), 1)

    return annotated

def draw_live_scanning_hud(cv_img: np.ndarray) -> np.ndarray:
    """
    Draws a modern scanning HUD on live camera feed when searching for fasteners.
    """
    if cv_img is None or cv_img.size == 0:
        return cv_img

    annotated = cv_img.copy()
    h, w = annotated.shape[:2]

    # 1. Top status banner
    badge_text = "LIVE AI INSPECTION ACTIVE"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.45
    font_thick = 1
    (tw, th), _ = cv2.getTextSize(badge_text, font, font_scale, font_thick)

    bx1, by1 = 14, 14
    bx2, by2 = bx1 + tw + 28, by1 + th + 14
    # Rounded badge (emerald green)
    cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (4, 120, 87), -1)
    # Pulsing live indicator dot
    cv2.circle(annotated, (bx1 + 12, (by1 + by2) // 2), 4, (0, 255, 128), -1)
    cv2.putText(
        annotated,
        badge_text,
        (bx1 + 22, by2 - 5),
        font,
        font_scale,
        (255, 255, 255),
        font_thick,
        cv2.LINE_AA
    )

    # 2. Subtle center targeting guide
    cx, cy = w // 2, h // 2
    x1, y1, box_w, box_h = centre_guide_box(w, h)
    x2, y2 = x1 + box_w, y1 + box_h

    guide_color = (180, 180, 180)
    c_len = 20

    # Corners
    cv2.line(annotated, (x1, y1), (x1 + c_len, y1), guide_color, 1)
    cv2.line(annotated, (x1, y1), (x1, y1 + c_len), guide_color, 1)

    cv2.line(annotated, (x2, y1), (x2 - c_len, y1), guide_color, 1)
    cv2.line(annotated, (x2, y1), (x2, y1 + c_len), guide_color, 1)

    cv2.line(annotated, (x1, y2), (x1 + c_len, y2), guide_color, 1)
    cv2.line(annotated, (x1, y2), (x1, y2 - c_len), guide_color, 1)

    cv2.line(annotated, (x2, y2), (x2 - c_len, y2), guide_color, 1)
    cv2.line(annotated, (x2, y2), (x2, y2 - c_len), guide_color, 1)

    # Subtle prompt text
    prompt = "Present fastener to camera (Hand / Surface)"
    (pw, ph), _ = cv2.getTextSize(prompt, font, 0.45, 1)
    cv2.putText(
        annotated,
        prompt,
        (cx - pw // 2, y2 + 24),
        font,
        0.45,
        (220, 220, 220),
        1,
        cv2.LINE_AA
    )

    return annotated

# ============================================================================
# SAMPLE IMAGES
# Draw the four built-in demo fasteners used by the 'Load Sample' menu.
# ============================================================================
def generate_sample_dataset(output_dir: str):
    """
    Creates high-quality synthetic engineering sample images for demonstration
    (NUT, BOLT, SCREW, WASHER) if real samples are not already present.
    """
    os.makedirs(output_dir, exist_ok=True)

    samples = [
        ("sample_01_hex_nut.png", CATEGORY_NUT),
        ("sample_02_hex_bolt.png", CATEGORY_BOLT),
        ("sample_03_wood_screw.png", CATEGORY_SCREW),
        ("sample_04_flat_washer.png", CATEGORY_WASHER),
    ]

    for filename, category in samples:
        filepath = os.path.join(output_dir, filename)
        if not os.path.exists(filepath):
            img = render_synthetic_fastener(category)
            cv2.imwrite(filepath, img)
            app_logger.info(f"Generated sample image: {filepath}")

# Synthetic samples are drawn at the default camera calibration so they measure true to size
SAMPLE_PX_PER_MM = 8.0  # 0.125 mm/pixel


def render_synthetic_fastener(category: str, width: int = 640, height: int = 480) -> np.ndarray:
    """
    Renders a to-scale engineering silhouette of a standard fastener on the inspection mat:
    M8 hex nut, M8 x 40 hex bolt, M4 x 20 countersunk screw, or M8 flat washer.
    """
    # Matte gray background with subtle grid
    img = np.full((height, width, 3), 238, dtype=np.uint8)

    # Draw faint grid (inspection surface)
    grid_color = (222, 222, 222)
    for gx in range(0, width, 40):
        cv2.line(img, (gx, 0), (gx, height), grid_color, 1)
    for gy in range(0, height, 40):
        cv2.line(img, (0, gy), (width, gy), grid_color, 1)

    center_x, center_y = width // 2, height // 2
    background = (238, 238, 238)
    metal_dark = (60, 60, 60)
    metal_base = (140, 140, 140)
    metal_highlight = (195, 195, 195)
    thread_color = (95, 95, 95)
    rim = 3  # outline thickness, drawn inside the silhouette so outer dimensions stay exact

    def mm(value: float) -> int:
        return int(round(value * SAMPLE_PX_PER_MM))

    if category == CATEGORY_NUT:
        # M8 hex nut: 13 mm across flats, 8 mm bore
        # One pixel under nominal: contour tracing reads the outline about a pixel wide
        corner_radius = (mm(13.0) - 1) / 2.0 / np.cos(np.pi / 6)
        angles = np.linspace(0, 2 * np.pi, 7)[:-1]

        def hexagon(radius: float) -> np.ndarray:
            return np.array(
                [[int(round(center_x + radius * np.cos(a))), int(round(center_y + radius * np.sin(a)))] for a in angles],
                np.int32
            )

        cv2.fillPoly(img, [hexagon(corner_radius)], metal_dark)
        cv2.fillPoly(img, [hexagon(corner_radius - rim)], metal_base)

        bore_radius = mm(8.0) // 2
        cv2.circle(img, (center_x, center_y), bore_radius + rim, metal_dark, -1)
        # Chamfer ring on the face of the nut
        cv2.circle(img, (center_x, center_y), bore_radius + rim + 5, thread_color, 1, cv2.LINE_AA)
        cv2.circle(img, (center_x, center_y), bore_radius, background, -1)

    elif category == CATEGORY_BOLT:
        # M8 x 40 hex bolt, side view: 13 mm x 5.3 mm head, 8 mm x 40 mm shank
        head_len, head_w = mm(5.3), mm(13.0)
        shank_len, shank_w = mm(40.0), mm(8.0)
        x0 = center_x - (head_len + shank_len) // 2
        head_x2 = x0 + head_len - 1
        shank_x1 = head_x2 + 1
        shank_x2 = shank_x1 + shank_len - 1
        head_y1 = center_y - head_w // 2
        head_y2 = head_y1 + head_w - 1
        shank_y1 = center_y - shank_w // 2
        shank_y2 = shank_y1 + shank_w - 1

        cv2.rectangle(img, (x0, head_y1), (head_x2, head_y2), metal_dark, -1)
        cv2.rectangle(img, (shank_x1, shank_y1), (shank_x2, shank_y2), metal_dark, -1)
        cv2.rectangle(img, (x0 + rim, head_y1 + rim), (head_x2 - rim, head_y2 - rim), metal_base, -1)
        cv2.rectangle(img, (shank_x1 - rim, shank_y1 + rim), (shank_x2 - rim, shank_y2 - rim), metal_base, -1)
        cv2.line(img, (x0 + rim, center_y), (head_x2 - rim, center_y), metal_highlight, 1)

        # Threads
        for tx in range(shank_x1 + 60, shank_x2 - 12, 10):
            cv2.line(img, (tx, shank_y1 + rim), (tx + 6, shank_y2 - rim), thread_color, 2, cv2.LINE_AA)

    elif category == CATEGORY_SCREW:
        # M4 x 20 countersunk screw: 7 mm head tapering to a 4 mm shank, pointed tip, 20 mm overall
        total_len, shank_w, head_w = mm(20.0), mm(4.0), mm(7.0)
        x0 = center_x - total_len // 2
        x_end = x0 + total_len - 1
        cone_end = x0 + mm(2.2)
        tip_start = x_end - mm(3.5)
        top, bottom = center_y - shank_w // 2, center_y - shank_w // 2 + shank_w - 1
        head_top = center_y - head_w // 2
        head_bottom = head_top + head_w - 1

        outline = np.array([
            [x0, head_top], [cone_end, top], [tip_start, top], [x_end, center_y],
            [tip_start, bottom], [cone_end, bottom], [x0, head_bottom]
        ], np.int32)
        inner = np.array([
            [x0 + rim, head_top + rim + 2], [cone_end, top + rim], [tip_start - 2, top + rim], [x_end - 8, center_y],
            [tip_start - 2, bottom - rim], [cone_end, bottom - rim], [x0 + rim, head_bottom - rim - 2]
        ], np.int32)
        cv2.fillPoly(img, [outline], metal_dark)
        cv2.fillPoly(img, [inner], metal_base)

        # Helical Screw Threads
        for tx in range(cone_end + 10, tip_start - 6, 9):
            cv2.line(img, (tx, top + rim), (tx + 5, bottom - rim), thread_color, 2, cv2.LINE_AA)

    elif category == CATEGORY_WASHER:
        # M8 flat washer: 16 mm outer diameter, 8.4 mm bore
        outer_radius = mm(16.0) // 2
        # One pixel over nominal: the dark outline ring drawn round the bore makes it read about
        # two pixels small, and 8.4 mm must land inside the M8 washer tolerance (8.2 - 8.6 mm)
        bore_radius = int(mm(8.4) // 2) + 1
        cv2.circle(img, (center_x, center_y), outer_radius, metal_dark, -1)
        cv2.circle(img, (center_x, center_y), outer_radius - rim, metal_base, -1)
        cv2.circle(img, (center_x, center_y), outer_radius - rim - 4, metal_highlight, 1, cv2.LINE_AA)
        cv2.circle(img, (center_x, center_y), bore_radius + rim, metal_dark, -1)
        cv2.circle(img, (center_x, center_y), bore_radius, background, -1)

    return img
