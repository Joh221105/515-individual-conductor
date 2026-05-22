# Gesture Training Collector Design

## Goal

Add a PlatformIO-based ESP32-S3 firmware project and a Python host collector so BMI270 motion samples can be captured for gesture training.

## Hardware

- Board: Seeed Studio XIAO ESP32S3.
- IMU: BMI270 connected over I2C.
- Pins: BMI270 SDA on XIAO `D4`, BMI270 SCL on XIAO `D5`.
- Sample rate: 100 Hz.
- Capture length: 1 second, exactly 100 samples.

## Data Labels

The collector saves each capture under `data/wave/<label>/`.

| User-facing gesture | Label | Intended action |
| --- | --- | --- |
| Sharp up gesture | `sharp_up` | Increase volume |
| Sharp down gesture | `sharp_down` | Decrease volume |
| Horizontal line | `horizontal_line` | Mute |
| Circle | `circle` | Solo |
| `^` | `tempo_up` | Tempo up |
| `v` | `tempo_down` | Tempo down |

## Architecture

The firmware owns sensor initialization and 100 Hz timing. It stays idle until the host sends a serial `CAPTURE` command. For each command, the ESP32 samples the BMI270 for 1 second and streams one CSV row per sample between clear start and end markers.

The Python collector owns label selection, keyboard triggering, the 2-second pre-capture delay, filesystem layout, CSV headers, and validation. It asks what gesture is being collected, waits for a keypress, delays 2 seconds, sends `CAPTURE`, reads exactly 100 rows, and writes a timestamped CSV file.

## Serial Protocol

Host to firmware:

```text
CAPTURE\n
```

Firmware to host:

```text
READY
BEGIN
<timestamp>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>
...
END
```

- `READY` is emitted after BMI270 initialization succeeds.
- `BEGIN` starts a capture payload.
- `END` ends a capture payload.
- The payload contains exactly 100 sample rows.
- `timestamp` is emitted by firmware in milliseconds from boot.
- Acceleration and gyroscope units follow the selected BMI270 library output units and are kept consistent across all samples.

## CSV Format

Every saved file uses this header:

```csv
timestamp,ax,ay,az,gx,gy,gz
```

Each file represents one 1-second capture. The host refuses to save partial captures unless explicitly extended later.

## Files

- Create `firmware/gesture_collector/` as a PlatformIO project.
- Create `tools/collect_gesture.py` for host-side collection.
- Create focused tests for collector parsing, folder naming, and sample validation without requiring hardware.
- Update `README.md` with upload, monitor, and collection commands.

## Error Handling

- Firmware prints an error and does not emit `READY` if BMI270 initialization fails.
- Collector exits with a clear message if the serial port cannot be opened.
- Collector rejects unknown labels.
- Collector rejects captures that do not contain exactly 100 rows.
- Collector rejects malformed sample rows before writing the CSV.

## Testing

Automated tests cover host logic that can run without hardware:

- Gesture choices map to expected folder labels.
- Timestamped output paths are created under `data/wave/<label>/`.
- Serial payload parsing accepts 100 valid rows.
- Serial payload parsing rejects partial or malformed captures.

Manual hardware verification covers:

- PlatformIO builds the XIAO ESP32S3 firmware.
- Serial monitor prints `READY`.
- Running the collector produces one CSV under the selected gesture folder.
- The CSV has one header row and 100 data rows.
