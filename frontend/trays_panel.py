"""
Sorting Bins & Chute Configuration Panel for AI Fastener Inspection System.
Allows complete customization of the number of sorting bins (e.g. 2 to 12 bins),
per-bin fastener assignments, servo angles (0° - 180°), capacities, and automatic angle spacing.
"""

from typing import List, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QSpinBox, QComboBox, QCheckBox,
    QProgressBar, QMessageBox
)

from backend.database import db_instance
from backend.hardware_comm import hardware_manager
from backend.logger import log_session_step

class TraysConfigurationPanel(QWidget):
    """Panel for configuring customizable sorting bins and rotating chute angles."""
    bins_configuration_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_trays()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ---------------- 1. Quick Bin Setup & Angle Spacing Generator ----------------
        setup_group = QGroupBox("DYNAMIC SORTING BINS & SERVO ANGLE SETUP")
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

        self.apply_preset_btn = QPushButton("⚙ Auto-Configure Bins & Equal Spacing")
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
        all_specs = db_instance.get_specifications()
        spec_size_options = sorted(list(set([s["size_name"] for s in all_specs] + ["Any Size", "Out of Spec", "Custom"])))

        for row_idx, t in enumerate(trays):
            self.table.insertRow(row_idx)

            # 0. Bin ID
            id_item = QTableWidgetItem(f"Bin {t['tray_id']}")
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
            size_combo.addItems(spec_size_options)
            curr_size = t.get("assigned_size", "Any Size")
            if curr_size in spec_size_options:
                size_combo.setCurrentText(curr_size)
            else:
                size_combo.setEditText(curr_size)

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
            pbar.setValue(pct)
            pbar.setFormat(f"{curr} / {cap} ({pct}%)")
            pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if pct >= 90:
                pbar.setStyleSheet("QProgressBar::chunk { background-color: #DC2626; }")
            else:
                pbar.setStyleSheet("QProgressBar::chunk { background-color: #059669; }")

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

    def _on_auto_configure_clicked(self):
        count = self.bin_count_spin.value()
        start_a = self.start_angle_spin.value()
        end_a = self.end_angle_spin.value()

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
            tray_id = r + 1
            name_item = self.table.item(r, 1)
            tray_name = name_item.text().strip() if name_item else f"Bin {tray_id}"

            cat_widget = self.table.cellWidget(r, 2)
            category = cat_widget.currentText() if cat_widget else "ANY"

            size_widget = self.table.cellWidget(r, 3)
            size_name = size_widget.currentText() if size_widget else "Any Size"

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
                enabled=1
            )

        log_session_step("CONFIG", f"Saved customizations for {row_count} sorting bins.")
        self.bins_configuration_changed.emit()
        QMessageBox.information(self, "Settings Saved", f"All {row_count} bin assignments and servo angles have been saved!")

    def _test_chute_spin(self, tray_id: int, spin: QSpinBox):
        angle = spin.value()
        hardware_manager.send_command({"command": "SORT", "tray": tray_id, "angle": angle})
        QMessageBox.information(self, "Chute Actuated", f"Chute servo moved to Bin {tray_id} ({angle}°).")

    def _reset_counts(self):
        db_instance.reset_tray_counts()
        self.load_trays()
        self.bins_configuration_changed.emit()
        QMessageBox.information(self, "Counters Reset", "All bin piece counts reset to zero.")
