"""
SQLite Database module for AI Fastener Inspection System.
Manages standard fastener specifications, 10-tray sorting chute mappings,
camera calibration parameters, machine settings, and persistent inspection audits.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Any, Optional, Iterator
from datetime import datetime
from backend.config import BASE_DIR
from backend.logger import app_logger, log_session_step

# FASTENER_DB_PATH lets tests run against a throwaway database instead of production data
DB_PATH = os.getenv("FASTENER_DB_PATH") or (BASE_DIR / "fastener_inspection.db")

# Size labels that mean "this bin is not tied to one specific size"
GENERIC_SIZE_LABELS = ("Any Size", "Out of Spec", "Custom", "Configurable")

def default_tray_label(tray_id: int, category: str, size: str) -> str:
    """Builds the standard bin label, which describes what the bin is assigned to."""
    if category == "REJECT":
        return f"Bin {tray_id} (Reject / Out of Spec)"
    if size in GENERIC_SIZE_LABELS or not size:
        return f"Bin {tray_id} ({category.title()})"
    return f"Bin {tray_id} ({size})"


class FastenerDatabase:
    """Thread-safe SQLite database manager for the inspection system."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yields a connection that is committed on success and always closed afterwards."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Creates tables and populates default ISO metric standards and 10 sorting trays."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Specifications Table (Nominal dimensions and tolerance limits)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS specifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    size_name TEXT NOT NULL,
                    nominal_diameter REAL NOT NULL,
                    min_diameter REAL NOT NULL,
                    max_diameter REAL NOT NULL,
                    nominal_length REAL,
                    min_length REAL,
                    max_length REAL,
                    head_width REAL,
                    min_head_width REAL,
                    max_head_width REAL,
                    inner_diameter REAL,
                    min_inner_dia REAL,
                    max_inner_dia REAL,
                    outer_diameter REAL,
                    min_outer_dia REAL,
                    max_outer_dia REAL,
                    tolerance_grade TEXT DEFAULT 'ISO 965',
                    enabled INTEGER DEFAULT 1
                )
            """)

            # 2. Sorting Trays / Chute Mapping Table (10 Trays)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trays (
                    tray_id INTEGER PRIMARY KEY,
                    tray_name TEXT NOT NULL,
                    assigned_category TEXT,
                    assigned_size TEXT,
                    servo_angle INTEGER NOT NULL,
                    capacity INTEGER DEFAULT 200,
                    current_count INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1
                )
            """)

            # 3. Detailed Inspection Results Audit Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inspection_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    detected_size TEXT,
                    confidence REAL NOT NULL,
                    length_mm REAL,
                    stem_dia_mm REAL,
                    head_width_mm REAL,
                    inner_dia_mm REAL,
                    outer_dia_mm REAL,
                    decision TEXT NOT NULL,
                    assigned_tray INTEGER,
                    servo_angle INTEGER,
                    reason TEXT,
                    image_path TEXT
                )
            """)

            # 4. Camera Calibration Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calibration (
                    camera_id TEXT PRIMARY KEY,
                    pixel_to_mm_ratio REAL NOT NULL,
                    reference_dimension_mm REAL NOT NULL,
                    calibrated_at TEXT NOT NULL,
                    notes TEXT
                )
            """)

            # 5. Machine & Communication Settings Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS machine_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT
                )
            """)

            conn.commit()

        # Seed default ISO specifications and trays if empty
        self._seed_default_data()

    def _seed_default_data(self):
        """Populates initial ISO fastener tolerances and 10 chute sorting trays."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Seed Specifications
            cursor.execute("SELECT COUNT(*) FROM specifications")
            if cursor.fetchone()[0] == 0:
                defaults = [
                    # Bolts (M4, M5, M6, M8, M10, M12)
                    ("BOLT", "M4 x 20", 4.0, 3.82, 4.18, 20.0, 19.3, 20.7, 7.0, 6.78, 7.22, None, None, None, None, None, None),
                    ("BOLT", "M5 x 25", 5.0, 4.82, 5.18, 25.0, 24.2, 25.8, 8.0, 7.78, 8.22, None, None, None, None, None, None),
                    ("BOLT", "M6 x 30", 6.0, 5.82, 6.18, 30.0, 29.2, 30.8, 10.0, 9.78, 10.22, None, None, None, None, None, None),
                    ("BOLT", "M8 x 40", 8.0, 7.78, 8.22, 40.0, 39.0, 41.0, 13.0, 12.73, 13.27, None, None, None, None, None, None),
                    ("BOLT", "M10 x 50", 10.0, 9.78, 10.22, 50.0, 48.8, 51.2, 16.0, 15.73, 16.27, None, None, None, None, None, None),
                    ("BOLT", "M12 x 60", 12.0, 11.73, 12.27, 60.0, 58.5, 61.5, 18.0, 17.73, 18.27, None, None, None, None, None, None),

                    # Nuts (M4, M5, M6, M8, M10, M12)
                    ("NUT", "M4 Nut", 4.0, 3.85, 4.15, None, None, None, None, None, None, 4.0, 3.85, 4.15, 7.0, 6.78, 7.22),
                    ("NUT", "M5 Nut", 5.0, 4.85, 5.15, None, None, None, None, None, None, 5.0, 4.85, 5.15, 8.0, 7.78, 8.22),
                    ("NUT", "M6 Nut", 6.0, 5.85, 6.15, None, None, None, None, None, None, 6.0, 5.85, 6.15, 10.0, 9.78, 10.22),
                    ("NUT", "M8 Nut", 8.0, 7.85, 8.15, None, None, None, None, None, None, 8.0, 7.85, 8.15, 13.0, 12.73, 13.27),
                    ("NUT", "M10 Nut", 10.0, 9.85, 10.15, None, None, None, None, None, None, 10.0, 9.85, 10.15, 16.0, 15.73, 16.27),
                    ("NUT", "M12 Nut", 12.0, 11.85, 12.15, None, None, None, None, None, None, 12.0, 11.85, 12.15, 18.0, 17.73, 18.27),

                    # Washers (M4, M5, M6, M8, M10, M12)
                    ("WASHER", "M4 Washer", 4.3, 4.1, 4.5, None, None, None, None, None, None, 4.3, 4.1, 4.5, 9.0, 8.64, 9.36),
                    ("WASHER", "M5 Washer", 5.3, 5.1, 5.5, None, None, None, None, None, None, 5.3, 5.1, 5.5, 10.0, 9.64, 10.36),
                    ("WASHER", "M6 Washer", 6.4, 6.2, 6.6, None, None, None, None, None, None, 6.4, 6.2, 6.6, 12.0, 11.57, 12.43),
                    ("WASHER", "M8 Washer", 8.4, 8.2, 8.6, None, None, None, None, None, None, 8.4, 8.2, 8.6, 16.0, 15.57, 16.43),
                    ("WASHER", "M10 Washer", 10.5, 10.3, 10.7, None, None, None, None, None, None, 10.5, 10.3, 10.7, 20.0, 19.48, 20.52),

                    # Screws (M3 x 15, M4 x 20, M5 x 25, M6 x 30)
                    ("SCREW", "M3 x 15 Screw", 3.0, 2.85, 3.15, 15.0, 14.3, 15.7, 5.5, 5.2, 5.8, None, None, None, None, None, None),
                    ("SCREW", "M4 x 20 Screw", 4.0, 3.85, 4.15, 20.0, 19.3, 20.7, 7.0, 6.6, 7.4, None, None, None, None, None, None),
                    ("SCREW", "M5 x 25 Screw", 5.0, 4.85, 5.15, 25.0, 24.2, 25.8, 8.5, 8.1, 8.9, None, None, None, None, None, None),
                    ("SCREW", "M6 x 30 Screw", 6.0, 5.85, 6.15, 30.0, 29.2, 30.8, 10.0, 9.6, 10.4, None, None, None, None, None, None),
                ]
                cursor.executemany("""
                    INSERT INTO specifications (
                        category, size_name, nominal_diameter, min_diameter, max_diameter,
                        nominal_length, min_length, max_length, head_width, min_head_width, max_head_width,
                        inner_diameter, min_inner_dia, max_inner_dia, outer_diameter, min_outer_dia, max_outer_dia
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, defaults)

            # Seed 10 Trays
            cursor.execute("SELECT COUNT(*) FROM trays")
            if cursor.fetchone()[0] == 0:
                default_trays = [
                    (1, "Tray 1 (M8 Bolt)", "BOLT", "M8 x 40", 18, 200, 0, 1),
                    (2, "Tray 2 (M6 Bolt)", "BOLT", "M6 x 30", 36, 200, 0, 1),
                    (3, "Tray 3 (M10 Bolt)", "BOLT", "M10 x 50", 54, 150, 0, 1),
                    (4, "Tray 4 (M8 Nut)", "NUT", "M8 Nut", 72, 300, 0, 1),
                    (5, "Tray 5 (M6 Nut)", "NUT", "M6 Nut", 90, 300, 0, 1),
                    (6, "Tray 6 (M10 Nut)", "NUT", "M10 Nut", 108, 250, 0, 1),
                    (7, "Tray 7 (M8 Washer)", "WASHER", "M8 Washer", 126, 400, 0, 1),
                    (8, "Tray 8 (M6 Washer)", "WASHER", "M6 Washer", 144, 400, 0, 1),
                    (9, "Tray 9 (Wood Screw)", "SCREW", "M4 x 20 Screw", 162, 250, 0, 1),
                    (10, "Tray 10 (Reject / Out of Spec)", "REJECT", "Any Size", 180, 500, 0, 1),
                ]
                cursor.executemany("""
                    INSERT INTO trays (tray_id, tray_name, assigned_category, assigned_size, servo_angle, capacity, current_count, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, default_trays)

            # Seed Default Calibration (0.12 mm/pixel typical for 1080p at 250mm overhead distance)
            cursor.execute("SELECT COUNT(*) FROM calibration")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO calibration (camera_id, pixel_to_mm_ratio, reference_dimension_mm, calibrated_at, notes)
                    VALUES ('default', 0.125, 25.0, ?, 'Standard calibrated overhead inspection pad scale')
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

            # Seed Machine Settings
            cursor.execute("SELECT COUNT(*) FROM machine_settings")
            if cursor.fetchone()[0] == 0:
                settings = [
                    ("comm_mode", "SIMULATOR", "Active communication mode: USB_SERIAL, WIFI, or SIMULATOR"),
                    ("serial_port", "COM3", "ESP32 USB Serial COM Port"),
                    ("baud_rate", "115200", "ESP32 Serial Baud Rate"),
                    ("wifi_ip", "192.168.4.1", "ESP32 Wi-Fi IP Address"),
                    ("wifi_port", "8080", "ESP32 TCP / HTTP Port"),
                    ("conveyor_speed", "100", "Conveyor NEMA 17 Stepper Speed (mm/s)"),
                    ("pad_tilt_angle", "45", "Inspection pad MG996R servo tilt angle (degrees)"),
                    ("chute_home_angle", "0", "Rotating chute home angle (degrees)"),
                    ("multi_fastener_mode", "0", "Enable multi-fastener detection on inspection area (0=Single, 1=Multi)"),
                ]
                cursor.executemany("INSERT INTO machine_settings (key, value, description) VALUES (?, ?, ?)", settings)

            conn.commit()

    def get_specifications(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category and category != "ALL":
                cursor.execute("SELECT * FROM specifications WHERE category = ? AND enabled = 1 ORDER BY nominal_diameter ASC", (category.upper(),))
            else:
                cursor.execute("SELECT * FROM specifications WHERE enabled = 1 ORDER BY category ASC, nominal_diameter ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_distinct_categories(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT category FROM specifications WHERE enabled = 1 ORDER BY category ASC")
            cats = [row[0] for row in cursor.fetchall()]
            default_core = ["BOLT", "NUT", "WASHER", "SCREW"]
            for c in default_core:
                if c not in cats:
                    cats.append(c)
            return cats

    def add_specification(
        self,
        category: str,
        size_name: str,
        nominal_diameter: float,
        min_diameter: float,
        max_diameter: float,
        nominal_length: Optional[float] = None,
        min_length: Optional[float] = None,
        max_length: Optional[float] = None,
        head_width: Optional[float] = None,
        min_head_width: Optional[float] = None,
        max_head_width: Optional[float] = None,
        inner_diameter: Optional[float] = None,
        min_inner_dia: Optional[float] = None,
        max_inner_dia: Optional[float] = None,
        outer_diameter: Optional[float] = None,
        min_outer_dia: Optional[float] = None,
        max_outer_dia: Optional[float] = None,
        tolerance_grade: str = "ISO 965"
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO specifications (
                    category, size_name, nominal_diameter, min_diameter, max_diameter,
                    nominal_length, min_length, max_length, head_width, min_head_width, max_head_width,
                    inner_diameter, min_inner_dia, max_inner_dia, outer_diameter, min_outer_dia, max_outer_dia,
                    tolerance_grade, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                category.upper(), size_name, nominal_diameter, min_diameter, max_diameter,
                nominal_length, min_length, max_length, head_width, min_head_width, max_head_width,
                inner_diameter, min_inner_dia, max_inner_dia, outer_diameter, min_outer_dia, max_outer_dia,
                tolerance_grade
            ))
            conn.commit()
            log_session_step("DATABASE", f"Added new specification: {category} - {size_name}")
            return cursor.lastrowid

    def delete_specification(self, spec_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM specifications WHERE id = ?", (spec_id,))
            conn.commit()
            log_session_step("DATABASE", f"Deleted specification ID #{spec_id}")

    def save_batch_counters(self, counters: Dict[str, int]):
        """Persists batch counts to SQLite so session totals are never lost on restart."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for key, val in counters.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO machine_settings (key, value, description)
                    VALUES (?, ?, 'Persistent batch count')
                """, (f"count_{key}", str(val)))
            conn.commit()

    def load_batch_counters(self) -> Dict[str, int]:
        """Loads previously saved batch counters on startup."""
        counters = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM machine_settings WHERE key LIKE 'count_%'")
            for row in cursor.fetchall():
                key = row["key"].replace("count_", "")
                try:
                    counters[key] = int(row["value"])
                except ValueError:
                    counters[key] = 0
        return counters

    def get_trays(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if enabled_only:
                cursor.execute("SELECT * FROM trays WHERE enabled = 1 ORDER BY tray_id ASC")
            else:
                cursor.execute("SELECT * FROM trays ORDER BY tray_id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_reject_tray(self) -> Optional[Dict[str, Any]]:
        """Returns the active reject bin (enabled bin assigned to REJECT), or None if none is configured."""
        rejects = [t for t in self.get_trays(enabled_only=True) if t["assigned_category"] == "REJECT"]
        return rejects[-1] if rejects else None

    def update_tray(
        self,
        tray_id: int,
        assigned_category: str,
        assigned_size: str,
        servo_angle: int,
        capacity: int,
        enabled: int = 1,
        tray_name: Optional[str] = None
    ):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trays SET assigned_category = ?, assigned_size = ?, servo_angle = ?, capacity = ?, enabled = ?
                WHERE tray_id = ?
            """, (assigned_category, assigned_size, servo_angle, capacity, enabled, tray_id))
            if tray_name:
                cursor.execute("UPDATE trays SET tray_name = ? WHERE tray_id = ?", (tray_name, tray_id))
            conn.commit()

    def set_active_bin_count(self, count: int, start_angle: int = 20, end_angle: int = 160):
        """
        Dynamically configures the active number of sorting bins (e.g. 4 bins, 6 bins, 8 bins).
        Auto-calculates equidistant servo angles across the mechanical chute span.
        """
        count = max(2, min(16, count))
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Disable all currently
            cursor.execute("UPDATE trays SET enabled = 0")

            # Calculate equal angular steps
            step = (end_angle - start_angle) / (count - 1)
            angles = [int(round(start_angle + i * step)) for i in range(count)]

            default_presets = [
                ("BOLT", "M8 x 40"),
                ("NUT", "M8 Nut"),
                ("SCREW", "M4 x 20 Screw"),
                ("WASHER", "M8 Washer"),
                ("BOLT", "M6 x 30"),
                ("NUT", "M6 Nut"),
                ("WASHER", "M6 Washer"),
                ("BOLT", "M10 x 50"),
                ("NUT", "M10 Nut"),
                ("REJECT", "Any Size"),
            ]

            for idx in range(1, count + 1):
                angle = angles[idx - 1]
                # Default preset assignment (the reject preset is reserved for the last bin)
                if idx - 1 < len(default_presets) - 1:
                    preset_cat, preset_size = default_presets[idx - 1]
                else:
                    preset_cat, preset_size = "ANY", "Configurable"

                cursor.execute("SELECT assigned_category, assigned_size FROM trays WHERE tray_id = ?", (idx,))
                existing = cursor.fetchone()

                if idx == count:
                    # The last active bin is always the reject bin
                    category, size = "REJECT", "Out of Spec"
                elif existing and existing["assigned_category"] != "REJECT":
                    # Keep the operator's existing assignment for this bin
                    category, size = existing["assigned_category"], existing["assigned_size"]
                else:
                    category, size = preset_cat, preset_size

                # The label always describes what the bin is actually assigned to
                tray_name = default_tray_label(idx, category, size)

                if existing:
                    cursor.execute("""
                        UPDATE trays SET tray_name = ?, assigned_category = ?, assigned_size = ?, servo_angle = ?, enabled = 1
                        WHERE tray_id = ?
                    """, (tray_name, category, size, angle, idx))
                else:
                    cursor.execute("""
                        INSERT INTO trays (tray_id, tray_name, assigned_category, assigned_size, servo_angle, capacity, current_count, enabled)
                        VALUES (?, ?, ?, ?, ?, 250, 0, 1)
                    """, (idx, tray_name, category, size, angle))

            conn.commit()
        log_session_step("CONFIG", f"Configured {count} active sorting bins with angles {angles}")

    def increment_tray_count(self, tray_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE trays SET current_count = current_count + 1 WHERE tray_id = ?", (tray_id,))
            conn.commit()

    def reset_tray_counts(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE trays SET current_count = 0")
            conn.commit()

    def log_inspection(self, record: Dict[str, Any]) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO inspection_results (
                    timestamp, date, category, detected_size, confidence, length_mm, stem_dia_mm,
                    head_width_mm, inner_dia_mm, outer_dia_mm, decision, assigned_tray, servo_angle, reason, image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.get("timestamp", datetime.now().strftime("%H:%M:%S")),
                record.get("date", datetime.now().strftime("%Y-%m-%d")),
                record.get("category", "UNKNOWN"),
                record.get("detected_size", "Unknown Size"),
                float(record.get("confidence", 0.0)),
                record.get("length_mm"),
                record.get("stem_dia_mm"),
                record.get("head_width_mm"),
                record.get("inner_dia_mm"),
                record.get("outer_dia_mm"),
                record.get("decision", "REJECT"),
                record.get("assigned_tray", 10),
                record.get("servo_angle", 180),
                record.get("reason", ""),
                record.get("image_path", "")
            ))
            conn.commit()
            return cursor.lastrowid

    def get_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM inspection_results ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_history(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM inspection_results")
            conn.commit()

    def get_calibration(self, camera_id: str = "default") -> float:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pixel_to_mm_ratio FROM calibration WHERE camera_id = ?", (camera_id,))
            row = cursor.fetchone()
            if row:
                return float(row["pixel_to_mm_ratio"])
            return 0.125  # fallback mm/px

    def set_calibration(self, camera_id: str, ratio: float, ref_mm: float, notes: str = ""):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO calibration (camera_id, pixel_to_mm_ratio, reference_dimension_mm, calibrated_at, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (camera_id, ratio, ref_mm, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes))
            conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM machine_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Upsert the value only, so the setting's description is preserved
            cursor.execute("""
                INSERT INTO machine_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))
            conn.commit()

db_instance = FastenerDatabase()
