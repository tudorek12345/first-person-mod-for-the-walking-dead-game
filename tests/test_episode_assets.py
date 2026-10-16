from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('audit_episode_assets', ROOT / 'tools/audit_episode_assets.py')
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


class EpisodeAssetTests(unittest.TestCase):
    def setUp(self):
        self.config = {'head_meshes': {'sk54_lee.prop': ['sk54_lee_head']},
                       'weapons': [{'id': 'pistol', 'props': ['gun_absent.prop', 'gun.prop'],
                                    'sound': 'gun.wav', 'flash': 'flash.prop'}]}
        self.manifest = {'archives': [
            {'path': r'Pack\default\base.ttarch',
             'files': ['SK54_LEE.prop', 'sk54_lee_head.d3dmesh', 'gun.prop', 'flash.prop',
                       'module_null.prop', 'ui_text.prop', 'sk54_clementine.prop']},
            {'path': r'Pack\default\audio.ttarch', 'error': 'index failed'},
            {'path': r'Pack\WalkingDead105\base.ttarch', 'files': ['sk54_lee.prop']},
            {'path': r'Pack\WalkingDead106\base.ttarch', 'files': ['gun.wav']},
        ]}

    def report(self):
        return assets.audit(self.manifest, self.config)

    def test_weapon_alternatives_are_checked_as_a_group(self):
        weapon = self.report()['episodes'][0]['weapons'][0]
        self.assertTrue(weapon['has_indexed_prefab_candidate'])
        self.assertEqual(weapon['candidates'][0]['status'], 'not_indexed')
        self.assertEqual(weapon['candidates'][1]['status'], 'indexed_in_episode')

    def test_other_episode_resources_do_not_count_as_local_availability(self):
        weapon = self.report()['episodes'][-1]['weapons'][0]
        self.assertFalse(weapon['has_indexed_prefab_candidate'])
        self.assertEqual(weapon['candidates'][1]['status'], 'indexed_in_other_episode_only')
        self.assertIn('default', weapon['candidates'][1]['other_episodes'])

    def test_unindexed_audio_is_reported_without_fabricating_absence(self):
        episode = self.report()['episodes'][0]
        self.assertEqual(episode['weapons'][0]['sound']['status'], 'not_indexed')
        self.assertEqual(episode['archives_not_indexed'], [r'Pack\default\audio.ttarch'])
        self.assertIn('unverified', self.report()['scope'])

    def test_head_mesh_availability_is_independent_from_prefab(self):
        head = self.report()['episodes'][-1]['head_variants'][0]
        self.assertTrue(head['applicable_to_indexed_prefab'])
        self.assertEqual(head['meshes'][0]['status'], 'indexed_in_other_episode_only')

    def test_inventory_never_claims_runtime_verification(self):
        report = self.report()
        self.assertFalse(report['runtime_verified'])
        self.assertFalse(report['episodes'][0]['weapons'][0]['flash']['runtime_verified'])

    def test_unmapped_character_variants_are_visible(self):
        episode = self.report()['episodes'][0]
        self.assertEqual(episode['unmapped_actor_prefabs'], ['sk54_clementine.prop'])

    def test_config_loader_uses_current_configuration(self):
        config = assets.load_config(ROOT / 'src/fp_config.lua')
        self.assertTrue(config['head_meshes'])
        self.assertEqual({w['id'] for w in config['weapons']}, {'pistol', 'shotgun', 'rifle'})


if __name__ == '__main__':
    unittest.main()
