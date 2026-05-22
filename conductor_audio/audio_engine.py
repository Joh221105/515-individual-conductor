"""MIDI playback engine backed by FluidSynth."""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido

from .auto_detect import SECTION_ORDER, normalize_mapping

LOGGER = logging.getLogger(__name__)

DEFAULT_BPM = 120.0
DEFAULT_BRIGHTNESS = 0.7
UI_CONTROLLED_CC = {7, 74}
ACCENT_FILENAMES = {
    "strings": "strings_accent.wav",
    "vocals": "vocals_accent.wav",
    "rhythm": "rhythm_accent.wav",
    "atmosphere": "atmosphere_accent.wav",
}


@dataclass(frozen=True)
class TimedMidiEvent:
    beat: float
    message: mido.Message


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def scale_volume_to_cc7(value: float) -> int:
    return int((clamp(value, 0.0, 1.0) ** 2.0) * 127)


def scale_unit_to_cc(value: float) -> int:
    return int(clamp(value, 0.0, 1.0) * 127)


def build_timed_events(midi: mido.MidiFile) -> list[TimedMidiEvent]:
    events: list[TimedMidiEvent] = []
    ticks_per_beat = midi.ticks_per_beat or 480

    for track in midi.tracks:
        absolute_ticks = 0
        for message in track:
            absolute_ticks += int(message.time)
            if not message.is_meta:
                events.append(TimedMidiEvent(absolute_ticks / ticks_per_beat, message.copy(time=0)))

    events.sort(key=lambda event: event.beat)
    return events


def natural_bpm(midi: mido.MidiFile) -> float:
    first_tempo = None
    for track in midi.tracks:
        elapsed = 0
        for message in track:
            elapsed += message.time
            if message.is_meta and message.type == "set_tempo":
                candidate = (elapsed, float(mido.tempo2bpm(message.tempo)))
                if first_tempo is None or candidate[0] < first_tempo[0]:
                    first_tempo = candidate
    return first_tempo[1] if first_tempo is not None else DEFAULT_BPM


class AudioEngine:
    def __init__(
        self,
        midi_path: str | Path,
        soundfont_path: str | Path,
        section_mapping: dict[str, list[int]],
        accent_dir: str | Path | None = None,
        synth: Any | None = None,
    ) -> None:
        self.midi_path = Path(midi_path)
        self.soundfont_path = Path(soundfont_path)
        self.accent_dir = Path(accent_dir) if accent_dir is not None else self.midi_path.parent / "accents"
        self.section_mapping = normalize_mapping(section_mapping)
        self.channel_to_section = self._build_channel_index(self.section_mapping)

        self.midi = mido.MidiFile(str(self.midi_path))
        self.events = build_timed_events(self.midi)
        self.original_bpm = natural_bpm(self.midi)
        self.current_bpm = self.original_bpm

        self.lock = threading.RLock()
        self.playing = False
        self.paused = False
        self.thread: threading.Thread | None = None
        self.active_notes: dict[tuple[int, int], list[int]] = {}
        self.channel_activity = {channel: 0 for channel in range(16)}

        self.section_state = {
            section: {"volume": 1.0, "brightness": DEFAULT_BRIGHTNESS, "octave": 0}
            for section in SECTION_ORDER
        }

        self.synth = synth if synth is not None else self._create_synth()
        self.soundfont_id = self._load_soundfont()
        self.accent_sounds = self._load_accents()
        self._apply_initial_controls()

    def start(self) -> None:
        if self.playing:
            return
        self.playing = True
        self.paused = False
        self.thread = threading.Thread(target=self._playback_loop, name="midi-playback", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.playing = False
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        self._all_notes_off()
        if hasattr(self.synth, "delete"):
            self.synth.delete()

    def pause(self) -> None:
        with self.lock:
            self.paused = True
        self._all_notes_off()

    def resume(self) -> None:
        with self.lock:
            self.paused = False

    def toggle_pause(self) -> bool:
        with self.lock:
            next_state = not self.paused
        if next_state:
            self.pause()
        else:
            self.resume()
        return next_state

    def set_volume(self, section: str, value: float) -> None:
        section = section.lower()
        cc_value = scale_volume_to_cc7(value)
        with self.lock:
            self.section_state[section]["volume"] = clamp(value, 0.0, 1.0)
            channels = list(self.section_mapping.get(section, []))
        for channel in channels:
            self.synth.cc(channel, 7, cc_value)

    def set_brightness(self, section: str, value: float) -> None:
        section = section.lower()
        cc_value = scale_unit_to_cc(value)
        with self.lock:
            self.section_state[section]["brightness"] = clamp(value, 0.0, 1.0)
            channels = list(self.section_mapping.get(section, []))
        for channel in channels:
            self.synth.cc(channel, 74, cc_value)

    def set_octave(self, section: str, offset: int) -> None:
        section = section.lower()
        with self.lock:
            self.section_state[section]["octave"] = int(clamp(offset, -2, 2))

    def set_tempo(self, bpm: float) -> None:
        with self.lock:
            self.current_bpm = clamp(float(bpm), 50.0, 200.0)

    def play_accent(self, section: str) -> None:
        section = section.lower()
        sound = self.accent_sounds.get(section)
        if sound is None:
            LOGGER.warning("Accent sample missing for section %s", section)
            return
        sound.play()

    def get_state(self) -> dict[str, Any]:
        with self.lock:
            state = {
                section: dict(self.section_state[section])
                for section in SECTION_ORDER
            }
            state["tempo"] = self.current_bpm
            state["original_tempo"] = self.original_bpm
            state["paused"] = self.paused
            state["meters"] = self._meters_locked()
        return state

    def _playback_loop(self) -> None:
        while self.playing:
            previous_beat = 0.0
            for event in self.events:
                if not self.playing:
                    break
                self._wait_for_event(event.beat - previous_beat)
                if not self.playing:
                    break
                while self.playing and self.paused:
                    time.sleep(0.02)
                if self.playing:
                    self._dispatch(event.message)
                previous_beat = event.beat
            self._all_notes_off()

    def _wait_for_event(self, beat_delta: float) -> None:
        remaining_beats = max(0.0, beat_delta)
        while self.playing and remaining_beats > 0.0:
            if self.paused:
                time.sleep(0.02)
                continue
            with self.lock:
                bpm = self.current_bpm
            step_beats = min(remaining_beats, 0.02 * bpm / 60.0)
            time.sleep(step_beats * 60.0 / bpm)
            remaining_beats -= step_beats

    def _dispatch(self, message: mido.Message) -> None:
        if not hasattr(message, "channel"):
            return

        channel = int(message.channel)
        if message.type == "note_on" and message.velocity > 0:
            note = self._note_for_note_on(channel, int(message.note))
            self.synth.noteon(channel, note, int(message.velocity))
            with self.lock:
                self.channel_activity[channel] += 1
            return

        if message.type in ("note_off", "note_on"):
            note = self._note_for_note_off(channel, int(message.note))
            velocity = int(getattr(message, "velocity", 0))
            self.synth.noteoff(channel, note)
            with self.lock:
                self.channel_activity[channel] = max(0, self.channel_activity[channel] - 1)
            return

        if message.type == "control_change":
            if int(message.control) in UI_CONTROLLED_CC and channel in self.channel_to_section:
                return
            self.synth.cc(channel, int(message.control), int(message.value))
        elif message.type == "program_change" and self.soundfont_id is not None:
            self.synth.program_select(channel, self.soundfont_id, 0, int(message.program))
        elif message.type == "pitchwheel":
            self.synth.pitch_bend(channel, int(message.pitch))

    def _note_for_note_on(self, channel: int, note: int) -> int:
        section = self.channel_to_section.get(channel)
        with self.lock:
            octave = self.section_state[section]["octave"] if section else 0
            shifted = int(clamp(note + octave * 12, 0, 127))
            self.active_notes.setdefault((channel, note), []).append(shifted)
        return shifted

    def _note_for_note_off(self, channel: int, note: int) -> int:
        with self.lock:
            stack = self.active_notes.get((channel, note))
            if stack:
                shifted = stack.pop()
                if not stack:
                    self.active_notes.pop((channel, note), None)
                return shifted
        return note

    def _all_notes_off(self) -> None:
        for channel in range(16):
            self.synth.cc(channel, 123, 0)
            self.synth.cc(channel, 120, 0)
        with self.lock:
            self.active_notes.clear()
            self.channel_activity = {channel: 0 for channel in range(16)}

    def _meters_locked(self) -> dict[str, float]:
        meters = {}
        for section, channels in self.section_mapping.items():
            activity = sum(self.channel_activity.get(channel, 0) for channel in channels)
            meters[section] = min(1.0, math.log1p(activity) / math.log(8))
        return meters

    def _apply_initial_controls(self) -> None:
        for section in SECTION_ORDER:
            self.set_volume(section, self.section_state[section]["volume"])
            self.set_brightness(section, self.section_state[section]["brightness"])

    def _load_soundfont(self) -> int | None:
        if not self.soundfont_path.exists():
            raise FileNotFoundError(f"Soundfont not found: {self.soundfont_path}")
        sfid = self.synth.sfload(str(self.soundfont_path))
        for channel in range(16):
            self.synth.program_select(channel, sfid, 0, 0)
        return sfid

    def _load_accents(self) -> dict[str, Any]:
        sounds = {}
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            for section, filename in ACCENT_FILENAMES.items():
                path = self.accent_dir / filename
                if path.exists():
                    sounds[section] = pygame.mixer.Sound(str(path))
                else:
                    LOGGER.warning("Accent sample missing: %s", path)
        except Exception as exc:
            LOGGER.warning("Accent mixer unavailable: %s", exc)
        return sounds

    def _create_synth(self) -> Any:
        try:
            import fluidsynth
        except ImportError as exc:
            raise RuntimeError(
                "pyFluidSynth is required. Install FluidSynth first, then run "
                "`pip install pyFluidSynth`."
            ) from exc

        synth = fluidsynth.Synth()
        try:
            synth.start(driver=None)
        except TypeError:
            synth.start()
        return synth

    @staticmethod
    def _build_channel_index(mapping: dict[str, list[int]]) -> dict[int, str]:
        return {
            channel: section
            for section, channels in mapping.items()
            for channel in channels
        }
