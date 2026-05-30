import unittest

from conductor_audio.mixer_ui import MixerUI


class WandGestureTests(unittest.TestCase):
    def _ui_stub(self):
        ui = type("MixerUiStub", (), {})()
        ui.hand_tracker = None
        ui.base_volumes = {
            "strings": 1.0,
            "vocals": 1.0,
            "rhythm": 1.0,
            "atmosphere": 1.0,
        }
        ui.muted = {section: False for section in ui.base_volumes}
        ui.soloed = {section: False for section in ui.base_volumes}
        ui._hand_state = MixerUI._hand_state.__get__(ui)
        ui._hand_targeted_section = MixerUI._hand_targeted_section.__get__(ui)
        ui._set_base_volume = MixerUI._set_base_volume.__get__(ui)
        ui._apply_effective_volumes = lambda: None
        ui.apply_wand_gesture = MixerUI.apply_wand_gesture.__get__(ui)
        return ui

    def test_wand_volume_gesture_applies_to_all_sections_without_hand_target(self):
        ui = self._ui_stub()

        ui.apply_wand_gesture("volume_down")

        self.assertEqual(
            ui.base_volumes,
            {
                "strings": 0.92,
                "vocals": 0.92,
                "rhythm": 0.92,
                "atmosphere": 0.92,
            },
        )


if __name__ == "__main__":
    unittest.main()
