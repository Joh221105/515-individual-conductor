"""Saved Viva La Vida manual channel mapping.

The built-in song picker uses per-song mappings from song_catalog.py.
Custom MIDI runs can still pass this file with --mapping.
"""

SECTION_MAPPING = {
    "strings": [3, 5, 8],
    "vocals": [2],
    "rhythm": [4, 7, 11],
    "atmosphere": [0, 1, 6, 10],
}
