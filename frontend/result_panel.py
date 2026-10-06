"""
Redesigned Industrial Workstation Result Panel for AI Fastener Inspection System.
Displays Crisp Fastener Category, Matched ISO Standard Size, Calibrated Metric Parameter Grid,
Real-Time Chute Angle Dial/Gauge, Tolerance Verification Status, and Production Yield.
"""

from typing import Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QPushButton, QGroupBox, QProgressBar
)

from backend.config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER,
    CATEGORY_UNKNOWN, CATEGORY_COLORS
)

class ResultPanel(QWidget):
    """Clean industrial engineering result workstation panel."""
    reset_counters_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---------------- 1. Inspection Outcome Header Card ----------------
        self.header_card = QFrame()
        self.header_card.setObjectName("resultHeaderCard")
        self.header_card.setStyleSheet(
            "#resultHeaderCard { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; }"
            "#resultHeaderCard QLabel { background: transparent; border: none; }"
        )
        hdr_layout = QVBoxLayout(self.header_card)
        hdr_layout.setContentsMargins(14, 12, 14, 12)
        hdr_layout.setSpacing(6)

        # Top row: Category + Decision Badge
        top_row = QHBoxLayout()
        self.category_label = QLabel("STANDBY")
        self.category_label.setStyleSheet("font-size: 20px; font-weight: 800; color: #1E293B; letter-spacing: 0.5px;")

        self.decision_badge = QLabel("READY FOR INSPECTION")
        self.decision_badge.setStyleSheet(
            "background-color: #64748B; color: #FFFFFF; font-size: 11px; font-weight: 800; "
            "padding: 4px 10px; border-radius: 4px;"
        )
        top_row.addWidget(self.category_label)
        top_row.addStretch()
        top_row.addWidget(self.decision_badge)
        hdr_layout.addLayout(top_row)

        # Subtitle: Standard Size & Optical Confidence
        sub_row = QHBoxLayout()
        self.size_label = QLabel("Standard: Awaiting Part")
        self.size_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #1D4ED8;")

        self.conf_label = QLabel("Confidence: -- %")
        self.conf_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B;")

        sub_row.addWidget(self.size_label)
        sub_row.addStretch()
        sub_row.addWidget(self.conf_label)
        hdr_layout.addLayout(sub_row)

        layout.addWidget(self.header_card)

        # ---------------- 2. Calibrated Metric Dimension Parameter Matrix ----------------
        dim_group = QGroupBox("CALIBRATED PHYSICAL MEASUREMENTS (OPENCV)")
        dim_layout = QGridLayout(dim_group)
        dim_layout.setContentsMargins(8, 10, 8, 8)
        dim_layout.setHorizontalSpacing(8)
        dim_layout.setVerticalSpacing(8)

        # 4 Metric Readout Tiles
        self.tile_len, self.val_length = self._create_metric_tile("Length (L)", "-- mm")
        self.tile_stem, self.val_stem_dia = self._create_metric_tile("Stem / Shank Dia (Ø)", "-- mm")
        self.tile_head, self.val_head_width = self._create_metric_tile("Head / AF Width", "-- mm")
        self.tile_inner, self.val_inner_dia = self._create_metric_tile("Inner Hole Dia (d1)", "-- mm")

        dim_layout.addWidget(self.tile_len, 0, 0)
        dim_layout.addWidget(self.tile_stem, 0, 1)
        dim_layout.addWidget(self.tile_head, 1, 0)
        dim_layout.addWidget(self.tile_inner, 1, 1)

        layout.addWidget(dim_group)

        # ---------------- 3. Active Sorting Chute Destination & Servo Dial ----------------
        chute_group = QGroupBox("ACTIVE SORTING CHUTE DISPATCH")
        chute_layout = QVBoxLayout(chute_group)
        chute_layout.setContentsMargins(10, 10, 10, 8)
        chute_layout.setSpacing(6)

        c_row = QHBoxLayout()
        self.tray_dest_lbl = QLabel("Destination: Bin 1 (Awaiting Trigger)")
        self.tray_dest_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")

        self.angle_dest_lbl = QLabel("Chute Angle: 0°")
        self.angle_dest_lbl.setStyleSheet("font-size: 12px; font-weight: 800; color: #1D4ED8;")

        c_row.addWidget(self.tray_dest_lbl)
        c_row.addStretch()
        c_row.addWidget(self.angle_dest_lbl)
        chute_layout.addLayout(c_row)

        # Visual Servo Position Gauge (0° to 180°)
        self.servo_gauge = QProgressBar()
        self.servo_gauge.setRange(0, 180)
        self.servo_gauge.setValue(0)
        self.servo_gauge.setFormat("Chute Servo Angle: %v° / 180°")
        self.servo_gauge.setStyleSheet("QProgressBar::chunk { background-color: #1D4ED8; border-radius: 2px; }")
        chute_layout.addWidget(self.servo_gauge)

        layout.addWidget(chute_group)

        # ---------------- 4. Engineering Verification Notes ----------------
        self.reason_card = QLabel("Place fastener on inspection pad and press 'INSPECT, MEASURE & SORT'.")
        self.reason_card.setWordWrap(True)
        self.reason_card.setStyleSheet(
            "background-color: #FFFFFF; border: 1px dashed #CBD5E1; border-radius: 4px; "
            "padding: 8px; font-size: 11px; color: #334155; line-height: 1.4;"
        )
        layout.addWidget(self.reason_card)

        # ---------------- 5. Production Yield & Batch Stats ----------------
        stats_group = QGroupBox("BATCH QUALITY && YIELD STATISTICS")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(8, 10, 8, 8)
        stats_layout.setSpacing(6)

        s_grid = QGridLayout()
        s_grid.setHorizontalSpacing(8)
        s_grid.setVerticalSpacing(4)

        self.counter_labels = {}
        items = [
            ("ACCEPTED", "ACCEPTED", "#15803D"),
            ("REJECTED", "REJECTED", "#DC2626"),
            ("BOLTS", CATEGORY_BOLT, "#059669"),
            ("NUTS", CATEGORY_NUT, "#2563EB"),
            ("SCREWS", CATEGORY_SCREW, "#D97706"),
            ("WASHERS", CATEGORY_WASHER, "#7C3AED"),
        ]

        for idx, (display_name, key, color) in enumerate(items):
            r = idx // 2
            c = (idx % 2) * 2

            n_lbl = QLabel(display_name)
            n_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {color};")

            v_lbl = QLabel("0")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_lbl.setStyleSheet(
                "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 3px; "
                "font-size: 12px; font-weight: 700; color: #0F172A; padding: 2px 6px; min-width: 26px;"
            )
            self.counter_labels[key] = v_lbl

            s_grid.addWidget(n_lbl, r, c)
            s_grid.addWidget(v_lbl, r, c + 1)

        stats_layout.addLayout(s_grid)

        # Reset button
        rst_btn = QPushButton("Reset Batch Stats")
        rst_btn.setObjectName("dangerBtn")
        rst_btn.clicked.connect(self.reset_counters_requested.emit)
        stats_layout.addWidget(rst_btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(stats_group)

    def _create_metric_tile(self, title: str, default_val: str):
        tile = QFrame()
        tile.setObjectName("metricTile")
        tile.setStyleSheet(
            "#metricTile { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; }"
            "#metricTile QLabel { background: transparent; border: none; }"
        )
        t_layout = QVBoxLayout(tile)
        t_layout.setContentsMargins(10, 8, 10, 8)
        t_layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #64748B;")

        val_lbl = QLabel(default_val)
        val_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A;")

        t_layout.addWidget(title_lbl)
        t_layout.addWidget(val_lbl)
        return tile, val_lbl

    def display_result(self, result: Dict[str, Any]):
        category = result.get("category", CATEGORY_UNKNOWN).upper()
        detected_size = result.get("detected_size", "Unknown Size")
        decision = result.get("decision", "REJECT")
        confidence = float(result.get("confidence", 0.0))
        tray_id = result.get("assigned_tray", 1)
        angle = result.get("servo_angle", 45)
        reason = result.get("reason", "")

        cat_color = CATEGORY_COLORS.get(category, "#0F172A")
        self.category_label.setText(category)
        self.category_label.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {cat_color};")

        # Decision Pill Styling
        if decision == "ACCEPT":
            self.decision_badge.setText("ACCEPTED (IN SPEC)")
            self.decision_badge.setStyleSheet("background-color: #15803D; color: #FFFFFF; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 4px;")
        elif decision == "REINSPECT":
            self.decision_badge.setText("REINSPECT (AMBIGUOUS)")
            self.decision_badge.setStyleSheet("background-color: #D97706; color: #FFFFFF; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 4px;")
        else:
            # An unrecognized object was never measured against a spec, so it is not "out of spec"
            self.decision_badge.setText("NOT RECOGNIZED" if category == CATEGORY_UNKNOWN else "REJECTED (OUT OF SPEC)")
            self.decision_badge.setStyleSheet("background-color: #DC2626; color: #FFFFFF; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 4px;")

        self.size_label.setText(f"Standard: {detected_size}")
        self.conf_label.setText(f"Confidence: {int(confidence * 100)}%")

        # Dimension Tiles
        len_val = result.get("length_mm", 0.0)
        stem_val = result.get("stem_dia_mm", 0.0)
        head_val = result.get("head_width_mm", 0.0)
        inner_val = result.get("inner_dia_mm", 0.0)

        self.val_length.setText(f"{len_val:.2f} mm" if len_val > 0 else "-- mm")
        self.val_stem_dia.setText(f"{stem_val:.2f} mm" if stem_val > 0 else "-- mm")
        self.val_head_width.setText(f"{head_val:.2f} mm" if head_val > 0 else "-- mm")
        self.val_inner_dia.setText(f"{inner_val:.2f} mm" if inner_val > 0 else "-- mm")

        # Sorting Destination & Gauge
        if not tray_id:
            self.tray_dest_lbl.setText("Destination: Not sorted (no reject bin)")
        elif decision == "REINSPECT":
            self.tray_dest_lbl.setText(f"Destination: Bin {tray_id} (held for reinspection)")
        else:
            self.tray_dest_lbl.setText(f"Destination: Bin {tray_id}")
        self.angle_dest_lbl.setText(f"Chute Angle: {angle}°")
        self.servo_gauge.setValue(angle)

        self.reason_card.setText(reason)

    def update_counters(self, counters: Dict[str, int]):
        for cat, val in counters.items():
            if cat in self.counter_labels:
                self.counter_labels[cat].setText(str(val))

    def set_analyzing_state(self):
        self.category_label.setText("INSPECTING...")
        self.category_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #1D4ED8;")
        self.decision_badge.setText("PROCESSING...")
        self.decision_badge.setStyleSheet("background-color: #1D4ED8; color: #FFFFFF; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 4px;")
        self.size_label.setText("Standard: Measuring geometry...")
        self.reason_card.setText("Isolating contour, computing calibrated millimeter dimensions, and cross-checking ISO tolerance rules...")
