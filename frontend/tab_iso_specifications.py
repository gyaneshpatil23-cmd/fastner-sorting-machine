"""
FILE: frontend/tab_iso_specifications.py

WHAT THIS FILE DOES
    Tab 4 'ISO Specifications': view, add and delete the standard fastener sizes and their tolerance
    limits. These are the limits a measured part is checked against.

MAIN PARTS
    - AddSpecificationDialog: the form for adding a new size
    - SpecificationPanel: one table per category (Bolts, Nuts, Washers, Screws...)

USED BY
    frontend/main_window.py
"""

from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QTabWidget, QDialog,
    QLineEdit, QDoubleSpinBox, QComboBox, QMessageBox
)

from backend.sqlite_database import db_instance
from backend.app_logging import log_session_step


# ============================================================================
# ADD-SIZE DIALOG
# The form for adding a new fastener size.
# ============================================================================
class AddSpecificationDialog(QDialog):
    """Modal dialog to add new standard or custom fastener size specifications."""

    def __init__(self, default_category: str = "BOLT", parent=None):
        super().__init__(parent)
        self.default_category = default_category
        self.setWindowTitle("Add New Fastener Size Specification")
        self.setMinimumWidth(620)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Category & Size Name
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["BOLT", "NUT", "WASHER", "SCREW", "CUSTOM"])
        self.cat_combo.setCurrentText(self.default_category)
        self.cat_combo.currentTextChanged.connect(self._on_category_changed)
        row1.addWidget(self.cat_combo)

        row1.addWidget(QLabel("Size Name:"))
        self.size_input = QLineEdit()
        self.size_input.setPlaceholderText("e.g. M8 x 45 or M6 Flange Nut")
        row1.addWidget(self.size_input)
        layout.addLayout(row1)

        # 2. Diameter Limits
        d_group = QGroupBox("DIAMETER TOLERANCES (MM)")
        d_layout = QVBoxLayout(d_group)

        d_row1 = QHBoxLayout()
        d_row1.addWidget(QLabel("Nominal Dia:"))
        self.nom_dia_spin = QDoubleSpinBox()
        self.nom_dia_spin.setRange(0.5, 100.0)
        self.nom_dia_spin.setValue(8.0)
        self.nom_dia_spin.setSuffix(" mm")
        self.nom_dia_spin.valueChanged.connect(self._auto_fill_tolerances)
        d_row1.addWidget(self.nom_dia_spin)

        d_row1.addWidget(QLabel("Min Dia:"))
        self.min_dia_spin = QDoubleSpinBox()
        self.min_dia_spin.setRange(0.1, 100.0)
        self.min_dia_spin.setValue(7.78)
        self.min_dia_spin.setSuffix(" mm")
        d_row1.addWidget(self.min_dia_spin)

        d_row1.addWidget(QLabel("Max Dia:"))
        self.max_dia_spin = QDoubleSpinBox()
        self.max_dia_spin.setRange(0.1, 100.0)
        self.max_dia_spin.setValue(8.22)
        self.max_dia_spin.setSuffix(" mm")
        d_row1.addWidget(self.max_dia_spin)
        d_layout.addLayout(d_row1)
        layout.addWidget(d_group)

        # 3. Length Limits (For Bolts & Screws)
        self.len_group = QGroupBox("LENGTH TOLERANCES (MM)")
        l_layout = QHBoxLayout(self.len_group)

        l_layout.addWidget(QLabel("Nominal Length:"))
        self.nom_len_spin = QDoubleSpinBox()
        self.nom_len_spin.setRange(0.0, 500.0)
        self.nom_len_spin.setValue(40.0)
        self.nom_len_spin.setSuffix(" mm")
        l_layout.addWidget(self.nom_len_spin)

        l_layout.addWidget(QLabel("Min:"))
        self.min_len_spin = QDoubleSpinBox()
        self.min_len_spin.setRange(0.0, 500.0)
        self.min_len_spin.setValue(39.0)
        self.min_len_spin.setSuffix(" mm")
        l_layout.addWidget(self.min_len_spin)

        l_layout.addWidget(QLabel("Max:"))
        self.max_len_spin = QDoubleSpinBox()
        self.max_len_spin.setRange(0.0, 500.0)
        self.max_len_spin.setValue(41.0)
        self.max_len_spin.setSuffix(" mm")
        l_layout.addWidget(self.max_len_spin)
        layout.addWidget(self.len_group)

        # 4. Standard Grade
        g_row = QHBoxLayout()
        g_row.addWidget(QLabel("Tolerance Standard:"))
        self.grade_combo = QComboBox()
        self.grade_combo.addItems(["ISO 965 / DIN 933", "ISO 4032 (Nut)", "DIN 125 (Washer)", "ISO 7049 (Screw)", "Custom Standard"])
        g_row.addWidget(self.grade_combo)
        layout.addLayout(g_row)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save Specification")
        save_btn.setStyleSheet("background-color: #2563EB; color: white; font-weight: 700; padding: 6px 16px;")
        save_btn.clicked.connect(self._on_save_clicked)
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)

        self._on_category_changed(self.default_category)

    def _auto_fill_tolerances(self, val):
        self.min_dia_spin.setValue(round(val - 0.22, 2))
        self.max_dia_spin.setValue(round(val + 0.22, 2))

    def _on_category_changed(self, cat):
        is_linear = cat in ["BOLT", "SCREW", "CUSTOM"]
        self.len_group.setVisible(is_linear)

    def _on_save_clicked(self):
        cat = self.cat_combo.currentText().strip()
        name = self.size_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Error", "Please enter a size name (e.g. M8 x 40).")
            return

        nom_d = self.nom_dia_spin.value()
        min_d = self.min_dia_spin.value()
        max_d = self.max_dia_spin.value()

        nom_l = self.nom_len_spin.value() if cat in ["BOLT", "SCREW", "CUSTOM"] else None
        min_l = self.min_len_spin.value() if cat in ["BOLT", "SCREW", "CUSTOM"] else None
        max_l = self.max_len_spin.value() if cat in ["BOLT", "SCREW", "CUSTOM"] else None

        # A tolerance band that does not contain its nominal value would reject every part
        if not (min_d <= nom_d <= max_d):
            QMessageBox.warning(self, "Input Error", "Diameter limits must satisfy Min ≤ Nominal ≤ Max.")
            return
        if nom_l is not None and not (min_l <= nom_l <= max_l):
            QMessageBox.warning(self, "Input Error", "Length limits must satisfy Min ≤ Nominal ≤ Max.")
            return
        if any(s["size_name"].lower() == name.lower() for s in db_instance.get_specifications(cat)):
            QMessageBox.warning(self, "Input Error", f"A {cat} size named '{name}' already exists.")
            return

        inner_d = nom_d if cat in ["NUT", "WASHER"] else None
        min_in = min_d if cat in ["NUT", "WASHER"] else None
        max_in = max_d if cat in ["NUT", "WASHER"] else None

        db_instance.add_specification(
            category=cat,
            size_name=name,
            nominal_diameter=nom_d,
            min_diameter=min_d,
            max_diameter=max_d,
            nominal_length=nom_l,
            min_length=min_l,
            max_length=max_l,
            inner_diameter=inner_d,
            min_inner_dia=min_in,
            max_inner_dia=max_in,
            tolerance_grade=self.grade_combo.currentText()
        )
        self.accept()


# ============================================================================
# SPECIFICATIONS TAB
# One table of sizes per fastener category.
# ============================================================================
class SpecificationPanel(QWidget):
    """Hierarchical Tabbed Fastener Specifications & Tolerance Database Panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tables = {}
        self.init_ui()
        self.load_all_categories()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Control Bar
        top_bar = QHBoxLayout()
        title_lbl = QLabel("ISO Fastener Dimensional Standards & Tolerance Limits")
        title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #1E293B;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        self.add_btn = QPushButton("➕ Add New Size / Category")
        self.add_btn.setStyleSheet("background-color: #2563EB; color: white; font-weight: 700; padding: 6px 14px;")
        self.add_btn.clicked.connect(self._open_add_dialog)
        top_bar.addWidget(self.add_btn)

        self.del_btn = QPushButton("🗑 Delete Selected")
        self.del_btn.setObjectName("dangerBtn")
        self.del_btn.clicked.connect(self._delete_selected_size)
        top_bar.addWidget(self.del_btn)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.load_all_categories)
        top_bar.addWidget(self.refresh_btn)

        layout.addLayout(top_bar)

        # Hierarchical Sub-Tabs for Each Category
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setStyleSheet("""
            QTabBar::tab {
                font-weight: 700; font-size: 11px; padding: 6px 14px;
                background: #F1F5F9; color: #475569; border: 1px solid #CBD5E1;
            }
            QTabBar::tab:selected {
                background: #FFFFFF; color: #1D4ED8; border-bottom: 2px solid #1D4ED8;
            }
        """)

        categories = [
            ("BOLT", "🔩 Bolts && Hex Cap Screws"),
            ("NUT", "🥜 Nuts (Hex / Flange / Square)"),
            ("WASHER", "⭕ Flat && Spring Washers"),
            ("SCREW", "🪛 Screws && Machine Fasteners"),
            ("ALL", "📋 Master View (All Standards)")
        ]

        for cat_key, tab_title in categories:
            table = self._create_spec_table()
            self.tables[cat_key] = table
            self.sub_tabs.addTab(table, tab_title)

        layout.addWidget(self.sub_tabs)

    def _create_spec_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "ID", "Category", "Size Standard", "Nominal Dia (mm)", "Diameter Tolerance (Min - Max)",
            "Length (Nominal / Range)", "Inner / Outer Tolerances", "Tolerance Standard"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Read-only view: edits typed into cells were never saved to the database
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    # ========================================================================
    # TABLE CONTENT AND BUTTON ACTIONS
    # ========================================================================
    def load_all_categories(self):
        for cat_key, table in self.tables.items():
            specs = db_instance.get_specifications(category=None if cat_key == "ALL" else cat_key)
            table.setRowCount(0)

            for r_idx, s in enumerate(specs):
                table.insertRow(r_idx)

                id_item = QTableWidgetItem(str(s["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                cat_item = QTableWidgetItem(s["category"])
                cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                size_item = QTableWidgetItem(s["size_name"])
                s_font = size_item.font()
                s_font.setBold(True)
                size_item.setFont(s_font)

                nom_d = QTableWidgetItem(f"{s['nominal_diameter']:.2f} mm")
                nom_d.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                d_range = QTableWidgetItem(f"{s['min_diameter']:.2f} - {s['max_diameter']:.2f} mm")
                d_range.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                len_str = f"{s['nominal_length']:.1f} mm [{s['min_length']:.1f} - {s['max_length']:.1f}]" if s.get('nominal_length') else "--"
                len_item = QTableWidgetItem(len_str)
                len_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                io_str = f"ID: {s['min_inner_dia']:.1f}-{s['max_inner_dia']:.1f} mm" if s.get('min_inner_dia') else "--"
                io_item = QTableWidgetItem(io_str)
                io_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                std_item = QTableWidgetItem(s.get("tolerance_grade", "ISO 965"))
                std_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                table.setItem(r_idx, 0, id_item)
                table.setItem(r_idx, 1, cat_item)
                table.setItem(r_idx, 2, size_item)
                table.setItem(r_idx, 3, nom_d)
                table.setItem(r_idx, 4, d_range)
                table.setItem(r_idx, 5, len_item)
                table.setItem(r_idx, 6, io_item)
                table.setItem(r_idx, 7, std_item)

    def _open_add_dialog(self):
        curr_idx = self.sub_tabs.currentIndex()
        cat_map = ["BOLT", "NUT", "WASHER", "SCREW", "BOLT"]
        default_cat = cat_map[curr_idx] if curr_idx < len(cat_map) else "BOLT"
        dlg = AddSpecificationDialog(default_category=default_cat, parent=self)
        if dlg.exec():
            self.load_all_categories()
            QMessageBox.information(self, "Specification Added", "New fastener standard size added to the database.")

    def _delete_selected_size(self):
        curr_table = self.sub_tabs.currentWidget()
        if not isinstance(curr_table, QTableWidget):
            return

        selected_rows = curr_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "Select Row", "Please select a row in the table to delete.")
            return

        row = selected_rows[0].row()
        spec_id = int(curr_table.item(row, 0).text())
        size_name = curr_table.item(row, 2).text()

        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{size_name}' (ID #{spec_id})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            db_instance.delete_specification(spec_id)
            self.load_all_categories()
