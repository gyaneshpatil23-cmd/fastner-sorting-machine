"""
Verification & Decision Engine module for AI Fastener Inspection System.
Cross-checks vision predictions against ISO specifications and dimensional tolerances.
Determines ACCEPT / REINSPECT / REJECT status, maps to 10-tray sorting chute angles,
and detects inconsistencies.
"""

from typing import Dict, Any, Optional, Tuple, List
from backend.config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER, CATEGORY_UNKNOWN
)
from backend.database import db_instance
from backend.logger import app_logger, log_session_step

class FastenerVerificationEngine:
    """Evaluates measured dimensions against tolerance database and assigns sorting actions."""

    def verify_and_decide(
        self,
        category: str,
        confidence: float,
        measurements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cross-checks physical measurements against specifications.
        Returns:
            {
                "decision": "ACCEPT" | "REINSPECT" | "REJECT",
                "matched_size": str,
                "nominal_spec": dict,
                "assigned_tray": int,
                "servo_angle": int,
                "reason": str,
                "inconsistency_detected": bool,
                "tolerance_errors": list
            }
        """
        category = category.upper()
        if category == CATEGORY_UNKNOWN or not measurements.get("success", False):
            return self._create_reject_decision(
                category="UNKNOWN",
                reason="Object could not be recognized as a valid fastener category.",
                tray_id=10,
                servo_angle=180
            )

        # Retrieve enabled specifications for this category
        specs = db_instance.get_specifications(category)
        if not specs:
            return self._create_reject_decision(
                category=category,
                reason=f"No specification standards configured for category '{category}'.",
                tray_id=10,
                servo_angle=180
            )

        # Extract measured dimensions
        stem_dia = measurements.get("stem_dia_mm", 0.0)
        length = measurements.get("length_mm", 0.0)
        inner_dia = measurements.get("inner_dia_mm", 0.0)
        outer_dia = measurements.get("outer_dia_mm", 0.0)

        # Primary matching dimension
        target_dim = stem_dia if category in [CATEGORY_BOLT, CATEGORY_SCREW] else inner_dia

        # Find best matching specification based on nominal diameter & length
        best_spec = None
        min_dim_error = float("inf")

        for spec in specs:
            spec_nom_dia = spec["nominal_diameter"]
            dia_diff = abs(target_dim - spec_nom_dia)

            # For bolts/screws, also consider length difference
            if category in [CATEGORY_BOLT, CATEGORY_SCREW] and spec.get("nominal_length"):
                len_diff = abs(length - spec["nominal_length"])
                total_error = dia_diff * 2.0 + len_diff
            else:
                total_error = dia_diff

            if total_error < min_dim_error:
                min_dim_error = total_error
                best_spec = spec

        if not best_spec:
            return self._create_reject_decision(
                category=category,
                reason="No matching fastener standard could be found.",
                tray_id=10,
                servo_angle=180
            )

        # Validate against strict tolerance limits of the matched spec
        tolerance_errors = []
        is_consistent = True

        if category in [CATEGORY_BOLT, CATEGORY_SCREW]:
            # Stem Diameter tolerance check
            min_dia = best_spec["min_diameter"]
            max_dia = best_spec["max_diameter"]
            if not (min_dia <= stem_dia <= max_dia):
                tolerance_errors.append(
                    f"Stem diameter ({stem_dia:.2f}mm) out of spec [{min_dia:.2f} - {max_dia:.2f}mm]"
                )
                is_consistent = False

            # Length tolerance check (if defined)
            if best_spec.get("min_length") and best_spec.get("max_length"):
                min_len = best_spec["min_length"]
                max_len = best_spec["max_length"]
                if not (min_len <= length <= max_len):
                    tolerance_errors.append(
                        f"Length ({length:.2f}mm) out of spec [{min_len:.2f} - {max_len:.2f}mm]"
                    )
                    is_consistent = False

        elif category in [CATEGORY_NUT, CATEGORY_WASHER]:
            # Inner Diameter tolerance check
            min_in = best_spec["min_inner_dia"] or best_spec["min_diameter"]
            max_in = best_spec["max_inner_dia"] or best_spec["max_diameter"]
            if not (min_in <= inner_dia <= max_in):
                tolerance_errors.append(
                    f"Inner hole dia ({inner_dia:.2f}mm) out of spec [{min_in:.2f} - {max_in:.2f}mm]"
                )
                is_consistent = False

            # Outer Diameter tolerance check (if defined)
            if best_spec.get("min_outer_dia") and best_spec.get("max_outer_dia"):
                min_out = best_spec["min_outer_dia"]
                max_out = best_spec["max_outer_dia"]
                if not (min_out <= outer_dia <= max_out):
                    tolerance_errors.append(
                        f"Outer dia ({outer_dia:.2f}mm) out of spec [{min_out:.2f} - {max_out:.2f}mm]"
                    )
                    is_consistent = False

        matched_size_name = best_spec["size_name"]

        # Map to sorting tray
        target_tray, target_angle = self._find_target_tray(category, matched_size_name, is_consistent)

        # Formulate final decision
        if is_consistent and confidence >= 0.70:
            decision = "ACCEPT"
            reason = f"Verified {matched_size_name} within ISO dimensional tolerances. Routing to Tray {target_tray} (Chute Angle: {target_angle}°)."
        elif is_consistent and confidence < 0.70:
            decision = "REINSPECT"
            reason = f"Dimensions match {matched_size_name}, but visual confidence ({int(confidence*100)}%) is low. Reinspection recommended."
        else:
            decision = "REJECT"
            reason = f"Dimensional Mismatch for {matched_size_name}: {'; '.join(tolerance_errors)}. Routing to Reject Tray {target_tray}."

        log_session_step("DECISION", f"{decision}: {matched_size_name} -> Tray {target_tray} ({target_angle}°)")

        return {
            "decision": decision,
            "matched_size": matched_size_name,
            "nominal_spec": best_spec,
            "assigned_tray": target_tray,
            "servo_angle": target_angle,
            "reason": reason,
            "inconsistency_detected": not is_consistent,
            "tolerance_errors": tolerance_errors
        }

    def _find_target_tray(self, category: str, size_name: str, is_consistent: bool) -> Tuple[int, int]:
        """Finds configured tray and servo angle in the 10-tray mapping table."""
        trays = db_instance.get_trays()
        
        # If not consistent, route to Tray 10 (Reject)
        if not is_consistent:
            for t in trays:
                if t["assigned_category"] == "REJECT" or t["tray_id"] == 10:
                    return t["tray_id"], t["servo_angle"]
            return 10, 180

        # Exact match on size name
        for t in trays:
            if t["enabled"] and t["assigned_size"] == size_name:
                return t["tray_id"], t["servo_angle"]

        # Category match
        for t in trays:
            if t["enabled"] and t["assigned_category"] == category:
                return t["tray_id"], t["servo_angle"]

        # Default Tray 10 (Reject/Unassigned)
        return 10, 180

    def _create_reject_decision(self, category: str, reason: str, tray_id: int = 10, servo_angle: int = 180) -> Dict[str, Any]:
        return {
            "decision": "REJECT",
            "matched_size": "Non-Standard / Reject",
            "nominal_spec": None,
            "assigned_tray": tray_id,
            "servo_angle": servo_angle,
            "reason": reason,
            "inconsistency_detected": True,
            "tolerance_errors": [reason]
        }

verification_engine = FastenerVerificationEngine()
