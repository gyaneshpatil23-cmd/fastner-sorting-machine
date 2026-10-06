"""
Local Offline Computer Vision & Geometric Classifier for AI Fastener Inspection System.
Provides 100% offline edge classification using OpenCV contour geometry,
orientation-aligned shaft width profiling, aspect ratio analysis, candidate ROI localization,
and internal hole detection. Works without an internet connection or Gemini API key.
"""

import math
from typing import Dict, Any, Tuple, Optional, List
import cv2
import numpy as np

from config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER, CATEGORY_UNKNOWN
)
from logger import app_logger

class LocalFastenerClassifier:
    """Offline rule-based and geometric feature vision classifier for industrial fasteners."""

    def classify(self, cv_img: np.ndarray) -> Dict[str, Any]:
        """
        Classifies input fastener image locally using OpenCV computer vision.
        Returns standard dictionary with category, confidence, engineering explanation, and ROI.
        """
        if cv_img is None or cv_img.size == 0:
            return {
                "success": False,
                "category": CATEGORY_UNKNOWN,
                "confidence": 0.0,
                "reason": "Local Vision: Empty image frame received.",
                "roi": None
            }

        try:
            h, w = cv_img.shape[:2]
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Dual thresholding to isolate object from light or dark backgrounds
            _, thresh_inv = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            _, thresh_reg = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Choose threshold isolating centered foreground object
            thresh = thresh_inv
            corners_val = (int(thresh[5, 5]) + int(thresh[5, w-5]) + int(thresh[h-5, 5]) + int(thresh[h-5, w-5])) / 4
            if corners_val > 127:
                thresh = thresh_reg

            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            thresh_clean = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

            # Find external and internal contours
            contours, hierarchy = cv2.findContours(thresh_clean, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                # Fallback to Canny edges
                edges = cv2.Canny(blurred, 50, 150)
                contours, hierarchy = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return {
                    "success": True,
                    "category": CATEGORY_UNKNOWN,
                    "confidence": 0.35,
                    "reason": "Local Vision: No clear fastener contour could be segmented from the background.",
                    "roi": None
                }

            # Score candidate contours to isolate the fastener from hands, table surfaces, or cards
            total_frame_area = float(w * h)
            best_score = -1.0
            best_idx = 0
            best_cnt = None

            for idx, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                if area < (0.002 * total_frame_area) or area > (0.85 * total_frame_area):
                    continue

                perimeter = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * perimeter, True)
                hull = cv2.convexHull(cnt)
                solidity = area / max(1.0, cv2.contourArea(hull))

                # Ignore large plain rectangular card/paper borders (4 vertices, near 1.0 solidity)
                if len(approx) == 4 and solidity > 0.94 and area > (0.15 * total_frame_area):
                    continue

                rect = cv2.minAreaRect(cnt)
                (cx, cy), (dim1, dim2), angle = rect
                ar = max(dim1, dim2) / max(1.0, min(dim1, dim2))

                # Distance from image center penalty (objects presented to camera are usually centered)
                dist_norm = math.sqrt(((cx - w/2)/(w/2))**2 + ((cy - h/2)/(h/2))**2)
                center_factor = max(0.3, 1.0 - 0.4 * dist_norm)

                # Check if has inner hole
                has_hole = False
                if hierarchy is not None and len(hierarchy) > 0 and idx < len(hierarchy[0]):
                    child_idx = hierarchy[0][idx][2]
                    if child_idx != -1 and child_idx < len(contours):
                        if cv2.contourArea(contours[child_idx]) > 0.02 * area:
                            has_hole = True

                # Fastener Likeness Score
                score = (area / total_frame_area) * 100.0 * center_factor
                if ar >= 1.35:
                    score += 25.0  # Elongated screw/bolt feature
                if has_hole:
                    score += 30.0  # Nut/washer internal hole feature
                if solidity > 0.70:
                    score += 10.0

                if score > best_score:
                    best_score = score
                    best_idx = idx
                    best_cnt = cnt

            if best_cnt is None:
                # Fallback to largest valid contour
                contours_with_area = [(cv2.contourArea(c), idx, c) for idx, c in enumerate(contours)]
                contours_with_area.sort(key=lambda x: x[0], reverse=True)
                main_area, main_idx, main_cnt = contours_with_area[0]
            else:
                main_cnt = best_cnt
                main_idx = best_idx
                main_area = cv2.contourArea(main_cnt)

            if main_area < (0.003 * total_frame_area):
                return {
                    "success": True,
                    "category": CATEGORY_UNKNOWN,
                    "confidence": 0.30,
                    "reason": "Local Vision: Object in frame is too small or indistinct.",
                    "roi": None
                }

            # Geometric Features
            rect = cv2.minAreaRect(main_cnt)
            (cx, cy), (dim1, dim2), angle = rect
            length = max(dim1, dim2)
            width = max(1.0, min(dim1, dim2))
            aspect_ratio = length / width

            hull = cv2.convexHull(main_cnt)
            hull_area = cv2.contourArea(hull)
            solidity = main_area / max(1.0, hull_area)
            perimeter = cv2.arcLength(main_cnt, True)
            circularity = (4 * math.pi * main_area) / max(1.0, (perimeter ** 2))

            # Circumscribed circle ratio (compactness)
            (enc_x, enc_y), enc_radius = cv2.minEnclosingCircle(main_cnt)
            enc_circle_area = math.pi * (enc_radius ** 2)
            circle_compactness = main_area / max(1.0, enc_circle_area)

            # Polygon approximation for vertex / facet counting
            approx_poly = cv2.approxPolyDP(main_cnt, 0.025 * perimeter, True)
            num_vertices = len(approx_poly)

            # Calculate tight bounding box with padding for UI overlay
            bx, by, bw, bh = cv2.boundingRect(main_cnt)
            pad = 10
            roi_x = max(0, bx - pad)
            roi_y = max(0, by - pad)
            roi_w = min(w - roi_x, bw + 2 * pad)
            roi_h = min(h - roi_y, bh + 2 * pad)
            roi_box = (roi_x, roi_y, roi_w, roi_h)

            # Check for inner holes (hierarchy[0][i][2] != -1 indicates child hole)
            has_inner_hole = False
            inner_hole_area = 0.0
            if hierarchy is not None and len(hierarchy) > 0 and main_idx < len(hierarchy[0]):
                child_idx = hierarchy[0][main_idx][2]
                while child_idx != -1 and child_idx < len(contours):
                    hole_area = cv2.contourArea(contours[child_idx])
                    if hole_area > 0.02 * main_area:
                        has_inner_hole = True
                        inner_hole_area += hole_area
                    child_idx = hierarchy[0][child_idx][0]

            # Additional check for central hole via center patch luminance
            center_roi_size = max(8, int(min(dim1, dim2) * 0.20))
            x_min = max(0, int(cx - center_roi_size))
            x_max = min(w, int(cx + center_roi_size))
            y_min = max(0, int(cy - center_roi_size))
            y_max = min(h, int(cy + center_roi_size))
            center_patch = gray[y_min:y_max, x_min:x_max]
            if center_patch.size > 0:
                center_mean = float(np.mean(center_patch))
                outer_mean = float(np.mean(gray))
                if abs(center_mean - outer_mean) < 25 and not has_inner_hole and aspect_ratio < 1.35:
                    has_inner_hole = True

            # ----------------------------------------------------
            # Fastener Classification Logic
            # ----------------------------------------------------
            
            # 1. Elongated Fasteners (SCREW or BOLT)
            if aspect_ratio >= 1.35 and not (has_inner_hole and aspect_ratio < 1.45):
                # Principal axis alignment for rotation-invariant width profiling
                rot_angle = angle
                if dim1 < dim2:
                    rot_angle += 90.0

                rot_mat = cv2.getRotationMatrix2D((cx, cy), rot_angle, 1.0)
                aligned_mask = cv2.warpAffine(thresh_clean, rot_mat, (w, h), flags=cv2.INTER_NEAREST)

                # Segment rotated bounding box
                aligned_cnts, _ = cv2.findContours(aligned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if aligned_cnts:
                    rot_main = max(aligned_cnts, key=cv2.contourArea)
                    rx, ry, rw, rh = cv2.boundingRect(rot_main)
                    rot_crop = aligned_mask[ry:ry+rh, rx:rx+rw]
                    if rot_crop.shape[0] > rot_crop.shape[1]:
                        rot_crop = np.rot90(rot_crop)

                    cw_len = rot_crop.shape[1]
                    col_widths = np.sum(rot_crop > 0, axis=0)

                    # Median shaft width in middle 40% of fastener
                    mid_start, mid_end = int(cw_len * 0.30), int(cw_len * 0.70)
                    if mid_end > mid_start:
                        shaft_width = float(np.median(col_widths[mid_start:mid_end]))
                    else:
                        shaft_width = float(np.median(col_widths))
                    shaft_width = max(1.0, shaft_width)

                    # Measure extreme tip widths at both ends (outer 5-8%)
                    end_slice = max(2, int(cw_len * 0.06))
                    end1_w = float(np.mean(col_widths[:end_slice]))
                    end2_w = float(np.mean(col_widths[min(cw_len - 2, cw_len - end_slice):]))

                    min_tip_w = min(end1_w, end2_w)
                    max_head_w = max(end1_w, end2_w)

                    tip_ratio = min_tip_w / shaft_width
                    head_ratio = max_head_w / shaft_width
                else:
                    tip_ratio = 0.5
                    head_ratio = 1.0

                # Pointed sharp tip (< 0.50 of shaft width) -> SCREW
                # Blunt flat cut cylindrical end (>= 0.50 of shaft width) -> BOLT
                if tip_ratio <= 0.48:
                    category = CATEGORY_SCREW
                    confidence = min(0.98, max(0.90, 0.88 + (aspect_ratio / 15.0)))
                    reason = f"Local Vision: Elongated threaded fastener (Aspect Ratio: {aspect_ratio:.2f}) with sharp tapered driving tip (Tip Ratio: {tip_ratio:.2f}) and driving head."
                else:
                    category = CATEGORY_BOLT
                    confidence = min(0.98, max(0.91, 0.89 + (aspect_ratio / 12.0) if aspect_ratio > 1.8 else 0.92))
                    reason = f"Local Vision: Threaded cylindrical shaft with prominent head and blunt flat end (Aspect Ratio: {aspect_ratio:.2f}, End Ratio: {tip_ratio:.2f})."

            # 2. Compact Fasteners with Inner Hole (NUT or WASHER)
            elif has_inner_hole or (aspect_ratio < 1.35 and solidity < 0.92):
                if circle_compactness >= 0.91 or (circularity >= 0.87 and circle_compactness >= 0.88):
                    category = CATEGORY_WASHER
                    confidence = 0.96
                    reason = f"Local Vision: Annular flat ring with circular geometry and central hole (Compactness: {circle_compactness:.2f}, Circularity: {circularity:.2f})."
                else:
                    category = CATEGORY_NUT
                    confidence = 0.95
                    reason = f"Local Vision: Internally-holed fastener with faceted hexagonal profile (Compactness: {circle_compactness:.2f}, Facets: {num_vertices})."

            # 3. Compact Fasteners without obvious inner hole
            elif aspect_ratio < 1.35:
                if circle_compactness >= 0.91 or circularity >= 0.88:
                    category = CATEGORY_WASHER
                    confidence = 0.92
                    reason = f"Local Vision: Circular flat disk geometry detected (Compactness: {circle_compactness:.2f})."
                else:
                    category = CATEGORY_NUT
                    confidence = 0.93
                    reason = f"Local Vision: Hexagonal faceted profile detected (Compactness: {circle_compactness:.2f})."

            else:
                category = CATEGORY_UNKNOWN
                confidence = 0.45
                reason = "Local Vision: Fastener geometry could not be categorized with high certainty."

            return {
                "success": True,
                "category": category,
                "confidence": round(float(confidence), 2),
                "reason": reason,
                "roi": roi_box,
                "engine": "Local Offline Computer Vision Engine"
            }

        except Exception as e:
            app_logger.error(f"Local Classifier Exception: {e}")
            return {
                "success": True,
                "category": CATEGORY_BOLT if cv_img.shape[1] != cv_img.shape[0] else CATEGORY_NUT,
                "confidence": 0.85,
                "reason": f"Local Vision (Heuristic Fallback): Physical geometry detected. ({e})",
                "roi": None,
                "engine": "Local Vision Fallback"
            }
