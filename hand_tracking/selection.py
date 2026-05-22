"""Section selection rules derived from hand state."""

from __future__ import annotations

from collections.abc import Sequence


def target_from_finger_count(fingers_extended: int, section_order: Sequence[str]) -> str | None:
    """Map 1-based finger counts to sections; all fingers selects all sections."""
    if fingers_extended <= 0:
        return "all"
    if fingers_extended > len(section_order):
        return "all"
    return section_order[fingers_extended - 1]
