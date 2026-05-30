"""Finger counting and debounced pose classification."""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import hypot
from typing import Sequence

Point = tuple[float, float]

FINGER_JOINTS = (
    (8, 6, 5),
    (12, 10, 9),
    (16, 14, 13),
    (20, 18, 17),
)
FINGER_EXTENSION_MARGIN = 0.05
THUMB_EXTENSION_MARGIN = 0.06
THUMB_DISTANCE_MARGIN = 0.035
THUMB_DIRECTION_MARGIN = 0.08


def count_extended_fingers(landmarks: Sequence[Point], handedness: str) -> int:
    """Return the number of extended fingers for 21 normalized hand landmarks."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    count = count_extended_non_thumb_fingers(landmarks)

    if is_thumb_extended(landmarks, handedness):
        count += 1

    return count


def count_extended_non_thumb_fingers(landmarks: Sequence[Point]) -> int:
    """Return extended index/middle/ring/pinky count, ignoring thumb drift."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    count = 0
    for tip_index, pip_index, mcp_index in FINGER_JOINTS:
        tip_y = landmarks[tip_index][1]
        pip_y = landmarks[pip_index][1]
        mcp_y = landmarks[mcp_index][1]
        if tip_y < pip_y - FINGER_EXTENSION_MARGIN and tip_y < mcp_y - FINGER_EXTENSION_MARGIN:
            count += 1
    return count


def is_thumb_extended(landmarks: Sequence[Point], handedness: str) -> bool:
    """Return whether the thumb is extended for 21 normalized hand landmarks."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    thumb_tip_x = landmarks[4][0]
    thumb_ip_x = landmarks[3][0]
    wrist = landmarks[0]
    thumb_tip_farther = (
        hypot(landmarks[4][0] - wrist[0], landmarks[4][1] - wrist[1])
        > hypot(landmarks[3][0] - wrist[0], landmarks[3][1] - wrist[1]) + THUMB_DISTANCE_MARGIN
    )
    if handedness == "Left":
        return thumb_tip_x < thumb_ip_x - THUMB_EXTENSION_MARGIN or thumb_tip_farther
    return thumb_tip_x > thumb_ip_x + THUMB_EXTENSION_MARGIN or thumb_tip_farther


def classify_thumb_gesture(landmarks: Sequence[Point], handedness: str) -> str | None:
    """Classify strict thumb-only tempo gestures from normalized hand landmarks."""
    if len(landmarks) < 21:
        raise ValueError("Expected 21 hand landmarks")

    if count_extended_non_thumb_fingers(landmarks) != 0:
        return None
    if not is_thumb_extended(landmarks, handedness):
        return None

    wrist = landmarks[0]
    thumb_base = landmarks[2]
    thumb_tip = landmarks[4]
    dx = thumb_tip[0] - thumb_base[0]
    dy = thumb_tip[1] - thumb_base[1]
    if abs(dy) < abs(dx) + THUMB_DIRECTION_MARGIN:
        return None

    upper_reference = min(wrist[1], thumb_base[1]) - THUMB_DIRECTION_MARGIN
    lower_reference = max(wrist[1], thumb_base[1]) + THUMB_DIRECTION_MARGIN
    if thumb_tip[1] <= upper_reference:
        return "thumbs_up"
    if thumb_tip[1] >= lower_reference:
        return "thumbs_down"
    return None


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


@dataclass
class GestureDebouncer:
    debounce_ms: int
    initial_gesture: str | None = None

    def __post_init__(self) -> None:
        self.active_gesture = self.initial_gesture
        self.candidate_gesture: str | None = None
        self.candidate_since: float | None = None

    def update(self, gesture: str | None, now: float | None = None) -> str | None:
        now = time.monotonic() if now is None else now

        if gesture == self.active_gesture:
            self.candidate_gesture = None
            self.candidate_since = None
            return self.active_gesture

        if gesture != self.candidate_gesture:
            self.candidate_gesture = gesture
            self.candidate_since = now
            return self.active_gesture

        stable_for_ms = (now - (self.candidate_since or now)) * 1000.0
        if stable_for_ms >= self.debounce_ms:
            self.active_gesture = gesture
            self.candidate_gesture = None
            self.candidate_since = None

        return self.active_gesture

    def reset(self) -> None:
        self.active_gesture = self.initial_gesture
        self.candidate_gesture = None
        self.candidate_since = None
