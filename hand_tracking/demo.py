"""Standalone debug visualizer for HandTracker."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import SimpleNamespace
import time

from hand_tracking import HandTracker
from hand_tracking.dashboard import render_dashboard


def make_config(camera_index: int | None = None):
    defaults = importlib.import_module("hand_tracking.config")
    values = {name: getattr(defaults, name) for name in dir(defaults) if name.isupper()}
    if camera_index is not None:
        values["CAMERA_INDEX"] = camera_index
    return SimpleNamespace(**values)


def list_cameras(max_index: int = 6) -> None:
    import cv2

    for index in range(max_index):
        cap = cv2.VideoCapture(index)
        opened = cap.isOpened()
        ok, frame = cap.read() if opened else (False, None)
        shape = None if frame is None else frame.shape
        print(f"camera {index}: opened={opened} read={ok} shape={shape}")
        cap.release()


def main() -> None:
    import cv2

    parser = argparse.ArgumentParser(description="Run the hand tracking debug display.")
    parser.add_argument("--camera-index", type=int, default=None, help="OpenCV camera index to use.")
    parser.add_argument("--list-cameras", action="store_true", help="Probe camera indexes and exit.")
    parser.add_argument("--camera-view", action="store_true", help="Show the raw camera overlay instead of the mixer dashboard.")
    parser.add_argument("--no-audio", action="store_true", help="Run hand tracking without starting MIDI playback.")
    parser.add_argument("--song", default=None, help="Built-in demo song to play.")
    parser.add_argument("--midi", type=Path, default=None, help="MIDI file to play.")
    parser.add_argument("--soundfont", type=Path, default=None, help="SoundFont file to use.")
    parser.add_argument("--mapping", type=Path, default=None, help="Section mapping Python file.")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    config = make_config(args.camera_index)
    tracker = HandTracker(config)
    engine = None
    if not args.no_audio:
        engine = create_audio_engine(args.midi, args.soundfont, args.mapping, args.song)
        engine.start()
    tracker.start()
    try:
        while True:
            if args.camera_view:
                frame = tracker.get_debug_frame()
                window_title = "Hand Tracking Camera Debug"
            else:
                audio_state = engine.get_state() if engine is not None else None
                frame = render_dashboard(tracker.get_state(), config.ZONES, audio_state)
                window_title = "Conductor Section Status"
            if frame is not None:
                cv2.imshow(window_title, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            time.sleep(0.001)
    finally:
        tracker.stop()
        if engine is not None:
            engine.stop()
        cv2.destroyAllWindows()


def create_audio_engine(
    midi_path: Path | None,
    soundfont_path: Path | None,
    mapping_path: Path | None,
    song_id: str | None = None,
):
    from conductor_audio.audio_engine import AudioEngine
    from conductor_audio.main import resolve_mapping, select_builtin_song

    project_dir = Path(__file__).resolve().parents[1] / "conductor_audio"
    soundfont = soundfont_path or project_dir / "assets" / "FluidR3_GM.sf2"
    if midi_path is not None:
        midi = midi_path
        mapping_config = mapping_path or project_dir / "section_mapping.py"
        mapping = resolve_mapping(midi, mapping_config)
    else:
        song = select_builtin_song(song_id)
        if song is None:
            raise SystemExit(0)
        midi = song.midi_path
        mapping = song.section_mapping
    return AudioEngine(midi, soundfont, mapping)


if __name__ == "__main__":
    main()
