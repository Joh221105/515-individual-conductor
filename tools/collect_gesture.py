#!/usr/bin/env python3
"""Collect labeled BMI270 gesture samples from ESP32-S3 serial output."""

from __future__ import annotations

import argparse
import csv
import sys
import termios
import time
import tty
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO


CSV_HEADER = "timestamp,ax,ay,az,gx,gy,gz"
EXPECTED_SAMPLES = 100
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "wave"


@dataclass(frozen=True)
class Gesture:
    choice: str
    label: str
    display: str
    action: str


GESTURES: tuple[Gesture, ...] = (
    Gesture("1", "sharp_up", "Sharp up gesture", "increase volume"),
    Gesture("2", "sharp_down", "Sharp down gesture", "decrease volume"),
    Gesture("3", "horizontal_line", "Horizontal line", "mute"),
    Gesture("4", "circle", "Circle", "solo"),
    Gesture("5", "tempo_up", "^", "tempo up"),
    Gesture("6", "tempo_down", "v", "tempo down"),
    Gesture("7", "idle", "Idle / noise", "ignore"),
)


class CaptureError(RuntimeError):
    """Raised when a serial capture is missing, incomplete, or malformed."""


def resolve_gesture(value: str) -> Gesture:
    normalized = value.strip().lower()
    for gesture in GESTURES:
        if normalized in {gesture.choice, gesture.label}:
            return gesture
    raise ValueError(f"Unknown gesture: {value}")


def next_sample_number(base_dir: Path, gesture: Gesture) -> int:
    gesture_dir = base_dir / gesture.label
    if not gesture_dir.exists():
        return 1
    existing = [
        f for f in gesture_dir.iterdir()
        if f.suffix == ".csv" and f.stem.startswith(f"{gesture.label}_")
    ]
    return len(existing) + 1


def make_output_path(base_dir: Path, gesture: Gesture, sample_num: int) -> Path:
    return base_dir / gesture.label / f"{gesture.label}_{sample_num:03d}.csv"


def _parse_sample_line(line: str) -> list[str]:
    row = next(csv.reader([line.strip()]))
    if len(row) != 7:
        raise CaptureError(f"Expected 7 columns, got {len(row)}: {line.strip()}")
    for value in row:
        try:
            float(value)
        except ValueError as exc:
            raise CaptureError(f"Non-numeric sample value: {value}") from exc
    return row


def parse_capture(serial_in: TextIO, expected_samples: int = EXPECTED_SAMPLES) -> list[list[str]]:
    rows: list[list[str]] = []
    in_capture = False

    while True:
        raw = serial_in.readline()
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line == "":
            raise CaptureError("Serial stream ended before END marker")
        stripped = line.strip()
        if not stripped or stripped == "READY":
            continue
        if stripped == "BEGIN":
            rows = []
            in_capture = True
            continue
        if stripped == "END":
            if not in_capture:
                raise CaptureError("Received END before BEGIN")
            if len(rows) != expected_samples:
                raise CaptureError(f"Expected {expected_samples} samples, received {len(rows)}")
            return rows
        if in_capture:
            rows.append(_parse_sample_line(stripped))


def normalize_timestamps(rows: list[list[str]]) -> list[list[str]]:
    """Remap the timestamp column so it runs from 0 to 1000 across the sample."""
    timestamps = [int(r[0]) for r in rows]
    t_min, t_max = timestamps[0], timestamps[-1]
    t_range = t_max - t_min if t_max != t_min else 1
    return [
        [str(round((int(r[0]) - t_min) / t_range * 1000))] + r[1:]
        for r in rows
    ]


def write_capture_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER.split(","))
        writer.writerows(normalize_timestamps(rows))


def collect_once(serial_port, gesture: Gesture, sample_num: int, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    serial_port.write(b"CAPTURE\n")
    rows = parse_capture(serial_port, EXPECTED_SAMPLES)
    path = make_output_path(output_dir, gesture, sample_num)
    write_capture_csv(path, rows)
    return path


def prompt_gesture() -> Gesture:
    print("Select gesture to collect:")
    for gesture in GESTURES:
        print(f"  {gesture.choice}. {gesture.display} ({gesture.action}) [{gesture.label}]")
    return resolve_gesture(input("Gesture: "))


def _read_single_key() -> str:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def wait_for_next(sample_num: int, action: str = "start countdown") -> None:
    print(f"\nSample #{sample_num} — Press Space to {action} (Ctrl+C to stop)...", end="", flush=True)
    while True:
        key = _read_single_key()
        if key == " ":
            print()
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect BMI270 gesture training samples over serial.")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--gesture", default=None, help="Gesture label or menu number. If omitted, prompt interactively.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gesture = resolve_gesture(args.gesture) if args.gesture else prompt_gesture()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        import serial
    except ImportError:
        print("pyserial is required. Install dependencies with: pip install -r requirements.txt", file=sys.stderr)
        return 2

    continuous = gesture.label == "idle"

    try:
        with serial.Serial(args.port, args.baud, timeout=5) as serial_port:
            start_num = next_sample_number(args.output_dir, gesture)
            sample_num = start_num
            mode_note = " (continuous mode)" if continuous else ""
            print(f"\nCollecting [{gesture.display}]{mode_note} — starting at sample #{sample_num}")
            while True:
                needs_prompt = (not continuous) or sample_num == start_num
                if needs_prompt:
                    try:
                        wait_for_next(
                            sample_num,
                            action="start continuous capture" if continuous else "start countdown",
                        )
                    except KeyboardInterrupt:
                        print(f"\nDone. Collected {sample_num - start_num} sample(s).")
                        break
                    if not continuous:
                        for i in range(2, 0, -1):
                            print(i)
                            time.sleep(1)
                        print("Collecting data...")
                    else:
                        print("Streaming continuously — Ctrl+C to stop.\n")
                try:
                    path = collect_once(serial_port, gesture, sample_num, args.output_dir)
                except CaptureError as exc:
                    print(f"Capture failed: {exc} — try again", file=sys.stderr)
                    continue
                except KeyboardInterrupt:
                    print(f"\nDone. Collected {sample_num - start_num} sample(s).")
                    break
                print(f"✓ Saved {path.name}  ({sample_num} total)")
                sample_num += 1
    except OSError as exc:
        print(f"Serial error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
