"""Pure geometry for section targeting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

Zone = tuple[float, float, float, float]


@dataclass
class ZoneSelector:
    zones: Mapping[str, Zone]
    hysteresis: float = 0.03

    def __post_init__(self) -> None:
        self.current: str | None = None

    def update(self, position: tuple[float, float] | None) -> str | None:
        if position is None:
            self.current = None
            return None

        if self.current is not None and self._contains(self.current, position, self.hysteresis):
            return self.current

        for name, zone in self.zones.items():
            if self._point_in_zone(position, zone, 0.0):
                self.current = name
                return name

        self.current = None
        return None

    def _contains(self, name: str, position: tuple[float, float], margin: float) -> bool:
        zone = self.zones.get(name)
        return False if zone is None else self._point_in_zone(position, zone, margin)

    @staticmethod
    def _point_in_zone(position: tuple[float, float], zone: Zone, margin: float) -> bool:
        x, y = position
        zx, zy, width, height = zone
        return (
            zx - margin <= x <= zx + width + margin
            and zy - margin <= y <= zy + height + margin
        )


def update_target_for_pose(
    pose: str,
    previous_target: str | None,
    pointed_target: str | None,
) -> str | None:
    if pose == "open":
        return "all"
    if pose == "pointing":
        return pointed_target
    return previous_target
