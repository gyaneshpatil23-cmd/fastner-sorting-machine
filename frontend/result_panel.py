"""
Result and Counters Panel for AI Fastener Inspection System.
Displays primary classification outcome, confidence level badge, engineering reasoning,
and live category counters with reset capabilities.
"""

from typing import Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QPushButton, QGroupBox
)

from config import (
    CATEGORY_NUT, CATEGORY_BOLT, CATEGORY_SCREW, CATEGORY_WASHER, CATEGORY_UNKNOWN,
    CATEGORY_COLORS, get_confidence_level, get_confidence_color
)

class ResultPanel(QWidget):
    """Panel displaying AI classification result card and category statistics."""
    reset_counters_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ---------------- 1. Primary AI Result Card ----------------
        self.result_group = QGroupBox("INSPECTION CLASSIFICATION RESULT")
        result_layout = QVBoxLayout(self.result_group)
        result_layout.setContentsMargins(14, 16, 14, 14)
        result_layout.setSpacing(10)

        # Top tag / status
        header_layout = QHBoxLayout()
        tag_lbl = QLabel("DETECTED CATEGORY")
        tag_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 1px;")
        
        self.confidence_badge = QLabel("READY FOR INSPECTION")
        self.confidence_badge.setStyleSheet(
            "background-color: #E2E8F0; color: #475569; font-size: 11px; font-weight: 700; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        header_layout.addWidget(tag_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.confidence_badge)
        result_layout.addLayout(header_layout)

        # Big Category Name
        self.category_label = QLabel("NO OBJECT")
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.category_label.setStyleSheet("font-size: 26px; font-weight: 800; color: #1E293B;")
        result_layout.addWidget(self.category_label)

        # Confidence Bar / Number
        conf_layout = QHBoxLayout()
        conf_title = QLabel("AI Model Confidence:")
        conf_title.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        
        self.confidence_value = QLabel("-- %")
        self.confidence_value.setStyleSheet("font-size: 15px; font-weight: 800; color: #2563EB;")
        
        conf_layout.addWidget(conf_title)
        conf_layout.addWidget(self.confidence_value)
        conf_layout.addStretch()
        result_layout.addLayout(conf_layout)

        # Explanation Box
        reason_title = QLabel("Engineering Explanation:")
        reason_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; margin-top: 4px;")
        result_layout.addWidget(reason_title)

        self.reason_label = QLabel("Load an image or capture a camera frame and click 'ANALYZE FASTENER' to start.")
        self.reason_label.setWordWrap(True)
        self.reason_label.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; "
            "padding: 10px; font-size: 12px; color: #334155; line-height: 1.4;"
        )
        self.reason_label.setMinimumHeight(60)
        result_layout.addWidget(self.reason_label)

        layout.addWidget(self.result_group)

        # ---------------- 2. Category Counters Card ----------------
        self.counters_group = QGroupBox("FASTENER BATCH COUNTERS")
        counters_layout = QVBoxLayout(self.counters_group)
        counters_layout.setContentsMargins(12, 14, 12, 12)
        counters_layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.counter_labels = {}
        categories = [
            ("NUTS", CATEGORY_NUT, "#2563EB"),
            ("BOLTS", CATEGORY_BOLT, "#059669"),
            ("SCREWS", CATEGORY_SCREW, "#D97706"),
            ("WASHERS", CATEGORY_WASHER, "#7C3AED"),
            ("UNKNOWN", CATEGORY_UNKNOWN, "#64748B")
        ]

        for idx, (display_name, key, color) in enumerate(categories):
            row = idx // 2
            col = (idx % 2) * 2

            # Name label
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {color};")
            
            # Value box
            val_lbl = QLabel("0")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(
                "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 4px; "
                "font-size: 14px; font-weight: 700; color: #0F172A; padding: 4px 10px; min-width: 32px;"
            )
            self.counter_labels[key] = val_lbl

            grid.addWidget(name_lbl, row, col)
            grid.addWidget(val_lbl, row, col + 1)

        counters_layout.addLayout(grid)

        # Reset button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.reset_btn = QPushButton("Reset Counters")
        self.reset_btn.setObjectName("dangerBtn")
        self.reset_btn.clicked.connect(self.reset_counters_requested.emit)
        btn_layout.addWidget(self.reset_btn)
        counters_layout.addLayout(btn_layout)

        layout.addWidget(self.counters_group)

    def display_result(self, result: Dict[str, Any]):
        """Updates UI elements with classification outcome."""
        category = result.get("category", CATEGORY_UNKNOWN).upper()
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "")

        conf_pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
        conf_level = get_confidence_level(confidence if confidence <= 1.0 else confidence / 100.0)
        badge_color = get_confidence_color(confidence if confidence <= 1.0 else confidence / 100.0)
        cat_color = CATEGORY_COLORS.get(category, "#1E293B")

        # Update category label
        self.category_label.setText(category)
        self.category_label.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {cat_color};")

        # Update confidence badge
        self.confidence_badge.setText(conf_level)
        self.confidence_badge.setStyleSheet(
            f"background-color: {badge_color}; color: #FFFFFF; font-size: 11px; font-weight: 700; "
            f"padding: 3px 8px; border-radius: 4px;"
        )

        # Update confidence value
        self.confidence_value.setText(f"{conf_pct}%")
        self.confidence_value.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {badge_color};")

        # Update reason
        self.reason_label.setText(reason)

    def update_counters(self, counters: Dict[str, int]):
        """Updates category counter badge labels."""
        for cat, val in counters.items():
            if cat in self.counter_labels:
                self.counter_labels[cat].setText(str(val))

    def set_analyzing_state(self):
        """Displays transient 'Analyzing...' UI state."""
        self.category_label.setText("ANALYZING...")
        self.category_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #2563EB;")
        self.confidence_badge.setText("PROCESSING")
        self.confidence_badge.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-size: 11px; font-weight: 700; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        self.confidence_value.setText("-- %")
        self.reason_label.setText("Querying Gemini Vision model for fastener geometry analysis...")

    def set_live_scanning_state(self):
        """Displays real-time 'Live Scanning...' UI state."""
        self.category_label.setText("SCANNING...")
        self.category_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #059669;")
        self.confidence_badge.setText("LIVE AI")
        self.confidence_badge.setStyleSheet(
            "background-color: #059669; color: #FFFFFF; font-size: 11px; font-weight: 700; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        self.confidence_value.setText("-- %")
        self.reason_label.setText("⚡ Live Mode Active: Present any bolt, screw, nut, or washer to the camera.")
