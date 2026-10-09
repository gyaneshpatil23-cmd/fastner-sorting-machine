"""
FILE: backend/opencv_measurement.py

WHAT THIS FILE DOES
    Measures a fastener in millimetres from a camera image using OpenCV.
    It finds the part's outline, measures it in pixels, then converts to mm with the camera calibration.

MAIN PARTS
    - Width-profile helpers: separate a bolt/screw outline into head and shank
    - Trust check: refuses to measure when the outline found is background, not a part
    - measure_fastener(): bolt and screw -> length, shank diameter, head width; nut and washer -> hole diameter, outer diameter
    - detect_multiple_fasteners(): finds every separate part in one image
    - draw_calibrated_overlay(): draws the box, dimension lines and decision badge on the image
    - dimension_engine: the shared measurement object the rest of the app uses

USED BY
    backend/inspection_pipeline.py
    frontend/main_window.py
    frontend/tab_camera_calibration.py
    run_all_tests.py
"""

import math
from typing import Dict, Any, List, Tuple, Optional
import cv2
import numpy as np

from backend.app_config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER,
    CATEGORY_UNKNOWN, CATEGORY_COLORS
)
from backend.sqlite_database import db_instance
from backend.app_logging import app_logger

# Outline length divided by the length of a rubber band stretched round it. Clean part outlines measure
# 1.05 - 1.16 (1.4 for a fully threaded bolt with every thread crest showing); patches of wood grain
# and shadow that were wrongly picked up as the part measured 1.6 - 2.3.
MAX_OUTLINE_ROUGHNESS = 1.5

# ============================================================================
# WIDTH-PROFILE HELPERS
# Split a bolt or screw outline into its head and its shank.
# ============================================================================
def axial_width_profile(contour: np.ndarray, rect) -> np.ndarray:
    """
    Returns the object's width (px) at every pixel step along its long axis.
    Works at any rotation, so head, shank and tip can be measured separately.
    """
    x, y, bw, bh = cv2.boundingRect(contour)
    mask = np.zeros((bh, bw), dtype=np.uint8)
    cv2.drawContours(mask, [contour - np.array([x, y])], -1, 255, cv2.FILLED)
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return np.zeros(0, dtype=np.float64)

    (cx, cy), _, _ = rect
    box = cv2.boxPoints(rect)
    edge_a, edge_b = box[1] - box[0], box[2] - box[1]
    axis = edge_a if np.linalg.norm(edge_a) >= np.linalg.norm(edge_b) else edge_b
    norm = float(np.linalg.norm(axis))
    if norm < 1e-6:
        return np.zeros(0, dtype=np.float64)
    ax, ay = axis / norm

    px = xs + x - cx
    py = ys + y - cy
    along = px * ax + py * ay
    across = -px * ay + py * ax

    bins = np.round(along - along.min()).astype(np.int64)
    count = int(bins.max()) + 1
    low = np.full(count, np.inf)
    high = np.full(count, -np.inf)
    np.minimum.at(low, bins, across)
    np.maximum.at(high, bins, across)
    return np.where(np.isfinite(low), high - low + 1.0, 0.0)


def measure_head_and_shank(widths: np.ndarray) -> Dict[str, float]:
    """
    Splits an elongated fastener's width profile into head and shank.
    Returns pixel values: total_len, shank_dia, head_width, head_len (0 if no distinct head).
    """
    total = len(widths)
    if total < 10:
        fallback = float(np.median(widths)) if total else 0.0
        return {"total_len": float(total), "shank_dia": fallback, "head_width": fallback, "head_len": 0.0}

    # The shank is the uniform middle section; the head sits at the wider end
    shank = max(1.0, float(np.median(widths[int(total * 0.30):int(total * 0.70)])))
    end = max(2, int(total * 0.08))
    if float(np.mean(widths[-end:])) > float(np.mean(widths[:end])):
        widths = widths[::-1]

    head_zone = widths[:int(total * 0.45)]
    wide = np.nonzero(head_zone > shank * 1.2)[0]
    head_len = int(wide[-1]) + 1 if wide.size >= 2 else 0
    head_width = float(np.percentile(widths[:head_len], 90)) if head_len else shank

    return {"total_len": float(total), "shank_dia": shank, "head_width": head_width, "head_len": float(head_len)}


# ============================================================================
# MEASUREMENT ENGINE
# Turns a camera image into millimetre dimensions.
# ============================================================================
class FastenerDimensionEngine:
    """Computes physical dimensions (mm) from high-resolution OpenCV frames."""

    def __init__(self):
        self.pixel_to_mm_ratio = db_instance.get_calibration("default")

    def reload_calibration(self):
        """Refreshes mm/pixel ratio from SQLite database."""
        self.pixel_to_mm_ratio = db_instance.get_calibration("default")

    # ========================================================================
    # MEASURE ONE FASTENER
    # Find the outline, then measure by type (bolt / nut / washer / screw).
    # ========================================================================
    def measure_fastener(
        self,
        cv_img: np.ndarray,
        category: str,
        roi_bbox: Optional[Tuple[int, int, int, int]] = None
    ) -> Dict[str, Any]:
        """
        Executes calibrated dimensional measurement on fastener.
        Returns dictionary containing lengths, diameters, widths, and pixel coordinates.
        """
        self.reload_calibration()
        scale = self.pixel_to_mm_ratio

        if cv_img is None or cv_img.size == 0:
            return {"success": False, "error": "Empty image provided."}

        h, w = cv_img.shape[:2]

        # If specific ROI bounding box provided, crop or focus
        if roi_bbox is not None:
            rx, ry, rw, rh = roi_bbox
            crop = cv_img[ry:ry+rh, rx:rx+rw]
        else:
            rx, ry, rw, rh = 0, 0, w, h
            crop = cv_img

        if crop.size == 0 or rw < 12 or rh < 12:
            return {"success": False, "error": "Inspection region is too small to measure."}

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Multi-polarity segmentation
        _, thresh_inv = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, thresh_reg = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        thresh = thresh_inv
        corners_val = (int(thresh[5, 5]) + int(thresh[5, rw-5]) + int(thresh[rh-5, 5]) + int(thresh[rh-5, rw-5])) / 4
        if corners_val > 127:
            thresh = thresh_reg

        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return {"success": False, "error": "No contour segmented for measurement."}

        # Pick largest outer contour
        contours_with_area = [(cv2.contourArea(c), idx, c) for idx, c in enumerate(contours)]
        contours_with_area.sort(key=lambda x: x[0], reverse=True)
        main_area, main_idx, main_cnt = contours_with_area[0]

        # Trust check: a real part sits inside the picture with background all round it. An outline that
        # runs into the edge is a patch of table, wood grain or shadow, and its "size" means nothing.
        bx, by, bw, bh = cv2.boundingRect(main_cnt)
        edge = 2
        touches_edge = bx <= edge or by <= edge or bx + bw >= rw - edge or by + bh >= rh - edge
        if touches_edge and roi_bbox is not None and (rw < w or rh < h):
            # The region may simply have been too tight for the part: try the whole picture once
            return self.measure_fastener(cv_img, category, roi_bbox=None)

        # A machined part has a smooth outline; a patch of background has a ragged one
        hull_perimeter = max(1.0, cv2.arcLength(cv2.convexHull(main_cnt), True))
        too_ragged = cv2.arcLength(main_cnt, True) / hull_perimeter > MAX_OUTLINE_ROUGHNESS

        if touches_edge or too_ragged:
            return {
                "success": False,
                "category": category,
                "bbox": (rx, ry, rw, rh),
                "error": ("The part's outline could not be separated from the background. "
                          "Measuring needs a plain background that contrasts with the part, "
                          "with the whole part inside the picture."),
            }

        # Shift contour coordinates back to full image if cropped
        if roi_bbox is not None:
            main_cnt_full = main_cnt + np.array([rx, ry])
        else:
            main_cnt_full = main_cnt

        rect = cv2.minAreaRect(main_cnt)
        (cx, cy), (dim1, dim2), angle = rect
        cx_full = cx + rx
        cy_full = cy + ry

        length_px = max(dim1, dim2)
        width_px = max(1.0, min(dim1, dim2))

        # Check for inner holes (Nut / Washer inner diameter)
        inner_dia_px = 0.0
        inner_cnt_full = None
        if hierarchy is not None and len(hierarchy) > 0 and main_idx < len(hierarchy[0]):
            child_idx = hierarchy[0][main_idx][2]
            while child_idx != -1 and child_idx < len(contours):
                c_area = cv2.contourArea(contours[child_idx])
                if c_area > (0.02 * main_area):
                    # Diameter of the circle with the same area as the hole. The traced outline runs along
                    # the metal pixels bordering the hole, so it reads about half a pixel wide (checked
                    # against test images of known size). An enclosing circle reads higher still: it
                    # grows with every rough pixel on the hole's edge.
                    hole_dia_px = 2.0 * math.sqrt(c_area / math.pi) - 0.5
                    inner_dia_px = max(inner_dia_px, hole_dia_px)
                    inner_cnt_full = contours[child_idx] + np.array([rx, ry])
                child_idx = hierarchy[0][child_idx][0]

        # Fallback inner hole calculation if hierarchy did not separate hole
        if inner_dia_px == 0.0 and category in [CATEGORY_NUT, CATEGORY_WASHER]:
            inner_dia_px = width_px * 0.45

        # Type-specific measurements
        measurements: Dict[str, Any] = {
            "success": True,
            "category": category,
            "scale_mm_per_px": scale,
            "length_mm": 0.0,
            "stem_dia_mm": 0.0,
            "head_width_mm": 0.0,
            "inner_dia_mm": 0.0,
            "outer_dia_mm": 0.0,
            "details": {}
        }

        if category == CATEGORY_BOLT:
            # Bolt: nominal length is measured under the head; diameter is the shank, not the head
            profile = measure_head_and_shank(axial_width_profile(main_cnt, rect))
            overall_mm = profile["total_len"] * scale
            head_height_mm = profile["head_len"] * scale
            length_mm = overall_mm - head_height_mm

            measurements["length_mm"] = round(length_mm, 2)
            measurements["stem_dia_mm"] = round(profile["shank_dia"] * scale, 2)
            measurements["head_width_mm"] = round(profile["head_width"] * scale, 2)
            measurements["details"]["overall_length_mm"] = round(overall_mm, 2)
            measurements["details"]["head_height_mm"] = round(head_height_mm, 2)
            measurements["details"]["thread_length_est_mm"] = round(length_mm * 0.70, 2)

        elif category == CATEGORY_NUT:
            # Nut: Inner-hole diameter & Across-flats outer width
            inner_dia_mm = inner_dia_px * scale
            outer_af_mm = width_px * scale
            outer_ac_mm = length_px * scale

            measurements["inner_dia_mm"] = round(inner_dia_mm, 2)
            measurements["outer_dia_mm"] = round(outer_af_mm, 2)
            measurements["details"]["across_corners_mm"] = round(outer_ac_mm, 2)

        elif category == CATEGORY_WASHER:
            # Washer: Inner hole diameter & Outer circular diameter
            inner_dia_mm = inner_dia_px * scale
            outer_dia_mm = length_px * scale
            wall_thick_mm = max(0.5, (outer_dia_mm - inner_dia_mm) / 2.0)

            measurements["inner_dia_mm"] = round(inner_dia_mm, 2)
            measurements["outer_dia_mm"] = round(outer_dia_mm, 2)
            measurements["details"]["rim_thickness_mm"] = round(wall_thick_mm, 2)

        elif category == CATEGORY_SCREW:
            # Screw: overall length (countersunk convention), measured head width, shank diameter
            profile = measure_head_and_shank(axial_width_profile(main_cnt, rect))

            measurements["length_mm"] = round(profile["total_len"] * scale, 2)
            measurements["stem_dia_mm"] = round(profile["shank_dia"] * scale, 2)
            measurements["head_width_mm"] = round(profile["head_width"] * scale, 2)
            measurements["details"]["head_height_mm"] = round(profile["head_len"] * scale, 2)

        else:
            measurements["length_mm"] = round(length_px * scale, 2)
            measurements["stem_dia_mm"] = round(width_px * scale, 2)

        measurements["bbox"] = cv2.boundingRect(main_cnt_full)
        measurements["contour"] = main_cnt_full
        measurements["inner_contour"] = inner_cnt_full
        return measurements

    # ========================================================================
    # MULTI-FASTENER MODE
    # Find every separate part in one image.
    # ========================================================================
    def detect_multiple_fasteners(self, cv_img: np.ndarray, min_area_ratio: float = 0.005) -> List[Dict[str, Any]]:
        """
        Segments and measures multiple fasteners present in the inspection area simultaneously.
        Returns a list of detected fastener objects with individual ROIs and measurements.
        """
        if cv_img is None or cv_img.size == 0:
            return []

        h, w = cv_img.shape[:2]
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        _, thresh1 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, thresh2 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        thresh = thresh1 if np.sum(thresh1[0:5, 0:5]) == 0 else thresh2

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = w * h * min_area_ratio
        max_area = w * h * 0.85

        detected_objects = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area < area < max_area:
                x, y, bw, bh = cv2.boundingRect(cnt)
                # Pad ROI slightly
                pad = 10
                px = max(0, x - pad)
                py = max(0, y - pad)
                pbw = min(w - px, bw + 2 * pad)
                pbh = min(h - py, bh + 2 * pad)

                roi_bbox = (px, py, pbw, pbh)
                detected_objects.append({
                    "bbox": (x, y, bw, bh),
                    "roi_bbox": roi_bbox,
                    "area": area,
                    "contour": cnt
                })

        # Sort left-to-right / top-to-bottom
        detected_objects.sort(key=lambda o: (o["bbox"][1] // 100, o["bbox"][0]))
        return detected_objects

    # ========================================================================
    # RESULT OVERLAY
    # Draw the box, dimension lines and decision badge on the image.
    # ========================================================================
    def draw_calibrated_overlay(
        self,
        cv_img: np.ndarray,
        measurements: Dict[str, Any],
        decision: str = "ACCEPT",
        target_tray: Optional[int] = None
    ) -> np.ndarray:
        """
        Draws high-precision engineering dimensional overlay with dimension arrows,
        exact mm callouts, and sorting decision badge onto image.
        """
        if cv_img is None:
            return cv_img

        annotated = cv_img.copy()
        h, w = annotated.shape[:2]

        bbox = measurements.get("bbox")
        if not bbox:
            return annotated

        x, y, bw, bh = bbox
        category = measurements.get("category", "FASTENER")
        scale = measurements.get("scale_mm_per_px", self.pixel_to_mm_ratio)

        # Color based on decision: ACCEPT -> Green, REINSPECT -> Amber, REJECT -> Red
        if decision == "ACCEPT":
            status_bgr = (40, 180, 40)
            status_text = "ACCEPT"
        elif decision == "REINSPECT":
            status_bgr = (0, 165, 255)
            status_text = "REINSPECT"
        elif decision == "IDENTIFIED":
            # Sorted by type only: the size was measured but not judged
            status_bgr = (216, 78, 29)
            status_text = "IDENTIFIED"
        else:
            status_bgr = (30, 30, 220)
            status_text = "REJECT"

        # Scale line weight and text with the image so the overlay stays readable on large photos
        k = max(1.0, max(h, w) / 800.0)
        thin = max(1, int(round(k)))
        thick = max(2, int(round(2 * k)))
        gap = int(10 * k)

        # 1. Bounding box & Corner Brackets
        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), status_bgr, thin, cv2.LINE_AA)
        corner_len = min(int(20 * k), bw // 4, bh // 4)
        for cx_pt, cy_pt, dx, dy in [
            (x, y, 1, 1), (x + bw, y, -1, 1), (x, y + bh, 1, -1), (x + bw, y + bh, -1, -1)
        ]:
            cv2.line(annotated, (cx_pt, cy_pt), (cx_pt + dx * corner_len, cy_pt), status_bgr, thick)
            cv2.line(annotated, (cx_pt, cy_pt), (cx_pt, cy_pt + dy * corner_len), status_bgr, thick)

        # 2. Draw Dimension Lines (Arrows & MM Text)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.45 * k

        len_val = measurements.get("length_mm") or measurements.get("outer_dia_mm", 0.0)
        len_label = f"L: {len_val:.1f}mm" if measurements.get("length_mm") else f"OD: {len_val:.1f}mm"
        dia_val = measurements.get("stem_dia_mm") or measurements.get("inner_dia_mm", 0.0)
        dia_label = f"Dia: {dia_val:.1f}mm" if measurements.get("stem_dia_mm") else f"ID: {dia_val:.1f}mm"

        # The length callout goes on whichever side of the box the fastener's long axis runs along
        horiz_label, vert_label = (len_label, dia_label) if bw >= bh else (dia_label, len_label)

        # Horizontal Dimension Line
        dim_y = max(int(15 * k), y - gap)
        cv2.arrowedLine(annotated, (x + gap, dim_y), (x, dim_y), (255, 255, 0), thin, tipLength=0.15)
        cv2.arrowedLine(annotated, (x + bw - gap, dim_y), (x + bw, dim_y), (255, 255, 0), thin, tipLength=0.15)
        cv2.line(annotated, (x, dim_y), (x + bw, dim_y), (255, 255, 0), thin)
        (lw, _), _ = cv2.getTextSize(horiz_label, font, font_scale, thin)
        cv2.putText(annotated, horiz_label, (x + bw // 2 - lw // 2, dim_y - int(4 * k)), font, font_scale, (255, 255, 0), thin, cv2.LINE_AA)

        # Vertical Dimension Line
        dim_x = min(w - int(15 * k), x + bw + int(15 * k))
        cv2.arrowedLine(annotated, (dim_x, y + gap), (dim_x, y), (0, 255, 255), thin, tipLength=0.15)
        cv2.arrowedLine(annotated, (dim_x, y + bh - gap), (dim_x, y + bh), (0, 255, 255), thin, tipLength=0.15)
        cv2.line(annotated, (dim_x, y), (dim_x, y + bh), (0, 255, 255), thin)
        (vw, _), _ = cv2.getTextSize(vert_label, font, font_scale, thin)
        vert_x = dim_x + int(4 * k)
        if vert_x + vw > w:
            vert_x = max(0, dim_x - int(4 * k) - vw)
        cv2.putText(annotated, vert_label, (vert_x, y + bh // 2), font, font_scale, (0, 255, 255), thin, cv2.LINE_AA)

        # 3. Header Badge: Category + Decision + Assigned Bin
        tray_str = f" -> Bin {target_tray}" if target_tray else ""
        header_text = f"{category} | {status_text}{tray_str}"
        badge_scale = 0.55 * k
        (tw, th), _ = cv2.getTextSize(header_text, font, badge_scale, thick)
        pad_x, pad_y = int(7 * k), int(6 * k)
        # Sits above the dimension callout so the two never overlap
        badge_y = max(th + pad_y + int(4 * k), y - int(34 * k))
        cv2.rectangle(annotated, (x, badge_y - th - pad_y), (x + tw + 2 * pad_x, badge_y + int(4 * k)), status_bgr, -1)
        cv2.putText(annotated, header_text, (x + pad_x, badge_y - int(2 * k)), font, badge_scale, (255, 255, 255), thin, cv2.LINE_AA)

        return annotated

# ============================================================================
# SHARED INSTANCE
# Created once here; every other file imports this same object.
# ============================================================================
dimension_engine = FastenerDimensionEngine()
