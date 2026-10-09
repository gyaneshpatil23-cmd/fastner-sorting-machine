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
├── main.py                             # START HERE: opens the desktop app
├── run_all_tests.py                    # Automated test suite (8 checks)
├── build_classifier_dataset.py         # Roboflow download -> fastener_sorter_cls/ (one folder per class)
├── train_yolo_classifier.py            # Trains and tests the YOLO11n-cls model -> models/
│
├── backend/                            # Everything that is not a window or button
│   ├── app_config.py                   # Settings & constants: categories, thresholds, paths, model list
│   ├── app_logging.py                  # Log files: logs/application.log and logs.txt
│   ├── sqlite_database.py              # All database reads/writes (specs, bins, history, calibration, settings)
│   ├── camera_capture.py               # Live camera thread and camera discovery
│   ├── image_loading_and_overlays.py   # Load images, convert for display, draw boxes/labels, demo samples
│   ├── yolo_classifier.py              # Trained YOLO11n-cls classifier (works on ordinary camera photos)
│   ├── opencv_shape_classifier.py      # Offline classifier: OpenCV shape rules -> NUT/BOLT/SCREW/WASHER
│   ├── gemini_cloud_classifier.py      # Optional online classifier using Google Gemini
│   ├── opencv_measurement.py           # Measures the part in millimetres with OpenCV
│   ├── tolerance_and_bin_decision.py   # Tolerance check -> ACCEPT / REINSPECT / REJECT and which bin
│   ├── inspection_pipeline.py          # Runs one full inspection: classify -> measure -> verify -> save -> sort
│   └── esp32_communication.py          # Talks to the ESP32 over USB / Wi-Fi, plus the built-in simulator
│
├── frontend/                           # Windows, tabs and buttons (PySide6)
│   ├── main_window.py                  # Main window, header bar and Tab 1 (Live Inspection)
│   ├── inspection_result_panel.py      # Result panel on the right of Tab 1
│   ├── tab_bins_and_chute_angles.py    # Tab 2: sorting bins, chute angles, capacities
│   ├── tab_hardware_control.py         # Tab 3: ESP32 connection, live status, manual motor tests
│   ├── tab_iso_specifications.py       # Tab 4: standard sizes and tolerance limits
│   ├── tab_camera_calibration.py       # Tab 5: millimetres-per-pixel camera scale
│   ├── tab_inspection_history.py       # Tab 6: inspection history table and CSV export
│   ├── ai_settings_dialog.py           # Settings window: AI model and Gemini API key
│   └── app_stylesheet.py               # Colours, fonts and button styles
│
├── models/                             # Trained YOLO model, its class list and its test report
├── FASTENER SORTER.v3i.yolov11/        # Downloaded Roboflow dataset (photos with labelled boxes)
├── fastener_sorter_cls/                # Training images built from it, one folder per class
├── my_camera_photos/                   # Photos saved with 'Save Photo for Training' (created on first save)
├── training_runs/                      # Output of the last training run
├── firmware_esp32/                     # ESP32 sorter firmware (Arduino sketch)
├── sample_images/                      # Built-in demo sample images (M8 Bolt, Nut, Screw, Washer)
└── logs.txt                            # Step-by-step execution log
```

---

## 3. How to Run

Launch the application in PowerShell:
```powershell
python main.py
```

Run the automated test suite (it uses a temporary database, so your specs, bins and counters are not touched):
```powershell
python run_all_tests.py
```

### Identifying fasteners with the camera (YOLO)

The app starts with the trained **YOLO11n-cls** model when `models/fastener_yolo11n_cls.pt` exists, and with the laptop's built-in camera selected.

1. Click **Live Video** and hold the part inside the guide box in the middle of the picture.
2. Leave **Sort by Type Only** ticked: the part is named, measured and sent to the bin for its type, but its size is not judged against tolerances (the measurements are only approximate until the camera is calibrated). Untick it once a calibrated inspection camera is in place.
3. Click **INSPECT**.

**Teaching the model your own parts.** If the model names a part wrongly, start Live Video, choose the correct class next to *Teach the model*, and hold **Save Photo for Training** while turning the part (aim for 50 or more photos per class, plus some of the empty scene as `NO_FASTENER`). Photos go to `my_camera_photos/` and are included the next time you rebuild and retrain.

Rebuild the training images and retrain (CPU, about 35 minutes):
```powershell
python build_classifier_dataset.py
python train_yolo_classifier.py
```
The accuracy report is written to `models/fastener_yolo11n_cls_report.txt`. To use the external inspection camera by default, set `PREFER_BUILT_IN_CAMERA = False` in `backend/app_config.py`.

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
