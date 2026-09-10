"""
Image utilities module for AI Fastener Inspection System.
Handles image loading, color space conversions for PySide6,
OpenCV object region localization, engineering overlays, and sample generation.
"""

import os
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap

from config import CATEGORY_COLORS, CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER
from logger import app_logger

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
    box_w, box_h = int(w * 0.45), int(h * 0.50)
    cx, cy = w // 2, h // 2
    x1, y1 = cx - box_w // 2, cy - box_h // 2
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

def render_synthetic_fastener(category: str, width: int = 640, height: int = 480) -> np.ndarray:
    """Renders a clean engineering drawing of a fastener on industrial inspection mat."""
    # Matte gray background with subtle grid
    img = np.full((height, width, 3), 238, dtype=np.uint8)
    
    # Draw faint grid (inspection surface)
    grid_color = (222, 222, 222)
    for gx in range(0, width, 40):
        cv2.line(img, (gx, 0), (gx, height), grid_color, 1)
    for gy in range(0, height, 40):
        cv2.line(img, (0, gy), (width, gy), grid_color, 1)
        
    center_x, center_y = width // 2, height // 2
    metal_dark = (60, 60, 60)
    metal_base = (140, 140, 140)
    metal_highlight = (195, 195, 195)
    
    if category == CATEGORY_NUT:
        # Hex Nut Drawing
        radius = 100
        angles = np.linspace(0, 2 * np.pi, 7)[:-1]
        pts = np.array([[int(center_x + radius * np.cos(a)), int(center_y + radius * np.sin(a))] for a in angles], np.int32)
        cv2.fillPoly(img, [pts], metal_base)
        cv2.polylines(img, [pts], True, metal_dark, 4, cv2.LINE_AA)
        
        # Center Hole
        cv2.circle(img, (center_x, center_y), 45, (238, 238, 238), -1)
        cv2.circle(img, (center_x, center_y), 45, metal_dark, 3, cv2.LINE_AA)
        # Inner threads
        for tr in [40, 35, 30]:
            cv2.ellipse(img, (center_x, center_y), (tr, tr), 0, 0, 360, (110, 110, 110), 1, cv2.LINE_AA)
            
    elif category == CATEGORY_BOLT:
        # Hex Head + Threaded Shaft
        # Head (Left)
        hx = center_x - 140
        hy = center_y
        head_pts = np.array([
            [hx - 40, hy - 65], [hx, hy - 65], [hx + 25, hy],
            [hx, hy + 65], [hx - 40, hy + 65], [hx - 60, hy]
        ], np.int32)
        cv2.fillPoly(img, [head_pts], metal_base)
        cv2.polylines(img, [head_pts], True, metal_dark, 3, cv2.LINE_AA)
        
        # Shaft
        sx1 = hx + 25
        sx2 = center_x + 160
        sy1 = center_y - 32
        sy2 = center_y + 32
        cv2.rectangle(img, (sx1, sy1), (sx2, sy2), metal_base, -1)
        cv2.rectangle(img, (sx1, sy1), (sx2, sy2), metal_dark, 3)
        
        # Threads
        for tx in range(sx1 + 30, sx2 - 10, 12):
            cv2.line(img, (tx, sy1), (tx + 8, sy2), (80, 80, 80), 2, cv2.LINE_AA)
            
    elif category == CATEGORY_SCREW:
        # Countersunk screw head + tapered pointed threaded shaft
        sx1 = center_x - 130
        sy = center_y
        # Head
        cv2.ellipse(img, (sx1, sy), (20, 50), 0, 0, 360, metal_base, -1)
        cv2.ellipse(img, (sx1, sy), (20, 50), 0, 0, 360, metal_dark, 3, cv2.LINE_AA)
        # Drive Slot
        cv2.line(img, (sx1 - 10, sy - 25), (sx1 - 10, sy + 25), metal_dark, 4)
        
        # Shaft tapering to point
        shaft_pts = np.array([
            [sx1, sy - 24], [center_x + 100, sy - 18], [center_x + 160, sy],
            [center_x + 100, sy + 18], [sx1, sy + 24]
        ], np.int32)
        cv2.fillPoly(img, [shaft_pts], metal_base)
        cv2.polylines(img, [shaft_pts], True, metal_dark, 3, cv2.LINE_AA)
        
        # Helical Screw Threads
        for tx in range(sx1 + 25, center_x + 140, 15):
            t_half = int(24 - (tx - sx1) * 0.08)
            cv2.line(img, (tx, sy - t_half), (tx + 10, sy + t_half), (70, 70, 70), 2, cv2.LINE_AA)
            
    elif category == CATEGORY_WASHER:
        # Flat annular ring
        cv2.circle(img, (center_x, center_y), 95, metal_base, -1)
        cv2.circle(img, (center_x, center_y), 95, metal_dark, 3, cv2.LINE_AA)
        cv2.circle(img, (center_x, center_y), 45, (238, 238, 238), -1)
        cv2.circle(img, (center_x, center_y), 45, metal_dark, 3, cv2.LINE_AA)
        cv2.circle(img, (center_x, center_y), 85, metal_highlight, 1, cv2.LINE_AA)
        
    return img
