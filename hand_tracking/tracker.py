"""Threaded webcam hand tracker built on MediaPipe Hands."""

from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass, replace
from types import ModuleType
from typing import Any

import numpy as np

from hand_tracking.beat import BeatTracker
from hand_tracking.pose import (
    PoseDebouncer,
    classify_pose,
    count_extended_fingers,
    count_extended_non_thumb_fingers,
)
from hand_tracking.selection import target_from_finger_count
from hand_tracking.zones import ZoneSelector, update_target_for_pose


@dataclass(frozen=True)
class HandState:
    detected: bool
    position: tuple[float, float]
    pose: str
    fingers_extended: int
    targeted_section: str | None
    selection_locked: bool
    bpm: float | None
    beat_just_fired: bool


class HandTracker:
    def __init__(self, config_module: ModuleType | None = None) -> None:
        self.config = config_module or importlib.import_module("hand_tracking.config")
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._capture: Any = None
        self._hands: Any = None
        self._mp_hands: Any = None
        self._mp_drawing: Any = None
        self._debug_frame: np.ndarray | None = None
        self._latest_landmarks: Any = None
        self._latest_connections: Any = None

        self._position: tuple[float, float] = (0.0, 0.0)
        self._position_initialized = False
        self._pose_debouncer = PoseDebouncer(self.config.POSE_DEBOUNCE_MS)
        self._zone_selector = ZoneSelector(self.config.ZONES, self.config.ZONE_HYSTERESIS)
        self._beat_tracker = BeatTracker(
            self.config.MIN_BEAT_INTERVAL_S,
            self.config.MAX_BEAT_INTERVAL_S,
            self.config.MIN_SWING_DISTANCE,
            self.config.BEAT_HISTORY_LENGTH,
            self.config.BEAT_TIMEOUT_S,
        )
        self._state = HandState(
            detected=False,
            position=self._position,
            pose="ambiguous",
            fingers_extended=0,
            targeted_section=None,
            selection_locked=False,
            bpm=None,
            beat_just_fired=False,
        )

    def start(self) -> None:
        if self._running:
            return

        cv2, mp = _load_runtime_dependencies()
        self._cv2 = cv2
        self._mp_drawing = mp.solutions.drawing_utils
        self._mp_hands = mp.solutions.hands
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.config.MAX_NUM_HANDS,
            min_detection_confidence=self.config.MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=self.config.MIN_TRACKING_CONFIDENCE,
        )
        self._capture = cv2.VideoCapture(self.config.CAMERA_INDEX)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.CAMERA_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.CAMERA_HEIGHT)
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            self._hands.close()
            self._hands = None
            raise RuntimeError(f"Could not open camera index {self.config.CAMERA_INDEX}")

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="HandTracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._hands is not None:
            self._hands.close()
            self._hands = None

    def get_state(self) -> HandState:
        with self._lock:
            return replace(self._state)

    def get_debug_frame(self) -> np.ndarray | None:
        with self._lock:
            return None if self._debug_frame is None else self._debug_frame.copy()

    def _run_loop(self) -> None:
        while self._running:
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.01)
                continue

            if self.config.MIRROR_FRAME:
                frame = self._cv2.flip(frame, 1)

            rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self._hands.process(rgb)
            rgb.flags.writeable = True

            state = self._process_results(results, time.monotonic())
            debug = self._draw_debug(frame, state)

            with self._lock:
                self._state = state
                self._debug_frame = debug

    def _process_results(self, results: Any, now: float) -> HandState:
        free_hand = self._select_free_hand(results)
        if free_hand is None:
            beat = self._beat_tracker.update(now, None)
            self._latest_landmarks = None
            return replace(
                self._state,
                detected=False,
                bpm=beat.bpm,
                beat_just_fired=False,
            )

        landmarks_obj, handedness = free_hand
        landmarks = [(lm.x, lm.y) for lm in landmarks_obj.landmark]
        wrist = landmarks[0]
        if self._position_initialized:
            alpha = self.config.POSITION_EMA_ALPHA
            self._position = (
                alpha * wrist[0] + (1.0 - alpha) * self._position[0],
                alpha * wrist[1] + (1.0 - alpha) * self._position[1],
            )
        else:
            self._position = wrist
            self._position_initialized = True

        fingers = count_extended_fingers(landmarks, handedness)
        selection_fingers = count_extended_non_thumb_fingers(landmarks)
        pose = self._pose_debouncer.update(classify_pose(fingers), now)
        self._zone_selector.update(self._position)
        target = target_from_finger_count(selection_fingers, tuple(self.config.ZONES.keys()))
        beat = self._beat_tracker.update(now, self._position[1])

        self._latest_landmarks = landmarks_obj
        self._latest_connections = self._mp_hands.HAND_CONNECTIONS
        return HandState(
            detected=True,
            position=self._position,
            pose=pose,
            fingers_extended=fingers,
            targeted_section=target,
            selection_locked=False,
            bpm=beat.bpm,
            beat_just_fired=beat.beat_just_fired,
        )

    def _select_free_hand(self, results: Any) -> tuple[Any, str] | None:
        if not results.multi_hand_landmarks or not results.multi_handedness:
            return None

        free_hand_label = "Left" if self.config.DOMINANT_HAND == "Right" else "Right"
        for landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
            label = handedness.classification[0].label
            if label == free_hand_label:
                return landmarks, label
        return None

    def _draw_debug(self, frame: np.ndarray, state: HandState) -> np.ndarray:
        debug = frame.copy()
        height, width = debug.shape[:2]
        self._draw_zones(debug, state)
        if state.detected and self._latest_landmarks is not None:
            color = _pose_color_bgr(state.pose)
            specs = self._mp_drawing.DrawingSpec(color=color, thickness=2, circle_radius=3)
            self._mp_drawing.draw_landmarks(
                debug,
                self._latest_landmarks,
                self._latest_connections,
                specs,
                specs,
            )
            y = int(state.position[1] * height)
            self._cv2.line(debug, (0, y), (width, y), (255, 255, 255), 1)
        self._draw_status_panel(debug, state)
        return debug

    def _draw_zones(self, frame: np.ndarray, state: HandState) -> None:
        overlay = frame.copy()
        height, width = frame.shape[:2]
        for name, (x, y, zone_w, zone_h) in self.config.ZONES.items():
            p1 = (int(x * width), int(y * height))
            p2 = (int((x + zone_w) * width), int((y + zone_h) * height))
            active = state.targeted_section in (name, "all")
            color = (70, 210, 255) if active else (80, 120, 160)
            self._cv2.rectangle(overlay, p1, p2, color, -1)
            self._cv2.rectangle(frame, p1, p2, color, 2 if active else 1)
            self._cv2.putText(frame, name, (p1[0] + 8, p1[1] + 24), self._cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        self._cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    def _draw_status_panel(self, frame: np.ndarray, state: HandState) -> None:
        lines = [
            f"Detected: {'yes' if state.detected else 'no'}",
            f"Pose: {state.pose}",
            f"Fingers: {state.fingers_extended}",
            f"Targeted: {state.targeted_section or 'none'}",
            f"Locked: {'yes' if state.selection_locked else 'no'}",
            f"BPM: {'--' if state.bpm is None else f'{state.bpm:.1f}'}",
            f"Beat: {'*' if state.beat_just_fired else 'o'}",
        ]
        x, y = 18, 28
        panel_w = 280
        panel_h = 34 + len(lines) * 28
        self._cv2.rectangle(frame, (10, 10), (10 + panel_w, 10 + panel_h), (20, 20, 20), -1)
        self._cv2.rectangle(frame, (10, 10), (10 + panel_w, 10 + panel_h), (230, 230, 230), 1)
        for index, line in enumerate(lines):
            self._cv2.putText(
                frame,
                line,
                (x, y + index * 28),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (245, 245, 245),
                2,
            )


def _load_runtime_dependencies() -> tuple[Any, Any]:
    try:
        mp = importlib.import_module("mediapipe")
        cv2 = importlib.import_module("cv2")
    except ImportError as exc:
        raise RuntimeError(
            "HandTracker requires opencv-python and mediapipe. "
            "Install them with `pip install -r requirements.txt` or see hand_tracking/README.md."
        ) from exc
    return cv2, mp


def _pose_color_bgr(pose: str) -> tuple[int, int, int]:
    return {
        "pointing": (0, 180, 0),
        "fist": (0, 0, 230),
        "open": (0, 190, 255),
        "ambiguous": (150, 150, 150),
    }.get(pose, (150, 150, 150))
