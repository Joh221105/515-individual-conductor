"""Finger counting and debounced pose classification."""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import hypot
from typing import Sequence

Point = tuple[float, float]

FINGER_JOINTS = (
    (8, 6),
    (12, 10),
    (16, 14),
    (20, 18),
)
THUMB_EXTENSION_MARGIN = 0.06
THUMB_DISTANCE_MARGIN = 0.035


def count_extended_fingers(landmarks: Sequence[Point], handedness: str) -> int:
    """Return the number of extended fingers for 21 normalized hand landmarks."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    count = count_extended_non_thumb_fingers(landmarks)

    thumb_tip_x = landmarks[4][0]
    thumb_ip_x = landmarks[3][0]
    wrist = landmarks[0]
    thumb_tip_farther = (
        hypot(landmarks[4][0] - wrist[0], landmarks[4][1] - wrist[1])
        > hypot(landmarks[3][0] - wrist[0], landmarks[3][1] - wrist[1]) + THUMB_DISTANCE_MARGIN
    )
    if handedness == "Left":
        thumb_extended = thumb_tip_x < thumb_ip_x - THUMB_EXTENSION_MARGIN or thumb_tip_farther
    else:
        thumb_extended = thumb_tip_x > thumb_ip_x + THUMB_EXTENSION_MARGIN or thumb_tip_farther
    if thumb_extended:
        count += 1

    return count


def count_extended_non_thumb_fingers(landmarks: Sequence[Point]) -> int:
    """Return extended index/middle/ring/pinky count, ignoring thumb drift."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    count = 0
    for tip_index, pip_index in FINGER_JOINTS:
        if landmarks[tip_index][1] < landmarks[pip_index][1]:
            count += 1
    return count


def classify_pose(fingers_extended: int) -> str:
    if fingers_extended <= 1:
        return "fist"
    if fingers_extended == 2:
        return "pointing"
    if fingers_extended == 3:
        return "ambiguous"
    return "open"


@dataclass
class PoseDebouncer:
    debounce_ms: int
    initial_pose: str = "ambiguous"

    def __post_init__(self) -> None:
        self.active_pose = self.initial_pose
        self.candidate_pose: str | None = None
        self.candidate_since: float | None = None

    def update(self, pose: str, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now

        if pose == self.active_pose:
            self.candidate_pose = None
            self.candidate_since = None
            return self.active_pose

        if pose != self.candidate_pose:
            self.candidate_pose = pose
            self.candidate_since = now
            return self.active_pose

        stable_for_ms = (now - (self.candidate_since or now)) * 1000.0
        if stable_for_ms >= self.debounce_ms:
            self.active_pose = pose
            self.candidate_pose = None
            self.candidate_since = None

        return self.active_pose
