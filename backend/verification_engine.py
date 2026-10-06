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

    # Bin id reported when a part cannot be routed anywhere (no physical sort is performed)
    NO_BIN = 0
    # Key diameter off by more than this fraction of the nearest standard size = not a known fastener
    GROSS_MISMATCH_RATIO = 0.5

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
                reason="Object could not be recognized as a valid fastener category."
            )

        # Retrieve enabled specifications for this category
        specs = db_instance.get_specifications(category)
        if not specs:
            return self._create_reject_decision(
                category=category,
                reason=f"No specification standards configured for category '{category}'."
            )

        # Extract measured dimensions
        stem_dia = measurements.get("stem_dia_mm", 0.0)
        length = measurements.get("length_mm", 0.0)
        inner_dia = measurements.get("inner_dia_mm", 0.0)
        outer_dia = measurements.get("outer_dia_mm", 0.0)

        # Primary matching dimension
        target_dim = stem_dia if category in [CATEGORY_BOLT, CATEGORY_SCREW] else inner_dia

        # Match the thread size (diameter) first, then the closest length within that size.
        # Mixing the two lets a length coincidence pick the wrong thread size (an M4 x 35 read as M6 x 30).
        def match_error(spec: Dict[str, Any]) -> Tuple[float, float]:
            dia_diff = round(abs(target_dim - spec["nominal_diameter"]), 3)
            len_diff = 0.0
            if category in [CATEGORY_BOLT, CATEGORY_SCREW] and spec.get("nominal_length"):
                len_diff = abs(length - spec["nominal_length"])
            return dia_diff, len_diff

        best_spec = min(specs, key=match_error, default=None)

        if not best_spec:
            return self._create_reject_decision(
                category=category,
                reason="No matching fastener standard could be found."
            )

        # A part whose key diameter is nowhere near any configured size is not a known fastener at all
        nearest_dia = min(specs, key=lambda s: abs(target_dim - s["nominal_diameter"]))["nominal_diameter"]
        if abs(target_dim - nearest_dia) > self.GROSS_MISMATCH_RATIO * nearest_dia:
            dim_name = "shank diameter" if category in [CATEGORY_BOLT, CATEGORY_SCREW] else "hole diameter"
            decision = self._create_reject_decision(
                category=category,
                reason=(
                    f"Measured {dim_name} ({target_dim:.1f} mm) is far outside every configured "
                    f"{category.lower()} size (nearest is {nearest_dia:g} mm). Not a recognized standard fastener."
                )
            )
            decision["unrecognized"] = True
            return decision

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
        target_tray, target_angle, has_bin = self._find_target_tray(category, matched_size_name, is_consistent)

        # Formulate final decision
        if is_consistent and confidence >= 0.70:
            decision = "ACCEPT"
            if has_bin:
                reason = f"Verified {matched_size_name} within ISO dimensional tolerances. Routing to Bin {target_tray} (Chute Angle: {target_angle}°)."
            else:
                reason = f"Verified {matched_size_name} within ISO dimensional tolerances, but no bin is assigned to it. {self._describe_reject_route(target_tray)}"
        elif is_consistent and confidence < 0.70:
            decision = "REINSPECT"
            reason = f"Dimensions match {matched_size_name}, but visual confidence ({int(confidence*100)}%) is low. Reinspection recommended."
        else:
            decision = "REJECT"
            reason = f"Dimensional Mismatch for {matched_size_name}: {'; '.join(tolerance_errors)}. {self._describe_reject_route(target_tray)}"
            # Right thread size but an unlisted length is usually a missing specification, not a bad part
            if category in [CATEGORY_BOLT, CATEGORY_SCREW] and best_spec["min_diameter"] <= stem_dia <= best_spec["max_diameter"]:
                reason += (
                    f" The diameter fits, but no {category.lower()} of this diameter with a length near {length:.0f} mm is configured"
                    " - add that size on the ISO Specifications tab if it is a valid part."
                )

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

    def _reject_route(self) -> Tuple[int, int]:
        """Returns (bin id, servo angle) of the active reject bin, or (NO_BIN, 0) when none is configured."""
        reject = db_instance.get_reject_tray()
        if reject:
            return reject["tray_id"], reject["servo_angle"]
        return self.NO_BIN, 0

    def _describe_reject_route(self, tray_id: int) -> str:
        if tray_id == self.NO_BIN:
            return "No reject bin is configured, so the part was not sorted - assign a bin to REJECT on the Custom Bins tab."
        return f"Routing to Reject Bin {tray_id}."

    def _find_target_tray(self, category: str, size_name: str, is_consistent: bool) -> Tuple[int, int, bool]:
        """Finds the active bin and servo angle for a part. The flag is False when it fell back to the reject bin."""
        if not is_consistent:
            return (*self._reject_route(), True)

        trays = db_instance.get_trays(enabled_only=True)

        # Exact match on size name within the category
        for t in trays:
            if t["assigned_category"] == category and t["assigned_size"] == size_name:
                return t["tray_id"], t["servo_angle"], True

        # Category match
        for t in trays:
            if t["assigned_category"] == category:
                return t["tray_id"], t["servo_angle"], True

        # A catch-all bin takes anything that has no dedicated bin
        for t in trays:
            if t["assigned_category"] == "ANY":
                return t["tray_id"], t["servo_angle"], True

        return (*self._reject_route(), False)

    def _create_reject_decision(self, category: str, reason: str) -> Dict[str, Any]:
        tray_id, servo_angle = self._reject_route()
        full_reason = f"{reason} {self._describe_reject_route(tray_id)}"
        return {
            "decision": "REJECT",
            "matched_size": "Non-Standard / Reject",
            "nominal_spec": None,
            "assigned_tray": tray_id,
            "servo_angle": servo_angle,
            "reason": full_reason,
            "inconsistency_detected": True,
            "tolerance_errors": [reason]
        }

verification_engine = FastenerVerificationEngine()
