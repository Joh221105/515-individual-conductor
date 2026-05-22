import importlib
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mido
import pygame

from conductor_audio.auto_detect import detect_section_mapping
from conductor_audio.audio_engine import AudioEngine, build_timed_events, scale_volume_to_cc7
from conductor_audio.main import start_hand_tracker_async, start_hand_tracker_safely
from conductor_audio.song_catalog import BUILTIN_SONGS, DEFAULT_SONG_ID, get_song
from conductor_audio.song_select_ui import SongSelectionUI
from conductor_audio.mixer_ui import MixerUI, section_target_number, nearest_tempo_step, next_tempo_step, previous_tempo_step


class AutoDetectTests(unittest.TestCase):
    def _write_demo_midi(self) -> Path:
        midi = mido.MidiFile(ticks_per_beat=480)
        tracks = {
            "Violins": 4,
            "Trumpet Vocal Melody": 0,
            "Steel Pans": 6,
            "Piano RH": 8,
        }
        for name, channel in tracks.items():
            track = mido.MidiTrack()
            track.append(mido.MetaMessage("track_name", name=name, time=0))
            track.append(mido.Message("program_change", channel=channel, program=1, time=0))
            track.append(mido.Message("note_on", channel=channel, note=60, velocity=64, time=0))
            midi.tracks.append(track)

        handle = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
        handle.close()
        midi.save(handle.name)
        return Path(handle.name)

    def test_detects_sections_from_track_names_and_channels(self):
        midi_path = self._write_demo_midi()

        mapping = detect_section_mapping(midi_path)

        self.assertEqual(mapping["strings"], [4])
        self.assertEqual(mapping["vocals"], [0])
        self.assertEqual(mapping["rhythm"], [6])
        self.assertEqual(mapping["atmosphere"], [8])


class SongCatalogTests(unittest.TestCase):
    def test_builtin_songs_resolve_to_existing_midi_files(self):
        self.assertEqual(get_song(DEFAULT_SONG_ID).song_id, "vivalavida")

        for song in BUILTIN_SONGS:
            self.assertTrue(song.midi_path.exists(), song.midi_path)

    def test_builtin_song_mappings_include_every_section(self):
        for song in BUILTIN_SONGS:
            for section in ("strings", "vocals", "rhythm", "atmosphere"):
                self.assertGreaterEqual(len(song.section_mapping[section]), 1, f"{song.title}: {section}")

    def test_viva_la_vida_preserves_original_manual_mapping(self):
        song = get_song("vivalavida")

        self.assertEqual(song.section_mapping["strings"], [3, 5, 8])
        self.assertEqual(song.section_mapping["vocals"], [2])
        self.assertEqual(song.section_mapping["rhythm"], [4, 7, 11])
        self.assertEqual(song.section_mapping["atmosphere"], [0, 1, 6, 10])


class SongSelectionUITests(unittest.TestCase):
    def test_click_selection_closes_picker_display_before_returning_song(self):
        ui = SongSelectionUI.__new__(SongSelectionUI)
        ui.songs = BUILTIN_SONGS
        ui.cards = [pygame.Rect(0, 0, 100, 100)]
        ui.selected_index = 0

        with patch("conductor_audio.song_select_ui.pygame.display.quit") as quit_display:
            selected = ui._handle_click((10, 10))

        self.assertEqual(selected, BUILTIN_SONGS[0])
        quit_display.assert_called_once_with()


class HandTrackingStartupTests(unittest.TestCase):
    def test_missing_optional_hand_tracking_dependency_disables_tracker(self):
        tracker = type("Tracker", (), {"start": lambda _self: (_ for _ in ()).throw(RuntimeError("missing mediapipe"))})()

        with self.assertLogs("conductor_audio.main", level="WARNING") as logs:
            started = start_hand_tracker_safely(tracker)

        self.assertIsNone(started)
        self.assertIn("Hand tracking disabled", logs.output[0])

    def test_async_hand_tracking_start_does_not_block_ui_startup(self):
        release_start = threading.Event()
        started = []

        class SlowTracker:
            def start(self):
                release_start.wait(timeout=2.0)

        thread = start_hand_tracker_async(SlowTracker(), started.append)

        self.assertTrue(thread.is_alive())
        self.assertEqual(started, [])

        release_start.set()
        thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(started), 1)


class AudioEngineControlTests(unittest.TestCase):
    def test_volume_uses_perceptual_cc7_curve(self):
        self.assertEqual(scale_volume_to_cc7(0.0), 0)
        self.assertEqual(scale_volume_to_cc7(0.5), 31)
        self.assertEqual(scale_volume_to_cc7(1.0), 127)

    def test_control_methods_send_expected_midi_cc_values(self):
        engine = AudioEngine.__new__(AudioEngine)
        engine.section_mapping = {"strings": [4, 5]}
        engine.lock = importlib.import_module("threading").RLock()
        engine.section_state = {
            "strings": {"volume": 1.0, "brightness": 0.7, "octave": 0},
        }
        sent = []
        engine.synth = type(
            "Synth",
            (),
            {"cc": lambda _self, channel, control, value: sent.append((channel, control, value))},
        )()

        engine.set_volume("strings", 0.5)
        engine.set_brightness("strings", 0.25)

        self.assertEqual(sent, [(4, 7, 31), (5, 7, 31), (4, 74, 31), (5, 74, 31)])
        self.assertEqual(engine.section_state["strings"]["volume"], 0.5)
        self.assertEqual(engine.section_state["strings"]["brightness"], 0.25)

    def test_build_timed_events_expands_delta_ticks_to_absolute_beats(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.Message("note_on", channel=0, note=60, velocity=64, time=240))
        track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=240))
        midi.tracks.append(track)

        events = build_timed_events(midi)

        self.assertEqual([event.beat for event in events], [0.5, 1.0])

    def test_playback_ignores_midi_volume_cc_for_ui_controlled_channels(self):
        engine = AudioEngine.__new__(AudioEngine)
        engine.channel_to_section = {3: "strings"}
        sent = []
        engine.synth = type(
            "Synth",
            (),
            {"cc": lambda _self, channel, control, value: sent.append((channel, control, value))},
        )()

        engine._dispatch(mido.Message("control_change", channel=3, control=7, value=50))
        engine._dispatch(mido.Message("control_change", channel=3, control=11, value=80))

        self.assertEqual(sent, [(3, 11, 80)])


class MixerUITempoTests(unittest.TestCase):
    def test_tempo_is_limited_to_fixed_steps(self):
        self.assertEqual(nearest_tempo_step(114), 120)
        self.assertEqual(nearest_tempo_step(171), 180)
        self.assertEqual(next_tempo_step(120), 140)
        self.assertEqual(next_tempo_step(180), 180)
        self.assertEqual(previous_tempo_step(140), 120)
        self.assertEqual(previous_tempo_step(100), 100)

    def test_section_target_numbers_match_section_order(self):
        self.assertEqual(section_target_number("strings"), 1)
        self.assertEqual(section_target_number("vocals"), 2)
        self.assertEqual(section_target_number("rhythm"), 3)
        self.assertEqual(section_target_number("atmosphere"), 4)

    def test_simplified_layout_omits_removed_controls(self):
        ui = MixerUI.__new__(MixerUI)

        layout = ui._build_layout()

        self.assertNotIn("minus", layout["tempo"])
        self.assertNotIn("plus", layout["tempo"])
        self.assertNotIn("reset", layout["tempo"])
        for section in ("strings", "vocals", "rhythm", "atmosphere"):
            self.assertNotIn("knob", layout[section])
            self.assertNotIn("accent", layout[section])
            self.assertNotIn("octave", layout[section])

    def test_reads_targeted_section_from_optional_hand_tracker(self):
        state = type(
            "HandState",
            (),
            {
                "detected": True,
                "targeted_section": "vocals",
                "fingers_extended": 2,
                "pose": "pointing",
                "bpm": None,
            },
        )()
        tracker = type("Tracker", (), {"get_state": lambda _self: state})()
        ui = MixerUI.__new__(MixerUI)
        ui.hand_tracker = tracker

        self.assertIs(ui._hand_state(), state)
        self.assertEqual(ui._hand_targeted_section(), "vocals")

    def test_hand_target_is_empty_without_tracker_or_detection(self):
        ui = MixerUI.__new__(MixerUI)
        ui.hand_tracker = None

        self.assertIsNone(ui._hand_state())
        self.assertIsNone(ui._hand_targeted_section())


if __name__ == "__main__":
    unittest.main()
