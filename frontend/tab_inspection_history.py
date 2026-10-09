"""
FILE: frontend/tab_inspection_history.py

WHAT THIS FILE DOES
    Tab 6 'Quality Audit History': a table of every inspected part with its measurements and decision.

MAIN PARTS
    - Loads saved records from the database when the app starts
    - Adds a row after each new inspection
    - Clear history, export to CSV

USED BY
    frontend/main_window.py
"""

import csv
from typing import Dict, Any, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QFileDialog, QMessageBox, QComboBox
)

from backend.app_config import CATEGORY_COLORS, CATEGORY_UNKNOWN
from backend.sqlite_database import db_instance
from backend.app_logging import app_logger

# ============================================================================
# HISTORY TAB
# ============================================================================
class HistoryPanel(QWidget):
    """Panel displaying session inspection history table with dimensional records."""
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_from_database()

    # ========================================================================
    # LAYOUT
    # ========================================================================
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Action Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QLabel("Inspection Audit Log:"))
        btn_layout.addStretch()

        self.export_btn = QPushButton("Export CSV Report")
        self.export_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Time", "Category", "Matched Size", "Length (mm)", "Stem Dia (mm)", "Inner / Outer Dia", "Decision", "Assigned Bin"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table)

    # ========================================================================
    # TABLE CONTENT
    # Load saved records and add a row for each new inspection.
    # ========================================================================
    def load_from_database(self):
        records = db_instance.get_history(limit=200)
        self.table.setRowCount(0)
        for r in reversed(records):
            self.add_inspection_entry(r)

    def add_inspection_entry(self, entry: Dict[str, Any]):
        """Appends a new inspection entry to the top of the table."""
        self.table.insertRow(0)

        time_str = entry.get("timestamp", "--:--:--")
        category = str(entry.get("category", CATEGORY_UNKNOWN)).upper()
        size_name = str(entry.get("detected_size", "--"))
        decision = str(entry.get("decision", "REJECT"))
        tray_id = entry.get("assigned_tray", 10)

        len_val = entry.get("length_mm")
        len_str = f"{len_val:.2f}" if len_val else "--"

        stem_val = entry.get("stem_dia_mm")
        stem_str = f"{stem_val:.2f}" if stem_val else "--"

        inner_val = entry.get("inner_dia_mm")
        outer_val = entry.get("outer_dia_mm")
        dia_combo_str = f"{inner_val:.1f} / {outer_val:.1f}" if (inner_val and outer_val) else "--"

        # Table Items
        item_time = QTableWidgetItem(time_str)
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_cat = QTableWidgetItem(category)
        item_cat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        cat_color = CATEGORY_COLORS.get(category, "#1E293B")
        font = item_cat.font()
        font.setBold(True)
        item_cat.setFont(font)

        item_size = QTableWidgetItem(size_name)
        item_len = QTableWidgetItem(len_str)
        item_len.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_stem = QTableWidgetItem(stem_str)
        item_stem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_dia_combo = QTableWidgetItem(dia_combo_str)
        item_dia_combo.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_dec = QTableWidgetItem(decision)
        item_dec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        dec_font = item_dec.font()
        dec_font.setBold(True)
        item_dec.setFont(dec_font)

        item_tray = QTableWidgetItem(f"Bin {tray_id}" if tray_id else "Not sorted")
        item_tray.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(0, 0, item_time)
        self.table.setItem(0, 1, item_cat)
        self.table.setItem(0, 2, item_size)
        self.table.setItem(0, 3, item_len)
        self.table.setItem(0, 4, item_stem)
        self.table.setItem(0, 5, item_dia_combo)
        self.table.setItem(0, 6, item_dec)
        self.table.setItem(0, 7, item_tray)

    # ========================================================================
    # BUTTON ACTIONS
    # Clear the history or export it to a CSV file.
    # ========================================================================
    def _on_clear_clicked(self):
        if self.table.rowCount() == 0:
            return
        confirm = QMessageBox.question(
            self, "Clear History",
            "Permanently delete all inspection records from the audit log?\n\nExport a CSV report first if you need to keep them.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.table.setRowCount(0)
        self.clear_history_requested.emit()

    def export_csv(self):
        records = db_instance.get_history(limit=500)
        if not records:
            QMessageBox.information(self, "Export", "No records to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Inspection Report", "fastener_inspection_audit.csv", "CSV Files (*.csv)"
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID", "Timestamp", "Date", "Category", "Detected Size", "Confidence",
                    "Length (mm)", "Stem Dia (mm)", "Head Width (mm)", "Inner Dia (mm)",
                    "Outer Dia (mm)", "Decision", "Assigned Tray", "Reason"
                ])
                for r in records:
                    writer.writerow([
                        r.get("id"), r.get("timestamp"), r.get("date"), r.get("category"),
                        r.get("detected_size"), r.get("confidence"), r.get("length_mm"),
                        r.get("stem_dia_mm"), r.get("head_width_mm"), r.get("inner_dia_mm"),
                        r.get("outer_dia_mm"), r.get("decision"), r.get("assigned_tray"), r.get("reason")
                    ])
            QMessageBox.information(self, "Export Complete", f"Report saved to:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed: {e}")
