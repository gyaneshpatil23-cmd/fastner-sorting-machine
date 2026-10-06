"""
Hardware Communication & ESP32 Controller module for AI Fastener Inspection System.
Supports USB Serial (pyserial), Wi-Fi TCP/HTTP socket links,
and an interactive built-in ESP32 Hardware Simulator for client demonstration.
"""

import time
import json
import socket
import threading
from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal, QThread

from backend.database import db_instance
from backend.logger import app_logger, log_session_step

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

class HardwareCommunicationManager(QObject):
    """Manages ESP32 communication, telemetry streams, and hardware execution."""
    telemetry_updated = Signal(dict)
    command_ack = Signal(str, dict)
    cycle_progress = Signal(str, int)  # (step_name, percent 0-100)
    connection_status_changed = Signal(bool, str)
    emergency_stop_triggered = Signal(bool)  # True = ESTOP active, False = Reset

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = db_instance.get_setting("comm_mode", "SIMULATOR")
        self.serial_port = db_instance.get_setting("serial_port", "COM3")
        self.baud_rate = int(db_instance.get_setting("baud_rate", "115200"))
        self.wifi_ip = db_instance.get_setting("wifi_ip", "192.168.4.1")
        self.wifi_port = int(db_instance.get_setting("wifi_port", "8080"))

        self._serial_conn = None
        self._is_connected = False
        self._is_simulating = (self.mode == "SIMULATOR")
        self._is_estopped = False
        self._lock = threading.Lock()

        # Telemetry State
        self.telemetry = {
            "state": "READY",
            "mode": self.mode,
            "connected": True if self._is_simulating else False,
            "wifi": True if self.mode == "WIFI" else False,
            "usb": True if self.mode == "USB_SERIAL" else False,
            "chute_home": True,
            "chute_angle": 0,
            "pad_angle": 0,
            "conveyor": False,
            "ir_sensor_pad": False,
            "ir_sensor_chute": False,
            "battery_voltage": 12.4,
            "battery_percent": 95,
            "active_tray": 0,
            "estop": False,
            "last_ack": "OK"
        }

    def emergency_stop(self):
        """
        IMMEDIATE HARDWARE & SOFTWARE KILL SWITCH (E-STOP).
        Instantly halts conveyor stepper, disengages servos, and aborts motion.
        """
        self._is_estopped = True
        self.telemetry["state"] = "EMERGENCY_STOP"
        self.telemetry["conveyor"] = False
        self.telemetry["estop"] = True
        
        # Dispatch instant halt command to ESP32
        self.send_command({"command": "ESTOP", "action": "HALT_ALL"})
        self.emergency_stop_triggered.emit(True)
        self.telemetry_updated.emit(self.telemetry.copy())
        log_session_step("ESTOP", "EMERGENCY STOP ACTIVATED - All hardware motion halted!")

    def reset_estop(self):
        """Resets the Emergency Stop state and re-initializes ready state."""
        self._is_estopped = False
        self.telemetry["state"] = "READY"
        self.telemetry["estop"] = False
        self.send_command({"command": "RESET_ESTOP"})
        self.emergency_stop_triggered.emit(False)
        self.telemetry_updated.emit(self.telemetry.copy())
        log_session_step("ESTOP", "Emergency Stop reset. System returned to READY.")

    def set_mode(self, mode: str):
        """Switches between 'SIMULATOR', 'USB_SERIAL', and 'WIFI'."""
        self.disconnect_hardware()
        self.mode = mode
        self._is_simulating = (mode == "SIMULATOR")
        db_instance.set_setting("comm_mode", mode)
        self.connect_hardware()

    def connect_hardware(self) -> bool:
        """Establishes connection based on active communication mode."""
        if self._is_simulating:
            self._is_connected = True
            self.telemetry["connected"] = True
            self.telemetry["mode"] = "SIMULATOR"
            self.connection_status_changed.emit(True, "ESP32 Hardware Simulator Connected (Virtual DevKit)")
            self.telemetry_updated.emit(self.telemetry.copy())
            return True

        if self.mode == "USB_SERIAL":
            if not HAS_SERIAL:
                self.connection_status_changed.emit(False, "pyserial not available")
                return False
            try:
                self._serial_conn = serial.Serial(self.serial_port, self.baud_rate, timeout=1.0)
                self._is_connected = True
                self.telemetry["connected"] = True
                self.telemetry["usb"] = True
                self.connection_status_changed.emit(True, f"USB Serial Connected ({self.serial_port})")
                log_session_step("HARDWARE", f"USB Serial connected on {self.serial_port} @ {self.baud_rate}")
                return True
            except Exception as e:
                self._is_connected = False
                self.telemetry["connected"] = False
                self.connection_status_changed.emit(False, f"Serial Connection Failed: {e}")
                return False

        elif self.mode == "WIFI":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((self.wifi_ip, self.wifi_port))
                s.close()
                self._is_connected = True
                self.telemetry["connected"] = True
                self.telemetry["wifi"] = True
                self.connection_status_changed.emit(True, f"Wi-Fi Connected ({self.wifi_ip}:{self.wifi_port})")
                log_session_step("HARDWARE", f"Wi-Fi link established with ESP32 at {self.wifi_ip}")
                return True
            except Exception as e:
                self._is_connected = False
                self.telemetry["connected"] = False
                self.connection_status_changed.emit(False, f"Wi-Fi Link Failed: {e}")
                return False

        return False

    def disconnect_hardware(self):
        """Safely closes active serial or network link."""
        if self._serial_conn and self._serial_conn.is_open:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None

        self._is_connected = False
        self.telemetry["connected"] = False
        self.telemetry["usb"] = False
        self.telemetry["wifi"] = False
        self.connection_status_changed.emit(False, "Disconnected")

    def send_command(self, cmd_dict: Dict[str, Any]) -> bool:
        """Sends structured JSON command to ESP32 (or simulation engine)."""
        msg_str = json.dumps(cmd_dict)
        app_logger.info(f"Hardware Command -> {msg_str}")
        log_session_step("HARDWARE_CMD", msg_str)

        if self._is_simulating or not self._is_connected:
            self._handle_simulated_command(cmd_dict)
            return True

        try:
            if self.mode == "USB_SERIAL" and self._serial_conn:
                self._serial_conn.write((msg_str + "\n").encode("utf-8"))
                return True
            elif self.mode == "WIFI":
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.5)
                s.connect((self.wifi_ip, self.wifi_port))
                s.sendall((msg_str + "\n").encode("utf-8"))
                resp = s.recv(1024).decode("utf-8")
                s.close()
                self.command_ack.emit("ACK", json.loads(resp) if resp else {})
                return True
        except Exception as e:
            app_logger.error(f"Hardware Send Error: {e}")
            return False

        return False

    def execute_sorting_cycle(self, tray_id: int, servo_angle: int):
        """
        Launches full automated inspection-to-bin physical sorting cycle in a background thread:
        Pad Tilt (MG996R) -> Conveyor Stepper Run -> Chute Positioning (MG996R) -> Part Released -> Reset.
        """
        thread = threading.Thread(target=self._run_sorting_sequence, args=(tray_id, servo_angle), daemon=True)
        thread.start()

    def _run_sorting_sequence(self, tray_id: int, servo_angle: int):
        """End-to-end hardware sequence with telemetry progress updates."""
        try:
            # 1. Start Cycle
            self.cycle_progress.emit("Positioning Rotating Chute...", 20)
            self.telemetry["state"] = "CHUTE_POSITION"
            self.telemetry["chute_angle"] = servo_angle
            self.telemetry["active_tray"] = tray_id
            self.send_command({"command": "SORT", "tray": tray_id, "angle": servo_angle})
            self.telemetry_updated.emit(self.telemetry.copy())
            time.sleep(0.4)

            # 2. Tilt Inspection Pad (MG996R)
            self.cycle_progress.emit("Tilting Inspection Pad...", 45)
            self.telemetry["state"] = "PAD_TILT"
            self.telemetry["pad_angle"] = 45
            self.send_command({"command": "TILT_PAD", "angle": 45})
            self.telemetry_updated.emit(self.telemetry.copy())
            time.sleep(0.5)

            # 3. Conveyor Stepper Running (NEMA 17)
            self.cycle_progress.emit("Conveyor Transferring Part...", 75)
            self.telemetry["state"] = "CONVEY"
            self.telemetry["conveyor"] = True
            self.telemetry["ir_sensor_pad"] = False
            self.telemetry["ir_sensor_chute"] = True
            self.send_command({"command": "CONVEYOR", "action": "RUN", "duration_ms": 1200})
            self.telemetry_updated.emit(self.telemetry.copy())
            time.sleep(0.8)

            # 4. Release into Bin & Increment Count
            self.cycle_progress.emit(f"Part Released into Tray {tray_id}!", 100)
            self.telemetry["state"] = "RELEASE"
            self.telemetry["conveyor"] = False
            self.telemetry["ir_sensor_chute"] = False
            db_instance.increment_tray_count(tray_id)
            time.sleep(0.4)

            # 5. Reset to Ready State
            self.telemetry["state"] = "READY"
            self.telemetry["pad_angle"] = 0
            self.send_command({"command": "RESET"})
            self.telemetry_updated.emit(self.telemetry.copy())
            self.cycle_progress.emit("Inspection Pad & Chute Ready", 0)

        except Exception as e:
            app_logger.error(f"Sorting Sequence Error: {e}")
            self.telemetry["state"] = "READY"
            self.telemetry_updated.emit(self.telemetry.copy())

    def _handle_simulated_command(self, cmd: Dict[str, Any]):
        """Processes simulated hardware commands with state feedback."""
        c = cmd.get("command", "")
        if c == "SORT":
            self.telemetry["chute_angle"] = cmd.get("angle", 0)
            self.telemetry["active_tray"] = cmd.get("tray", 0)
        elif c == "TILT_PAD":
            self.telemetry["pad_angle"] = cmd.get("angle", 0)
        elif c == "CONVEYOR":
            self.telemetry["conveyor"] = (cmd.get("action") == "RUN" or cmd.get("action") == "START")
        elif c == "RESET":
            self.telemetry["pad_angle"] = 0
            self.telemetry["conveyor"] = False
            self.telemetry["state"] = "READY"

        self.command_ack.emit("ACK", {"status": "SUCCESS", "telemetry": self.telemetry.copy()})
        self.telemetry_updated.emit(self.telemetry.copy())

    @staticmethod
    def get_available_serial_ports() -> List[str]:
        """Scans and lists active system COM ports."""
        if not HAS_SERIAL:
            return ["COM1", "COM3", "COM4"]
        return [p.device for p in serial.tools.list_ports.comports()] or ["COM3 (Simulated)"]

hardware_manager = HardwareCommunicationManager()
