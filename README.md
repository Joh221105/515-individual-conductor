# Conductor Baton

Python prototype for a conductor-baton project. The current audio app plays a MIDI arrangement through FluidSynth and exposes a pygame mixer for four orchestral sections: Strings, Vocals, Rhythm, and Atmosphere.

The MediaPipe hand-tracking module lives in `hand_tracking/` and exposes `HandTracker` for the current section-selection UI. Baton gesture recognition is expected to come from an ESP32-S3 IMU classifier in a later integration.

## Install

Requires Python 3.10+.

Install FluidSynth before installing Python packages:

```bash
# macOS
brew install fluid-synth

# Debian/Ubuntu
sudo apt update
sudo apt install fluidsynth libfluidsynth-dev
```

On Windows, install a FluidSynth binary and make sure the FluidSynth library is available on your PATH before installing Python dependencies.

Then install the Python packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The pip package name is case-sensitive in the usual docs: `pyFluidSynth`.
For the webcam hand tracker, a known-working combination is Python 3.11 with `mediapipe==0.10.14`.

## Assets

Built-in demo MIDI files and the soundfont live here:

```text
conductor_audio/assets/vivalavida_demo.mid
conductor_audio/assets/demons_demo.mid
conductor_audio/assets/titanium_demo.mid
conductor_audio/assets/FluidR3_GM.sf2
```

Optional accent samples go here. Missing samples are logged as warnings and skipped:

```text
conductor_audio/assets/accents/strings_accent.wav
conductor_audio/assets/accents/vocals_accent.wav
conductor_audio/assets/accents/rhythm_accent.wav
conductor_audio/assets/accents/atmosphere_accent.wav
```

## Run the App

Run these commands from the repository root. If you just installed the
dependencies, activate the virtual environment first:

```bash
source .venv/bin/activate
```

Start the main mixer app:

```bash
python -m conductor_audio.main
```

The app opens a song picker first. Choose Viva La Vida, Demons, or Titanium, then the mixer starts with that song's saved section mapping.

The mixer starts MIDI playback, opens the pygame mixer window, and starts hand tracking by default. Hand tracking highlights sections from non-thumb finger count: closed hand = all, 1 finger = Strings, 2 = Vocals, 3 = Rhythm, 4 = Atmosphere. The section strips are labeled 1-4 to match the gesture mapping. Thumb-only gestures control tempo: thumbs up moves to the next tempo step, thumbs down moves to the previous tempo step.

You can skip the song picker and open a built-in song directly:

```bash
python -m conductor_audio.main --song vivalavida
python -m conductor_audio.main --song demons
python -m conductor_audio.main --song titanium
```

To force a camera index or disable tracking:

```bash
python -m conductor_audio.main --camera-index 0
python -m conductor_audio.main --no-hand-tracking
```

If the wrong camera opens, list available camera indexes, then rerun the app with the index you want:

```bash
python demo.py --list-cameras
python -m conductor_audio.main --camera-index 1
```

To run the standalone hand-tracking debug display:

```bash
python demo.py
```

This opens the song picker, then a camera-hidden section status dashboard with MIDI playback. Add `--camera-view` if you need the raw webcam overlay for debugging, or `--no-audio` for tracker-only testing.

If you need to force the built-in computer camera, use:

```bash
python demo.py --camera-index 0
```

To run without the BLE wand scan, use:

```bash
python -m conductor_audio.main --no-wand
```

You can also override asset paths:

```bash
python demo.py --song titanium
python -m conductor_audio.main --midi /path/to/song.mid --soundfont /path/to/FluidR3_GM.sf2
```

For custom MIDI files, the app auto-detects the channel-to-section mapping from MIDI track names unless you pass a manual mapping file:

```bash
python -m conductor_audio.main --midi /path/to/song.mid --mapping /path/to/section_mapping.py
```

At startup the app prints the channel-to-section mapping it will use. Press `Esc` in the mixer window to quit.

## Section Mapping

Built-in demo mappings are saved in `conductor_audio/song_catalog.py`. Viva La Vida keeps the original manual mapping from `conductor_audio/section_mapping.py`; Demons and Titanium have their own adapted mappings with at least one channel in each section.

For custom MIDI files, `conductor_audio/auto_detect.py` reads MIDI track names and maps channels with fuzzy keywords:

- Strings: violin, cello, strings
- Vocals: trumpet, vocal, melody
- Rhythm: chimes, steel pans, bass guitar, percussion
- Atmosphere: echoes, synth, choir, piano, pad

If auto-detection is wrong, edit `conductor_audio/section_mapping.py`:

```python
SECTION_MAPPING = {
    "strings": [4, 5, 7],
    "vocals": [0],
    "rhythm": [1, 6, 9],
    "atmosphere": [2, 3, 8, 10],
}
```

## Mixer Controls

- Volume fader: sends MIDI CC7 to every channel in the section with a perceptual curve.
- M / S: mute and solo like a DAW.
- Tempo strip: selects one of five fixed BPM steps: 100, 120, 140, 160, or 180.

The engine API in `conductor_audio/audio_engine.py` is the future gesture integration point: `set_volume`, `set_brightness`, `set_octave`, `set_tempo`, `play_accent`, and `get_state`.

## Keyboard Shortcuts

- `1` / `2` / `3` / `4`: bump section volume up
- `Shift+1` / `Shift+2` / `Shift+3` / `Shift+4`: bump section volume down
- `+` / `-`: move to the next/previous tempo step
- `Space`: pause/resume playback
- `M` then `1` / `2` / `3` / `4`: toggle mute
- `S` then `1` / `2` / `3` / `4`: toggle solo
- `Esc`: quit

## Gesture Training Capture

The BMI270 gesture collector uses a Seeed Studio XIAO ESP32S3 with BMI270 I2C wired as:

- SDA: `D4`
- SCL: `D5`

Build and upload the firmware:

```bash
pio run -d firmware
pio run -d firmware -t upload
pio device monitor -d firmware
```

After the serial monitor prints `READY`, collect one labeled 1-second gesture sample:

```bash
python tools/collect_gesture.py --port /dev/cu.usbmodemXXXX
```

The collector asks which gesture is being captured, waits for Enter, starts after 2 seconds, and writes a CSV file with 100 samples at 100 Hz under `data/wave/<gesture>/`.

Each CSV uses:

```csv
timestamp,ax,ay,az,gx,gy,gz
```

## Tests

```bash
python -m unittest discover -s tests -p 'test*.py'
```
