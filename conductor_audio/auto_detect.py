"""Infer MIDI channel groups from track names."""

from __future__ import annotations

from pathlib import Path

import mido


SECTION_ORDER = ("strings", "vocals", "rhythm", "atmosphere")

SECTION_KEYWORDS = {
    "strings": ("violin", "violins", "cello", "cellos", "violoncello", "strings", "string"),
    "vocals": ("trumpet", "vocal", "melody", "lead"),
    "rhythm": ("chime", "chimes", "steel", "pan", "pans", "bass", "guitar", "drum", "perc"),
    "atmosphere": ("echo", "synth", "choir", "piano", "keys", "pad"),
}


def normalize_mapping(mapping: dict[str, list[int]]) -> dict[str, list[int]]:
    """Return a complete, sorted, de-duplicated section mapping."""
    normalized: dict[str, list[int]] = {}
    for section in SECTION_ORDER:
        channels = mapping.get(section, [])
        normalized[section] = sorted({int(channel) for channel in channels if 0 <= int(channel) <= 15})
    return normalized


def detect_section_mapping(midi_path: str | Path) -> dict[str, list[int]]:
    midi = mido.MidiFile(str(midi_path))
    mapping = {section: set() for section in SECTION_ORDER}

    for track in midi.tracks:
        track_name = ""
        channels: set[int] = set()
        for message in track:
            if message.is_meta and message.type == "track_name":
                track_name = message.name.lower()
            elif hasattr(message, "channel"):
                channels.add(int(message.channel))

        section = section_for_track_name(track_name)
        if section is None:
            continue

        mapping[section].update(channels)

    return normalize_mapping({section: list(channels) for section, channels in mapping.items()})


def section_for_track_name(track_name: str) -> str | None:
    lowered = track_name.lower()
    if not lowered:
        return None

    scores = {
        section: sum(1 for keyword in keywords if keyword in lowered)
        for section, keywords in SECTION_KEYWORDS.items()
    }
    best_section, best_score = max(scores.items(), key=lambda item: item[1])
    return best_section if best_score > 0 else None


def print_mapping(mapping: dict[str, list[int]], source: str) -> None:
    print(f"Section mapping ({source}):")
    for section in SECTION_ORDER:
        channels = mapping.get(section, [])
        rendered = ", ".join(str(channel) for channel in channels) if channels else "(none)"
        print(f"  {section:10s}: {rendered}")
