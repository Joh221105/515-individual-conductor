import unittest
from unittest.mock import patch


class HandTrackingPoseTests(unittest.TestCase):
    def test_counts_extended_fingers_and_classifies_pose(self):
        from hand_tracking.pose import classify_pose, count_extended_fingers

        landmarks = make_landmarks()
        extend_finger(landmarks, 8, 6)
        extend_finger(landmarks, 12, 10)

        self.assertEqual(count_extended_fingers(landmarks, "Left"), 2)
        self.assertEqual(classify_pose(2), "pointing")
        self.assertEqual(classify_pose(0), "fist")
        self.assertEqual(classify_pose(3), "ambiguous")
        self.assertEqual(classify_pose(5), "open")

    def test_thumb_extension_accounts_for_handedness(self):
        from hand_tracking.pose import count_extended_fingers

        left = make_landmarks()
        left[3] = (0.44, 0.58)
        left[4] = (0.34, 0.58)
        right = make_landmarks()
        right[3] = (0.56, 0.58)
        right[4] = (0.66, 0.58)

        self.assertEqual(count_extended_fingers(left, "Left"), 1)
        self.assertEqual(count_extended_fingers(right, "Right"), 1)

    def test_thumb_needs_clear_sideways_extension_to_count(self):
        from hand_tracking.pose import count_extended_fingers

        landmarks = make_landmarks()
        landmarks[3] = (0.44, 0.58)
        landmarks[4] = (0.41, 0.58)

        self.assertEqual(count_extended_fingers(landmarks, "Left"), 0)

    def test_thumb_counts_when_tip_is_clearly_farther_from_wrist(self):
        from hand_tracking.pose import count_extended_fingers

        landmarks = make_landmarks()
        landmarks[0] = (0.50, 0.80)
        landmarks[3] = (0.47, 0.62)
        landmarks[4] = (0.43, 0.52)

        self.assertEqual(count_extended_fingers(landmarks, "Left"), 1)

    def test_counts_non_thumb_fingers_for_section_selection(self):
        from hand_tracking.pose import count_extended_fingers, count_extended_non_thumb_fingers

        landmarks = make_landmarks()
        extend_finger(landmarks, 8, 6)
        landmarks[3] = (0.44, 0.58)
        landmarks[4] = (0.34, 0.58)

        self.assertEqual(count_extended_fingers(landmarks, "Left"), 2)
        self.assertEqual(count_extended_non_thumb_fingers(landmarks), 1)

    def test_pose_debouncer_requires_stable_candidate(self):
        from hand_tracking.pose import PoseDebouncer

        debouncer = PoseDebouncer(debounce_ms=150, initial_pose="fist")

        self.assertEqual(debouncer.update("pointing", now=1.00), "fist")
        self.assertEqual(debouncer.update("pointing", now=1.10), "fist")
        self.assertEqual(debouncer.update("pointing", now=1.16), "pointing")


class HandTrackingZoneTests(unittest.TestCase):
    def test_selects_zone_and_holds_current_zone_with_hysteresis(self):
        from hand_tracking.zones import ZoneSelector

        zones = {"strings": (0.05, 0.45, 0.40, 0.50), "vocals": (0.40, 0.20, 0.20, 0.35)}
        selector = ZoneSelector(zones, hysteresis=0.03)

        self.assertEqual(selector.update((0.10, 0.50)), "strings")
        self.assertEqual(selector.update((0.46, 0.50)), "strings")
        self.assertIsNone(selector.update((0.49, 0.96)))

    def test_open_pose_selects_all_and_fist_holds_previous_target(self):
        from hand_tracking.zones import update_target_for_pose

        self.assertEqual(update_target_for_pose("open", "strings", "vocals"), "all")
        self.assertEqual(update_target_for_pose("fist", "strings", "vocals"), "strings")
        self.assertEqual(update_target_for_pose("ambiguous", "strings", "vocals"), "strings")
        self.assertEqual(update_target_for_pose("pointing", "strings", "vocals"), "vocals")


class HandTrackingFingerSelectionTests(unittest.TestCase):
    def test_maps_finger_counts_to_ordered_sections(self):
        from hand_tracking.selection import target_from_finger_count

        sections = ("strings", "vocals", "rhythm", "atmosphere")

        self.assertEqual(target_from_finger_count(0, sections), "all")
        self.assertEqual(target_from_finger_count(1, sections), "strings")
        self.assertEqual(target_from_finger_count(2, sections), "vocals")
        self.assertEqual(target_from_finger_count(3, sections), "rhythm")
        self.assertEqual(target_from_finger_count(4, sections), "atmosphere")
        self.assertEqual(target_from_finger_count(5, sections), "all")


class HandTrackingBeatTests(unittest.TestCase):
    def test_detects_down_to_up_turnaround_as_beat_and_computes_bpm(self):
        from hand_tracking.beat import BeatTracker

        tracker = BeatTracker(
            min_interval_s=0.3,
            max_interval_s=1.5,
            min_swing_distance=0.05,
            history_length=4,
            timeout_s=2.0,
        )

        self.assertFalse(tracker.update(0.0, 0.20).beat_just_fired)
        self.assertFalse(tracker.update(0.2, 0.40).beat_just_fired)
        self.assertTrue(tracker.update(0.6, 0.30).beat_just_fired)
        self.assertIsNone(tracker.bpm)

        self.assertFalse(tracker.update(1.0, 0.55).beat_just_fired)
        event = tracker.update(1.2, 0.48)

        self.assertTrue(event.beat_just_fired)
        self.assertAlmostEqual(tracker.bpm, 100.0)
        self.assertEqual(tracker.update(4.0, 0.47).bpm, 100.0)


class HandTrackingPublicApiTests(unittest.TestCase):
    def test_package_exports_tracker_and_state_without_optional_import_failure(self):
        from hand_tracking import HandState, HandTracker

        state = HandState(
            detected=False,
            position=(0.0, 0.0),
            pose="ambiguous",
            fingers_extended=0,
            targeted_section=None,
            selection_locked=False,
            bpm=None,
            beat_just_fired=False,
        )

        self.assertFalse(state.detected)
        self.assertTrue(hasattr(HandTracker, "start"))

    def test_demo_config_override_sets_camera_index_without_mutating_defaults(self):
        import hand_tracking.config as defaults
        from hand_tracking.demo import make_config

        config = make_config(camera_index=2)

        self.assertEqual(config.CAMERA_INDEX, 2)
        self.assertEqual(defaults.CAMERA_INDEX, 0)

    def test_dashboard_renders_status_view_without_camera_pixels(self):
        from hand_tracking.dashboard import render_dashboard
        from hand_tracking.tracker import HandState

        frame = render_dashboard(
            HandState(
                detected=True,
                position=(0.25, 0.50),
                pose="pointing",
                fingers_extended=2,
                targeted_section="strings",
                selection_locked=False,
                bpm=120.0,
                beat_just_fired=True,
            ),
            {"strings": (0.05, 0.45, 0.40, 0.50)},
            size=(640, 360),
        )

        self.assertEqual(frame.shape, (360, 640, 3))
        self.assertGreater(frame.sum(), 0)

    def test_runtime_dependency_loader_checks_mediapipe_before_cv2(self):
        from hand_tracking.tracker import _load_runtime_dependencies

        imported = []

        def import_module(name):
            imported.append(name)
            if name == "mediapipe":
                raise ImportError("missing mediapipe")
            return object()

        with patch("hand_tracking.tracker.importlib.import_module", side_effect=import_module):
            with self.assertRaises(RuntimeError):
                _load_runtime_dependencies()

        self.assertEqual(imported, ["mediapipe"])

    def test_start_raises_runtime_error_when_camera_cannot_open(self):
        from hand_tracking.demo import make_config
        from hand_tracking.tracker import HandTracker

        released = []
        closed = []

        class ClosedCapture:
            def set(self, *_args):
                pass

            def isOpened(self):
                return False

            def read(self):
                return False, None

            def release(self):
                released.append(True)

        class FakeCv2:
            CAP_PROP_FRAME_WIDTH = 3
            CAP_PROP_FRAME_HEIGHT = 4

            @staticmethod
            def VideoCapture(_index):
                return ClosedCapture()

        class FakeHandsInstance:
            def close(self):
                closed.append(True)

        class FakeHandsModule:
            HAND_CONNECTIONS = ()

            @staticmethod
            def Hands(**_kwargs):
                return FakeHandsInstance()

        class FakeSolutions:
            drawing_utils = object()
            hands = FakeHandsModule

        class FakeMediapipe:
            solutions = FakeSolutions

        tracker = HandTracker(make_config(camera_index=9))

        with patch("hand_tracking.tracker._load_runtime_dependencies", return_value=(FakeCv2, FakeMediapipe)):
            with self.assertRaisesRegex(RuntimeError, "camera index 9"):
                tracker.start()

        self.assertFalse(tracker._running)
        self.assertEqual(released, [True])
        self.assertEqual(closed, [True])


def make_landmarks():
    landmarks = [(0.5, 0.8) for _ in range(21)]
    for tip, joint in ((8, 6), (12, 10), (16, 14), (20, 18)):
        landmarks[joint] = (0.5, 0.55)
        landmarks[tip] = (0.5, 0.70)
    landmarks[2] = (0.50, 0.60)
    landmarks[3] = (0.50, 0.60)
    landmarks[4] = (0.50, 0.60)
    return landmarks


def extend_finger(landmarks, tip, joint):
    landmarks[joint] = (landmarks[joint][0], 0.55)
    landmarks[tip] = (landmarks[tip][0], 0.35)


if __name__ == "__main__":
    unittest.main()
