"""
FILE: frontend/tab_bins_and_chute_angles.py

WHAT THIS FILE DOES
    Tab 2 'Custom Bins & Chute Angles': set how many sorting bins the machine has and, for each bin,
    which fastener it collects, its chute servo angle and its capacity.

MAIN PARTS
    - Quick setup: number of bins and automatic angle spacing
    - Bins table: one editable row per bin, with fill level and a 'test chute' button
    - Save to database, reset counts

USED BY
    frontend/main_window.py
"""

from typing import List, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QSpinBox, QComboBox, QCheckBox,
    QProgressBar, QMessageBox
)

import re

from backend.sqlite_database import db_instance, default_tray_label
from backend.esp32_communication import hardware_manager
from backend.app_logging import log_session_step

# ============================================================================
# BINS TAB
# ============================================================================
class TraysConfigurationPanel(QWidget):
    """Panel for configuring customizable sorting bins and rotating chute angles."""
    bins_configuration_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_trays()

    # ========================================================================
    # LAYOUT
    # Quick setup row, the bins table and the bottom buttons.
    # ========================================================================
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ---------------- 1. Quick Bin Setup & Angle Spacing Generator ----------------
        setup_group = QGroupBox("DYNAMIC SORTING BINS && SERVO ANGLE SETUP")
        setup_layout = QHBoxLayout(setup_group)
        setup_layout.setContentsMargins(12, 12, 12, 12)
        setup_layout.setSpacing(14)

        setup_layout.addWidget(QLabel("Active Bins Count:"))
        self.bin_count_spin = QSpinBox()
        self.bin_count_spin.setRange(2, 16)
        self.bin_count_spin.setValue(4)
        self.bin_count_spin.setSuffix(" Bins")
        self.bin_count_spin.setStyleSheet("font-weight: 700; padding: 4px;")
        setup_layout.addWidget(self.bin_count_spin)

        setup_layout.addWidget(QLabel("Angle Span:"))
        self.start_angle_spin = QSpinBox()
        self.start_angle_spin.setRange(0, 180)
        self.start_angle_spin.setValue(25)
        self.start_angle_spin.setSuffix("°")
        setup_layout.addWidget(self.start_angle_spin)

        setup_layout.addWidget(QLabel("to"))
        self.end_angle_spin = QSpinBox()
        self.end_angle_spin.setRange(0, 180)
        self.end_angle_spin.setValue(155)
        self.end_angle_spin.setSuffix("°")
        setup_layout.addWidget(self.end_angle_spin)

        self.apply_preset_btn = QPushButton("⚙ Auto-Configure Bins && Equal Spacing")
        self.apply_preset_btn.setStyleSheet("background-color: #2563EB; color: white; font-weight: 700; padding: 6px 14px;")
        self.apply_preset_btn.clicked.connect(self._on_auto_configure_clicked)
        setup_layout.addWidget(self.apply_preset_btn)

        setup_layout.addStretch()

        self.reset_counts_btn = QPushButton("Reset Counts")
        self.reset_counts_btn.setObjectName("dangerBtn")
        self.reset_counts_btn.clicked.connect(self._reset_counts)
        setup_layout.addWidget(self.reset_counts_btn)

        layout.addWidget(setup_group)

        # ---------------- 2. Custom Bins Table ----------------
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Bin #", "Bin Label", "Assigned Category", "Assigned Size Standard",
            "Chute Servo Angle", "Capacity", "Fill Status", "Test Chute"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

        # ---------------- 3. Bottom Action Row ----------------
        bottom_row = QHBoxLayout()
        hint_lbl = QLabel("Tip: You can edit Bin Label, Assigned Category, Size, and Angle directly for your hardware setup.")
        hint_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        bottom_row.addWidget(hint_lbl)
        bottom_row.addStretch()

        self.save_all_btn = QPushButton("💾 Save All Bin Configurations")
        self.save_all_btn.setStyleSheet("background-color: #059669; color: white; font-weight: 700; padding: 8px 20px;")
        self.save_all_btn.clicked.connect(self._save_table_to_db)
        bottom_row.addWidget(self.save_all_btn)

        layout.addLayout(bottom_row)

    # ========================================================================
    # BINS TABLE
    # Build one editable row per bin from the database.
    # ========================================================================
    def load_trays(self):
        """Loads only enabled active bins into the table with interactive widgets."""
        trays = db_instance.get_trays(enabled_only=True)
        if not trays:
            trays = db_instance.get_trays()[:4]

        self.bin_count_spin.blockSignals(True)
        self.bin_count_spin.setValue(len(trays))
        self.bin_count_spin.blockSignals(False)

        self.table.setRowCount(0)

        # Available categories and size choices
        category_options = ["BOLT", "NUT", "SCREW", "WASHER", "REJECT", "ANY"]
        self._sizes_by_category = {}
        for spec in db_instance.get_specifications():
            self._sizes_by_category.setdefault(spec["category"], []).append(spec["size_name"])

        for row_idx, t in enumerate(trays):
            self.table.insertRow(row_idx)

            # 0. Bin ID
            id_item = QTableWidgetItem(f"Bin {t['tray_id']}")
            id_item.setData(Qt.ItemDataRole.UserRole, t["tray_id"])
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            id_font = id_item.font()
            id_font.setBold(True)
            id_item.setFont(id_font)

            # 1. Label
            name_item = QTableWidgetItem(t["tray_name"])

            # 2. Category ComboBox
            cat_combo = QComboBox()
            cat_combo.addItems(category_options)
            curr_cat = t.get("assigned_category", "ANY")
            if curr_cat in category_options:
                cat_combo.setCurrentText(curr_cat)
            else:
                cat_combo.setCurrentText("ANY")

            # 3. Size Standard ComboBox
            size_combo = QComboBox()
            size_combo.setEditable(True)
            self._fill_size_options(size_combo, cat_combo.currentText(), t.get("assigned_size") or "Any Size")
            # Only sizes of the chosen category are offered, so a bolt size cannot be given to a screw bin
            cat_combo.currentTextChanged.connect(
                lambda cat, combo=size_combo: self._fill_size_options(combo, cat, combo.currentText())
            )

            # 4. Servo Angle SpinBox
            angle_spin = QSpinBox()
            angle_spin.setRange(0, 180)
            angle_spin.setValue(t.get("servo_angle", 45))
            angle_spin.setSuffix("°")
            angle_spin.setStyleSheet("font-weight: 700; color: #1D4ED8;")

            # 5. Capacity SpinBox
            cap_spin = QSpinBox()
            cap_spin.setRange(10, 5000)
            cap_spin.setValue(t.get("capacity", 250))

            # 6. Fill Progress Bar
            curr = t.get("current_count", 0)
            cap = max(1, t.get("capacity", 250))
            pct = min(100, int((curr / cap) * 100))

            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._set_fill_level(pbar, curr, cap)

            # 7. Test Chute Button
            test_btn = QPushButton(f"Aim Chute")
            test_btn.clicked.connect(lambda ch=False, asp=angle_spin, tid=t["tray_id"]: self._test_chute_spin(tid, asp))

            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, name_item)
            self.table.setCellWidget(row_idx, 2, cat_combo)
            self.table.setCellWidget(row_idx, 3, size_combo)
            self.table.setCellWidget(row_idx, 4, angle_spin)
            self.table.setCellWidget(row_idx, 5, cap_spin)
            self.table.setCellWidget(row_idx, 6, pbar)
            self.table.setCellWidget(row_idx, 7, test_btn)

    def _fill_size_options(self, size_combo: QComboBox, category: str, current: str):
        """Lists the size choices valid for a category, keeping the current choice when it still applies."""
        if category == "REJECT":
            options = ["Out of Spec"]
        elif category == "ANY":
            options = ["Any Size"]
        else:
            # "Any Size" makes the bin take every size of its category
            options = ["Any Size"] + sorted(self._sizes_by_category.get(category, []))

        size_combo.blockSignals(True)
        size_combo.clear()
        size_combo.addItems(options)
        size_combo.setCurrentText(current if current in options else options[0])
        size_combo.blockSignals(False)

    @staticmethod
    def _set_fill_level(pbar: QProgressBar, current: int, capacity: int):
        capacity = max(1, capacity)
        pct = min(100, int((current / capacity) * 100))
        pbar.setValue(pct)
        pbar.setFormat(f"{current} / {capacity} ({pct}%)")
        color = "#DC2626" if pct >= 90 else "#059669"
        pbar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

    def _row_tray_id(self, row: int) -> int:
        item = self.table.item(row, 0)
        tray_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return int(tray_id) if tray_id is not None else row + 1

    def refresh_fill_levels(self):
        """Updates only the fill gauges, leaving any unsaved edits in the table untouched."""
        trays = {t["tray_id"]: t for t in db_instance.get_trays()}
        for row in range(self.table.rowCount()):
            tray = trays.get(self._row_tray_id(row))
            pbar = self.table.cellWidget(row, 6)
            if tray and isinstance(pbar, QProgressBar):
                self._set_fill_level(pbar, tray.get("current_count", 0), tray.get("capacity", 250))

    # ========================================================================
    # BUTTON ACTIONS
    # Auto-space the angles, save, test a chute position, reset counts.
    # ========================================================================
    def _on_auto_configure_clicked(self):
        count = self.bin_count_spin.value()
        start_a = self.start_angle_spin.value()
        end_a = self.end_angle_spin.value()

        if end_a <= start_a:
            QMessageBox.warning(self, "Invalid Angle Span", "The end angle must be greater than the start angle.")
            return

        db_instance.set_active_bin_count(count, start_angle=start_a, end_angle=end_a)
        self.load_trays()
        self.bins_configuration_changed.emit()
        QMessageBox.information(
            self,
            "Bins Configured",
            f"Successfully configured {count} active sorting bins with angles spanning {start_a}° to {end_a}°."
        )

    def _save_table_to_db(self):
        """Saves current table edits back to SQLite database."""
        row_count = self.table.rowCount()
        for r in range(row_count):
            tray_id = self._row_tray_id(r)
            name_item = self.table.item(r, 1)
            tray_name = name_item.text().strip() if name_item else f"Bin {tray_id}"

            cat_widget = self.table.cellWidget(r, 2)
            category = cat_widget.currentText() if cat_widget else "ANY"

            size_widget = self.table.cellWidget(r, 3)
            size_name = size_widget.currentText() if size_widget else "Any Size"

            # Auto-generated labels follow the assignment; labels the operator typed are kept as they are
            if name_item and re.fullmatch(r"(Bin|Tray) \d+( \(.*\))?", tray_name):
                tray_name = default_tray_label(tray_id, category, size_name)
                name_item.setText(tray_name)

            angle_widget = self.table.cellWidget(r, 4)
            angle = angle_widget.value() if angle_widget else 45

            cap_widget = self.table.cellWidget(r, 5)
            capacity = cap_widget.value() if cap_widget else 250

            db_instance.update_tray(
                tray_id=tray_id,
                assigned_category=category,
                assigned_size=size_name,
                servo_angle=angle,
                capacity=capacity,
                enabled=1,
                tray_name=tray_name
            )

        log_session_step("CONFIG", f"Saved customizations for {row_count} sorting bins.")
        self.refresh_fill_levels()
        self.bins_configuration_changed.emit()

        if db_instance.get_reject_tray() is None:
            QMessageBox.warning(
                self,
                "No Reject Bin",
                f"All {row_count} bins were saved, but none is assigned to REJECT.\n\n"
                "Out-of-spec and unrecognized parts will not be sorted until one bin's category is set to REJECT."
            )
        else:
            QMessageBox.information(self, "Settings Saved", f"All {row_count} bin assignments and servo angles have been saved!")

    def _test_chute_spin(self, tray_id: int, spin: QSpinBox):
        angle = spin.value()
        if hardware_manager.send_command({"command": "SORT", "tray": tray_id, "angle": angle}):
            QMessageBox.information(self, "Chute Actuated", f"Chute servo moved to Bin {tray_id} ({angle}°).")
        else:
            QMessageBox.warning(
                self,
                "Chute Not Moved",
                "The command was not sent. Check that the emergency stop is reset and the hardware link is connected."
            )

    def _reset_counts(self):
        db_instance.reset_tray_counts()
        self.load_trays()
        self.bins_configuration_changed.emit()
        QMessageBox.information(self, "Counters Reset", "All bin piece counts reset to zero.")
