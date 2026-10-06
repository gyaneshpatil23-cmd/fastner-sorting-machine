# AI-Based Vision System for Automated Nut, Bolt & Fastener Size Inspection and Sorting

> **Industrial Engineering Desktop Software Suite**  
> *Complete Vision Classification, Calibrated OpenCV Measurement, Specification Verification, and ESP32 Sorting Chute System*

---

## 1. System Overview

This application is a complete industrial inspection and sorting system built with **Python 3.x**, **PySide6**, **OpenCV**, and **SQLite**. It addresses all requirements from the engineering specification:

1. **Fastener Classification & Sizing**: Automatically classifies fasteners (**BOLT, NUT, SCREW, WASHER**) using classical OpenCV geometric feature extraction with optional Gemini Cloud Vision.
2. **Calibrated Dimensional Measurement**: Measures visible length (mm), stem/shank diameter (mm), head width (mm), inner hole diameter (mm), and outer diameter (mm) with sub-millimeter precision using calibrated optical scale.
3. **Specification & Tolerance Database**: Matches measured dimensions against standard ISO metric standards (M3 through M16) with strict tolerance windows.
4. **Consistency & Verification Engine**: Cross-checks visual class against measured dimensions to flag inconsistencies and issue `ACCEPT`, `REINSPECT`, or `REJECT` decisions.
5. **10-Tray Sorting Chute Control**: Directly commands an ESP32 microcontroller over **Wi-Fi** or **USB Serial** (with built-in interactive **Hardware Simulator**) to actuate the MG996R inspection pad tilt servo, NEMA 17 conveyor stepper, and MG996R rotating chute servo (angles 18° to 180°).
6. **Camera Device Selector**: Auto-detects and prioritizes external USB inspection cameras over integrated webcams with runtime switching.
7. **Multi-Fastener Inspection**: Segments and dimensions multiple fasteners simultaneously on the inspection area.

---

## 2. System Architecture & 6 Dashboard Tabs

```text
fastener_vision/
│
├── main.py                         # Master Application Entry Point
├── test_app.py                     # Automated test suite
│
├── backend/
│   ├── config.py                   # Environment variables, constants & thresholds
│   ├── logger.py                   # Structured logging & session tracking
│   ├── database.py                 # SQLite database (ISO specs, 10 trays, audit logs)
│   ├── dimensional_measurement.py  # Calibrated OpenCV geometric measurement engine
│   ├── verification_engine.py      # Tolerance evaluation & 10-tray chute angle mapping
│   ├── hardware_comm.py            # ESP32 Wi-Fi / USB Serial & live hardware simulator
│   ├── local_classifier.py         # OpenCV geometric feature classifier (100% offline)
│   ├── gemini_client.py            # Optional cloud vision fallback
│   ├── camera.py                   # Multi-device camera manager with external cam preference
│   ├── classifier.py               # Asynchronous QThread inspection orchestrator
│   └── image_utils.py              # Image loading, annotation & sample dataset generation
│
├── frontend/
│   ├── main_window.py              # Master Multi-Tabbed Industrial Dashboard
│   ├── result_panel.py             # Live dimensional readouts, matched size & decision badge
│   ├── hardware_panel.py           # Live ESP32 telemetry, servo & conveyor testing
│   ├── specification_panel.py      # ISO specifications & tolerance database table
│   ├── trays_panel.py              # 10 Sorting Trays chute configuration & fill gauges
│   ├── calibration_panel.py        # Pixel-to-mm camera scale calibration
│   ├── history_panel.py            # Quality audit logs with CSV export
│   ├── settings_dialog.py          # Gemini API key & model settings
│   └── styles.py                   # Clean industrial engineering stylesheet
│
├── firmware_esp32/                 # ESP32 sorter firmware (Arduino sketch)
├── sample_images/                  # Built-in demo sample images (M8 Bolt, Nut, Screw, Washer)
└── logs.txt                        # Step-by-step execution log
```

---

## 3. How to Run

Launch the application in PowerShell:
```powershell
python main.py
```

Run the automated test suite:
```powershell
python test_app.py
```

---

## 4. Hardware & Microcontroller Integration (ESP32)

### Physical Actuators & Sensors
- **Inspection Pad Servo**: MG996R digital metal-gear servo (Tilts 45° to release part onto conveyor).
- **Conveyor Stepper**: NEMA 17 stepper motor driven by TB6600 driver (STEP/DIR pulses from ESP32).
- **Rotating Chute Servo**: MG996R servo positioning the chute to 1 of 10 configured bins (Angles 18°, 36°, 54°, 72°, 90°, 108°, 126°, 144°, 162°, 180°).
- **Part Presence Sensors**: IR break-beam sensors on inspection pad and conveyor transfer point.

### Communication Protocol
The laptop software sends structured JSON commands over USB Serial (115200 baud) or Wi-Fi TCP/HTTP:
```json
{"command": "SORT", "tray": 3, "angle": 54}
{"command": "TILT_PAD", "angle": 45}
{"command": "CONVEYOR", "action": "RUN", "duration_ms": 1200}
{"command": "RESET"}
```

---

## 5. Answers to Client / Professor Feedback

1. **Hardware Communication**: Built-in bidirectional JSON command/telemetry manager supporting Wi-Fi and USB serial, with a live Hardware Simulator built right into the app for demonstration.
2. **Camera Positioning & Selection**: Overhead inspection pad setup with automatic external USB camera preference and runtime dropdown picker.
3. **Classification**: Pure OpenCV geometric feature classification (contour circularity, aspect ratio, radial variance, thread density) — no external model required.
4. **Dimensional Measurement**: Calibrated sub-millimeter measurements for Length, Stem Diameter, Head Width, Inner Hole Diameter, and Across-Flats Width.
5. **10-Bin Sorting Mechanism**: 10 configurable sorting trays with individual servo angles, capacity tracking, and automatic routing.
6. **Multi-Fastener Inspection**: Checkbox toggle on dashboard to segment and measure multiple fasteners simultaneously on the inspection area.
