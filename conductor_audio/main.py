"""Entry point for the Conductor Baton audio mixer."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import threading
from pathlib import Path
from typing import Callable

from .audio_engine import AudioEngine
from .auto_detect import SECTION_ORDER, detect_section_mapping, normalize_mapping, print_mapping
from .song_catalog import BUILTIN_SONGS, SongConfig, get_song

LOGGER = logging.getLogger(__name__)


def load_manual_mapping(config_path: Path) -> dict[str, list[int]] | None:
    if not config_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("section_mapping", config_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    mapping = getattr(module, "SECTION_MAPPING", None)
    if not isinstance(mapping, dict):
        return None

    normalized = normalize_mapping(mapping)
    if any(normalized[section] for section in SECTION_ORDER):
        return normalized
    return None


def resolve_mapping(midi_path: Path, config_path: Path) -> dict[str, list[int]]:
    manual = load_manual_mapping(config_path)
    if manual is not None:
        print_mapping(manual, f"manual override: {config_path}")
        return manual

    detected = detect_section_mapping(midi_path)
    print_mapping(detected, "auto-detected from MIDI track names")
    return detected


def builtin_song_choices() -> tuple[str, ...]:
    return tuple(song.song_id for song in BUILTIN_SONGS)


def select_builtin_song(song_id: str | None) -> SongConfig | None:
    if song_id is not None:
        return get_song(song_id)

    from .song_select_ui import SongSelectionUI

    return SongSelectionUI().run()


def start_hand_tracker_safely(hand_tracker):
    if hand_tracker is None:
        return None
    try:
        hand_tracker.start()
    except RuntimeError as exc:
        LOGGER.warning("Hand tracking disabled: %s", exc)
        stop = getattr(hand_tracker, "stop", None)
        if callable(stop):
            stop()
        return None
    return hand_tracker


def start_hand_tracker_async(hand_tracker, on_started: Callable[[object], None]) -> threading.Thread | None:
    if hand_tracker is None:
        return None

    def run_startup() -> None:
        started = start_hand_tracker_safely(hand_tracker)
        if started is not None:
            on_started(started)

    thread = threading.Thread(target=run_startup, name="HandTrackerStartup", daemon=True)
    thread.start()
    return thread


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    project_dir = Path(__file__).resolve().parent
    soundfont_path = project_dir / "assets" / "FluidR3_GM.sf2"
    config_path = project_dir / "section_mapping.py"

    args = argparse.ArgumentParser(description="Conductor Baton MIDI audio mixer")
    args.add_argument("--song", choices=builtin_song_choices(), default=None, help="Built-in demo song to load.")
    args.add_argument("--midi", type=Path, default=None, help="Custom MIDI file. Skips the song selection screen.")
    args.add_argument("--soundfont", type=Path, default=soundfont_path)
    args.add_argument("--mapping", type=Path, default=None, help="Manual mapping file for a custom MIDI.")
    args.add_argument("--camera-index", type=int, default=None)
    args.add_argument("--no-hand-tracking", action="store_true")
    parsed = args.parse_args()

    if parsed.midi is not None:
        midi_path = parsed.midi
        mapping = resolve_mapping(midi_path, parsed.mapping or config_path)
    else:
        song = select_builtin_song(parsed.song)
        if song is None:
            return
        midi_path = song.midi_path
        mapping = song.section_mapping
        print_mapping(mapping, f"built-in song: {song.title}")

    engine = AudioEngine(midi_path, parsed.soundfont, mapping)
    hand_tracker = None
    if not parsed.no_hand_tracking:
        from hand_tracking import HandTracker
        from hand_tracking.demo import make_config

        hand_tracker = HandTracker(make_config(parsed.camera_index))
    from .mixer_ui import MixerUI

    ui = MixerUI(engine, hand_tracker=None)
    ui.draw_once()
    startup_thread = start_hand_tracker_async(hand_tracker, lambda started: setattr(ui, "hand_tracker", started))
    try:
        engine.start()
        ui.run()
    finally:
        if startup_thread is not None:
            startup_thread.join(timeout=2.0)
        if hand_tracker is not None:
            hand_tracker.stop()
        engine.stop()


if __name__ == "__main__":
    main()
