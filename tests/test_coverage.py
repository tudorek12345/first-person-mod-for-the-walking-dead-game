from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from scene_coverage import catalog, summarize


class CoverageTests(unittest.TestCase):
    def test_resource_inventory_deduplicates_translations_and_excludes_ui(self):
        scene = 'adv_motel.scene'
        manifest = {'archives': [
            {'path': 'Pack/default/data.ttarch', 'files': [scene, 'ui_menu.scene', 'adv_motel.lua']},
            {'path': 'Pack/default/translation.ttarch', 'files': [scene]},
            {'path': 'Pack/WalkingDead106/data.ttarch', 'files': [scene]},
            {'path': 'Pack/default/voice.ttarch', 'error': 'unsupported table'}]}
        rows = catalog(manifest)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['archives']), 2)

    def test_old_build_and_native_fixtures_do_not_count_as_coverage(self):
        scenes = [{'episode': 'default', 'scene': 'adv_motel.scene'}]
        base = {'episode': 'default', 'scene': 'adv_motel.scene', 'event': 'position_sample', 'time': '2026-10-16'}
        report = summarize(scenes, [dict(base, build='old'), dict(base, build='new', native_test=True)], 'new')
        self.assertEqual(report['observed'], 0)

    def test_observation_never_implies_completed_playthrough(self):
        scenes = [{'episode': 'default', 'scene': 'adv_motel.scene'}]
        row = {'episode': 'default', 'scene': 'adv_motel.scene', 'event': 'position_sample',
               'time': '2026-10-16', 'mode': 'station', 'camera': 'Station01', 'build': 'new'}
        report = summarize(scenes, [row], 'new')
        self.assertEqual(report['observed'], 1)
        self.assertEqual(report['scenes'][0]['modes'], ['station'])
        self.assertFalse(report['scenes'][0]['playthrough_verified'])

    def test_real_gameplay_in_native_test_build_counts_but_fixture_does_not(self):
        scenes = [{'episode': 'default', 'scene': 'adv_motel.scene'}]
        base = {'episode': 'default', 'scene': 'adv_motel', 'event': 'position_sample',
                'time': '2026-10-16', 'build': 'new', 'native_test': True}
        report = summarize(scenes, [dict(base, player='twd_fp_test_player'), dict(base, player='Lee')], 'new')
        self.assertEqual(report['observed'], 1)
        self.assertEqual(report['scenes'][0]['position_samples'], 1)
        self.assertEqual(report['scenes'][0]['native_test_build_gameplay_samples'], 1)

    def test_player_wait_marks_scene_seen_without_claiming_camera_coverage(self):
        scenes = [{'episode': 'WalkingDead104', 'scene': 'adv_savannahstreets.scene'}]
        report = summarize(scenes, [{'episode': 'WalkingDead104', 'scene': 'none',
            'bottom_scene': 'adv_SavannahStreets', 'event': 'adapter_waiting',
            'reason': 'player', 'build': 'new'}], 'new')
        self.assertEqual(report['observed'], 0)
        self.assertTrue(report['scenes'][0]['scene_seen'])
        self.assertEqual(report['scenes'][0]['adapter_wait_events'], 1)

    def test_catalog_accepts_absolute_archive_paths_and_case_insensitive_pack(self):
        scenes = catalog({'archives': [{'path': 'C:\\game\\PACK\\walkingdead104\\data.ttarch',
                                        'files': ['folder/ADV_MOTEL.scene']}]})
        self.assertEqual(scenes[0]['episode'], 'WalkingDead104')
        self.assertEqual(scenes[0]['scene'], 'adv_motel.scene')
