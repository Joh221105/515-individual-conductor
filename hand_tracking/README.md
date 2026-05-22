# Hand Tracking Module

Webcam hand tracking for the conductor demo. The package watches the user's free hand, reports pose and section targeting, and estimates conducting BPM from vertical wrist motion. Baton gesture recognition is out of scope here and will come from an external IMU classifier.

## Install

Use Python 3.10+. A known-working setup is Python 3.11 with `mediapipe==0.10.14`, `opencv-python>=4.8`, and `numpy>=1.24`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

MediaPipe can lag newer Python releases. If install fails on Python 3.12 or 3.13, use Python 3.11.

## Run

From the repository root:

```bash
python demo.py
```

The default view hides the camera feed, starts MIDI playback, and shows a mixer-like section dashboard. Press `q` or `Esc` to quit.

Non-thumb finger counts select sections directly:

- 0 fingers / closed hand: All sections
- 1 finger: Strings
- 2 fingers: Vocals
- 3 fingers: Rhythm
- 4 fingers: Atmosphere

To show the old camera overlay for debugging:

```bash
python demo.py --camera-view
```

To run without music:

```bash
python demo.py --no-audio
```

To force a specific OpenCV camera index:

```bash
python demo.py --camera-index 0
```

To see which indexes OpenCV can open:

```bash
python demo.py --list-cameras
```

## Public API

```python
from hand_tracking import HandTracker

tracker = HandTracker()
tracker.start()
while True:
    state = tracker.get_state()
    if state.targeted_section and state.beat_just_fired:
        pass
```

`HandTracker.get_state()` returns a thread-safe `HandState` snapshot:

- `detected`: whether the free hand is visible
- `position`: normalized wrist `(x, y)`
- `pose`: `fist`, `pointing`, `open`, or `ambiguous`
- `fingers_extended`: count from 0 to 5
- `targeted_section`: zone name, `all`, or `None`
- `selection_locked`: true when pose is `fist`
- `bpm`: detected BPM, or `None` until enough beats are observed
- `beat_just_fired`: true for one frame on a beat

## Configuration

Edit `hand_tracking/config.py`:

- `DOMINANT_HAND`: hand reserved for future IMU/baton input, `"Right"` or `"Left"`; the other hand drives this module
- camera settings: `CAMERA_INDEX`, width, height, and mirroring
- MediaPipe confidence thresholds and max hand count
- smoothing and pose debounce values
- beat tracking thresholds and history length
- normalized section `ZONES` and `ZONE_HYSTERESIS`

MediaPipe handedness labels assume a mirrored camera image. The default `MIRROR_FRAME = True` makes labels behave intuitively for webcam use.

## Testing Checklist

1. Run `python demo.py` and confirm the webcam debug view appears.
2. Move the non-dominant hand around the frame and confirm the targeted section updates.
3. Make a fist and confirm the selection locks; moving the fist should not change the targeted section.
4. Open the hand fully and confirm `Targeted: all`.
5. Beat time vertically with the non-dominant hand and confirm BPM appears and stabilizes.
6. Stop beating and confirm the last BPM freezes instead of dropping to `None`.
7. Hide both hands and confirm `Detected: no`.
8. Bring only the dominant hand into frame and confirm it does not update the state.

## Known Limitations

- MediaPipe can misclassify handedness when hands cross or overlap.
- The simple finger rules assume a roughly upright hand; sideways or rotated hands can be ambiguous.
- Beat detection relies on visible, steady vertical wrist motion and waits for a down-to-up turn, so BPM updates once per beat.
- The debug display requires a local webcam and an environment that can open OpenCV windows.
