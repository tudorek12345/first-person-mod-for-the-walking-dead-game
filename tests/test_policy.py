from pathlib import Path
import unittest

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT / 'src/fp_policy.lua').read_text())
        self.policy = self.lua.globals().FP_Policy

    def context(self, **flags):
        return self.policy.context(self.lua.table_from({'main': True, **flags}))

    def look(self, context, **flags):
        return self.policy.mouse_look(context, self.lua.table_from(flags))

    def test_resource_and_bare_scene_names_have_same_identity(self):
        for name in ['adv_savannahStreets', 'ADV_SAVANNAHSTREETS.scene',
                     'Pack/WalkingDead104/adv_savannahstreets.scene',
                     r'Pack\WalkingDead104\adv_savannahstreets']:
            self.assertEqual(self.policy.scene_name(name), 'adv_savannahstreets.scene')

    def test_empty_scene_identity_does_not_become_a_resource(self):
        for name in [None, '', 'none', 'NONE', '/', '\\']:
            self.assertEqual(self.policy.scene_name(name), 'none')

    def test_presentation_recognition_does_not_match_story_scenes(self):
        for name in ['adv_previouslyOn104', 'adv_nexttimeon101.scene', 'ui_closingcredits']:
            self.assertTrue(self.policy.presentation(name))
        for name in ['adv_traintilestation.scene', 'adv_savannahstreets', 'adv_previouslyon104_extra']:
            self.assertFalse(self.policy.presentation(name))

    def test_pause_overrides_all_play_modes(self):
        self.assertEqual(self.context(main=False, explore=True, combat=True, dialogue=True), 'paused')

    def test_spatial_choice_is_not_a_conversation(self):
        self.assertEqual(self.context(action_choice=True, cinematic=True), 'choice')
        self.assertEqual(self.context(direction_choice=True, explore=True), 'choice')
        self.assertEqual(self.context(dialogue=True, cinematic=True), 'dialogue')
        self.assertTrue(self.policy.authored('choice'))
        self.assertFalse(self.policy.authored('dialogue'))

    def test_native_input_modes_override_cinematic_capture(self):
        for flag, expected in [('qte', 'qte'), ('combat', 'combat'), ('peek', 'peek')]:
            self.assertEqual(self.context(**{flag: True, 'cinematic': True}), expected)

    def test_station_and_closeup_override_cinematic_and_exploration(self):
        self.assertEqual(self.context(station=True, cinematic=True, explore=True), 'station')
        self.assertEqual(self.context(closeup=True, cinematic=True, explore=True), 'closeup')

    def test_presentation_keeps_authored_anchor_despite_stale_explore_mode(self):
        self.assertEqual(self.context(presentation=True, cinematic=True, explore=True), 'presentation')
        self.assertTrue(self.policy.authored('presentation'))
        self.assertTrue(self.look('presentation', full_cutscene=True))

    def test_native_cursor_modes_never_capture_mouse(self):
        for context in ['combat', 'qte', 'choice', 'paused', 'inactive']:
            self.assertFalse(self.look(context, right=True, full_cutscene=True))

    def test_cutscene_look_requires_full_cutscene_or_explicit_drag(self):
        self.assertTrue(self.look('cinematic', full_cutscene=True))
        self.assertFalse(self.look('cinematic'))
        self.assertTrue(self.look('cinematic', right=True))
        self.assertFalse(self.look('dialogue', full_cutscene=True))

    def test_alt_always_releases_cursor(self):
        for context in ['explore', 'cinematic', 'dialogue', 'presentation', 'station']:
            self.assertFalse(self.look(context, right=True, full_cutscene=True, alt=True))

    def test_interaction_camera_drag_requires_right_button(self):
        for context in ['station', 'peek', 'closeup', 'dialogue', 'scripted']:
            self.assertFalse(self.look(context))
            self.assertTrue(self.look(context, right=True))


if __name__ == '__main__':
    unittest.main()
