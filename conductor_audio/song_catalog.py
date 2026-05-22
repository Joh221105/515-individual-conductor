"""Built-in demo song definitions and section mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .auto_detect import normalize_mapping


ASSET_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_SONG_ID = "vivalavida"


@dataclass(frozen=True)
class SongConfig:
    song_id: str
    title: str
    midi_filename: str
    section_mapping: dict[str, list[int]]

    @property
    def midi_path(self) -> Path:
        return ASSET_DIR / self.midi_filename


BUILTIN_SONGS = (
    SongConfig(
        song_id="vivalavida",
        title="Viva La Vida",
        midi_filename="vivalavida_demo.mid",
        section_mapping=normalize_mapping(
            {
                "strings": [3, 5, 8],
                "vocals": [2],
                "rhythm": [4, 7, 11],
                "atmosphere": [0, 1, 6, 10],
            }
        ),
    ),
    SongConfig(
        song_id="demons",
        title="Demons",
        midi_filename="demons_demo.mid",
        section_mapping=normalize_mapping(
            {
                "strings": [4],
                "vocals": [0, 2],
                "rhythm": [3, 9],
                "atmosphere": [1, 5],
            }
        ),
    ),
    SongConfig(
        song_id="titanium",
        title="Titanium",
        midi_filename="titanium_demo.mid",
        section_mapping=normalize_mapping(
            {
                "strings": [4],
                "vocals": [2, 3],
                "rhythm": [1],
                "atmosphere": [0],
            }
        ),
    ),
)


def get_song(song_id: str) -> SongConfig:
    normalized_id = song_id.lower()
    for song in BUILTIN_SONGS:
        if song.song_id == normalized_id:
            return song
    choices = ", ".join(song.song_id for song in BUILTIN_SONGS)
    raise ValueError(f"Unknown song {song_id!r}. Choose one of: {choices}")
