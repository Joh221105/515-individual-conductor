"""Beat detection from a stream of vertical hand positions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class BeatUpdate:
    bpm: float | None
    beat_just_fired: bool


class BeatTracker:
    def __init__(
        self,
        min_interval_s: float,
        max_interval_s: float,
        min_swing_distance: float,
        history_length: int,
        timeout_s: float,
    ) -> None:
        self.min_interval_s = min_interval_s
        self.max_interval_s = max_interval_s
        self.min_swing_distance = min_swing_distance
        self.timeout_s = timeout_s
        self.intervals: deque[float] = deque(maxlen=history_length)
        self.last_y: float | None = None
        self.last_velocity: float | None = None
        self.last_peak_y: float | None = None
        self.last_beat_time: float | None = None
        self.bpm: float | None = None

    def update(self, timestamp: float, y_position: float | None) -> BeatUpdate:
        if y_position is None:
            return BeatUpdate(self.bpm, False)

        if self.last_y is None:
            self.last_y = y_position
            self.last_peak_y = y_position
            return BeatUpdate(self.bpm, False)

        velocity = y_position - self.last_y
        beat = False

        if velocity > 0:
            self.last_peak_y = y_position if self.last_peak_y is None else max(self.last_peak_y, y_position)

        direction_changed = (
            self.last_velocity is not None
            and self.last_velocity > 0
            and velocity <= 0
        )

        if direction_changed:
            swing = 0.0 if self.last_peak_y is None else self.last_peak_y - y_position
            interval = None if self.last_beat_time is None else timestamp - self.last_beat_time
            valid_swing = swing >= self.min_swing_distance
            valid_interval = (
                interval is None
                or self.min_interval_s <= interval <= self.max_interval_s
            )
            if valid_swing and valid_interval:
                beat = True
                if interval is not None:
                    self.intervals.append(interval)
                    self.bpm = 60.0 / median(self.intervals)
                self.last_beat_time = timestamp
            self.last_peak_y = y_position

        self.last_velocity = velocity
        self.last_y = y_position
        return BeatUpdate(self.bpm, beat)
