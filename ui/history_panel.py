"""
Inspection History Panel for AI Fastener Inspection System.
Displays recent inspection events in a clean data table with export and clear options.
"""

import csv
from typing import Dict, Any, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QFileDialog, QMessageBox
)

from config import CATEGORY_COLORS, CATEGORY_UNKNOWN
from logger import app_logger

class HistoryPanel(QWidget):
    """Panel displaying session inspection history table."""
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history_data: List[Dict[str, Any]] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.group_box = QGroupBox("INSPECTION HISTORY")
        group_layout = QVBoxLayout(self.group_box)
        group_layout.setContentsMargins(10, 14, 10, 10)
        group_layout.setSpacing(8)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Time", "Category", "Confidence", "Reason"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(150)
        
        group_layout.addWidget(self.table)

        # Action Buttons below table
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(self.export_btn)

        btn_layout.addStretch()

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        btn_layout.addWidget(self.clear_btn)

        group_layout.addLayout(btn_layout)
        layout.addWidget(self.group_box)

    def add_inspection_entry(self, entry: Dict[str, Any]):
        """Appends a new inspection entry to the top of the table."""
        self._history_data.insert(0, entry)
        self.table.insertRow(0)

        time_str = entry.get("timestamp", "--:--:--")
        category = entry.get("category", CATEGORY_UNKNOWN).upper()
        confidence = float(entry.get("confidence", 0.0))
        conf_pct = f"{int(confidence * 100 if confidence <= 1.0 else confidence)}%"
        reason = entry.get("reason", "")

        # Items
        item_time = QTableWidgetItem(time_str)
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_cat = QTableWidgetItem(category)
        item_cat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Color category text
        cat_color = CATEGORY_COLORS.get(category, "#1E293B")
        # Bold font for category
        font = item_cat.font()
        font.setBold(True)
        item_cat.setFont(font)

        item_conf = QTableWidgetItem(conf_pct)
        item_conf.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_reason = QTableWidgetItem(reason)
        item_reason.setToolTip(reason)

        self.table.setItem(0, 0, item_time)
        self.table.setItem(0, 1, item_cat)
        self.table.setItem(0, 2, item_conf)
        self.table.setItem(0, 3, item_reason)

    def clear_table(self):
        """Empties table contents."""
        self._history_data.clear()
        self.table.setRowCount(0)

    def _on_clear_clicked(self):
        self.clear_table()
        self.clear_history_requested.emit()

    def export_csv(self):
        """Exports inspection records to a user-selected CSV file."""
        if not self._history_data:
            QMessageBox.information(self, "Export History", "No inspection records to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Inspection History",
            "fastener_inspection_history.csv",
            "CSV Files (*.csv)"
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Time", "Category", "Confidence", "Reason", "Raw Response"])
                for item in self._history_data:
                    writer.writerow([
                        item.get("date", ""),
                        item.get("timestamp", ""),
                        item.get("category", ""),
                        item.get("confidence", ""),
                        item.get("reason", ""),
                        item.get("raw_response", "")
                    ])
            QMessageBox.information(self, "Export Success", f"History successfully exported to:\n{filepath}")
            app_logger.info(f"Exported history to {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {str(e)}")
            app_logger.error(f"Failed exporting CSV: {e}")
