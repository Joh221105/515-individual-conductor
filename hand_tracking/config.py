"""Editable configuration for the hand tracking module."""

# Which hand is reserved for future IMU/baton input. The other hand is tracked.
DOMINANT_HAND = "Right"

# Camera
CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
MIRROR_FRAME = True

# Detection
MIN_DETECTION_CONFIDENCE = 0.7
MIN_TRACKING_CONFIDENCE = 0.7
MAX_NUM_HANDS = 2

# Smoothing
POSITION_EMA_ALPHA = 0.5
POSE_DEBOUNCE_MS = 150

# Beat tracking
MIN_BEAT_INTERVAL_S = 0.3
MAX_BEAT_INTERVAL_S = 1.5
MIN_SWING_DISTANCE = 0.05
BEAT_HISTORY_LENGTH = 4
BEAT_TIMEOUT_S = 2.0

# Section zones: (x, y, width, height) in normalized coordinates.
ZONES = {
    "strings": (0.05, 0.45, 0.40, 0.50),
    "vocals": (0.40, 0.20, 0.20, 0.35),
    "rhythm": (0.60, 0.55, 0.35, 0.40),
    "atmosphere": (0.30, 0.05, 0.40, 0.20),
}

ZONE_HYSTERESIS = 0.03
