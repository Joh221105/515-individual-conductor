"""Camera-free status dashboard for hand tracking."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from hand_tracking.tracker import HandState

Zone = tuple[float, float, float, float]

BG = (24, 24, 28)
PANEL = (42, 42, 48)
PANEL_ACTIVE = (48, 64, 56)
PANEL_ALL = (58, 52, 36)
PANEL_LOCKED = (64, 44, 44)
TEXT = (238, 238, 242)
MUTED = (145, 145, 154)
SUBTLE = (88, 88, 96)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
GOLD = (234, 179, 8)
CYAN = (70, 210, 255)

SECTION_LABELS = {
    "strings": "Strings",
    "vocals": "Vocals",
    "rhythm": "Rhythm",
    "atmosphere": "Atmosphere",
}


def render_dashboard(
    state: HandState,
    zones: Mapping[str, Zone],
    audio_state: Mapping[str, object] | None = None,
    size: tuple[int, int] = (1280, 720),
) -> np.ndarray:
    """Render a mixer-like dashboard from state only; no camera pixels are used."""
    import cv2

    width, height = size
    frame = np.full((height, width, 3), BG, dtype=np.uint8)
    section_names = list(zones.keys())
    margin = 32
    gap = 18
    top = 84
    card_h = height - top - 156
    card_w = (width - margin * 2 - gap * (len(section_names) - 1)) // max(1, len(section_names))

    _draw_header(cv2, frame, state)

    for index, section in enumerate(section_names):
        x = margin + index * (card_w + gap)
        rect = (x, top, card_w, card_h)
        _draw_section_card(cv2, frame, rect, section, state, audio_state)

    _draw_status_strip(cv2, frame, state, audio_state, (margin, height - 94, width - margin * 2, 62))
    return frame


def _draw_header(cv2, frame: np.ndarray, state: HandState) -> None:
    title = "Conductor Sections"
    subtitle = "Camera hidden - hand tracking active"
    cv2.putText(frame, title, (32, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.05, TEXT, 2, cv2.LINE_AA)
    color = GREEN if state.detected else RED
    cv2.circle(frame, (frame.shape[1] - 42, 34), 10, color, -1)
    cv2.putText(frame, subtitle, (32, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.58, MUTED, 1, cv2.LINE_AA)


def _draw_section_card(
    cv2,
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
    section: str,
    state: HandState,
    audio_state: Mapping[str, object] | None,
) -> None:
    x, y, w, h = rect
    targeted = state.targeted_section == section or state.targeted_section == "all"
    locked_here = state.selection_locked and targeted
    color = PANEL
    if state.targeted_section == "all":
        color = PANEL_ALL
    elif locked_here:
        color = PANEL_LOCKED
    elif targeted:
        color = PANEL_ACTIVE

    cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), CYAN if targeted else SUBTLE, 3 if targeted else 1)

    label = SECTION_LABELS.get(section, section.title())
    cv2.putText(frame, label, (x + 22, y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.86, TEXT, 2, cv2.LINE_AA)

    status = _section_status(section, state)
    status_color = GOLD if state.targeted_section == "all" else GREEN if targeted else MUTED
    cv2.putText(frame, status, (x + 22, y + 78), cv2.FONT_HERSHEY_SIMPLEX, 0.62, status_color, 2, cv2.LINE_AA)

    meter_rect = (x + 26, y + 118, w - 52, h - 164)
    cv2.rectangle(frame, (meter_rect[0], meter_rect[1]), (meter_rect[0] + meter_rect[2], meter_rect[1] + meter_rect[3]), (20, 20, 24), -1)
    fill_ratio = _section_meter(section, audio_state)
    if not state.detected:
        fill_ratio = max(fill_ratio, 0.08)
    elif targeted:
        fill_ratio = max(fill_ratio, 0.72)
    fill_h = int(meter_rect[3] * fill_ratio)
    fill_color = GOLD if state.targeted_section == "all" else CYAN if targeted else SUBTLE
    cv2.rectangle(
        frame,
        (meter_rect[0], meter_rect[1] + meter_rect[3] - fill_h),
        (meter_rect[0] + meter_rect[2], meter_rect[1] + meter_rect[3]),
        fill_color,
        -1,
    )

    volume = _section_volume(section, audio_state)
    cv2.putText(frame, f"VOL {volume:.0%}", (x + 22, y + h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.48, MUTED, 1, cv2.LINE_AA)
    marker = "ON" if targeted else "--"
    cv2.putText(frame, marker, (x + w - 66, y + h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, TEXT, 2, cv2.LINE_AA)


def _draw_status_strip(
    cv2,
    frame: np.ndarray,
    state: HandState,
    audio_state: Mapping[str, object] | None,
    rect: tuple[int, int, int, int],
) -> None:
    x, y, w, h = rect
    cv2.rectangle(frame, (x, y), (x + w, y + h), (34, 34, 40), -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), SUBTLE, 1)
    bpm = "--" if state.bpm is None else f"{state.bpm:.1f}"
    tempo = _audio_tempo(audio_state)
    target = state.targeted_section or "none"
    gesture = state.tempo_gesture or "none"
    beat = "BEAT" if state.beat_just_fired else "idle"
    text = (
        f"Detected: {'yes' if state.detected else 'no'}    "
        f"Pose: {state.pose}    Fingers: {state.fingers_extended}    "
        f"Tempo Gesture: {gesture}    Targeted: {target}    "
        f"Locked: {'yes' if state.selection_locked else 'no'}    "
        f"Hand BPM: {bpm}    Song: {tempo} BPM    {beat}"
    )
    cv2.putText(frame, text, (x + 18, y + 39), cv2.FONT_HERSHEY_SIMPLEX, 0.58, TEXT, 1, cv2.LINE_AA)


def _section_status(section: str, state: HandState) -> str:
    if not state.detected:
        return "waiting"
    if state.targeted_section == "all":
        return "all sections"
    if state.targeted_section == section:
        return "locked" if state.selection_locked else "targeted"
    return "standby"


def _section_meter(section: str, audio_state: Mapping[str, object] | None) -> float:
    if audio_state is None:
        return 0.28
    meters = audio_state.get("meters")
    if not isinstance(meters, Mapping):
        return 0.28
    return float(max(0.0, min(1.0, meters.get(section, 0.0))))


def _section_volume(section: str, audio_state: Mapping[str, object] | None) -> float:
    if audio_state is None:
        return 1.0
    section_state = audio_state.get(section)
    if not isinstance(section_state, Mapping):
        return 1.0
    return float(max(0.0, min(1.0, section_state.get("volume", 1.0))))


def _audio_tempo(audio_state: Mapping[str, object] | None) -> str:
    if audio_state is None:
        return "--"
    tempo = audio_state.get("tempo")
    return "--" if tempo is None else f"{float(tempo):.0f}"
