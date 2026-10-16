from datetime import datetime, timedelta, timezone
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_logs import collect, failed
from log_analysis import analyze, read_logs, scene_name


def row(second=0, **fields):
    result = {'time': (datetime(2026, 10, 16, tzinfo=timezone.utc) + timedelta(seconds=second)).isoformat(),
              'seq': second + 1, 'session': 'session', 'build': 'new', 'episode': 'default',
              'event': 'position_sample', 'level': 'info', 'mode': 'explore', 'scene': 'adv_motel.scene',
              'player': 'Lee', 'camera': 'navcam', 'actual_camera': 'navcam', 'frame': second * 60,
              'player_x': 0, 'player_y': 0, 'player_z': 0,
              'camera_x': 0, 'camera_y': 1.7, 'camera_z': 0,
              'author_x': 2, 'author_y': 3, 'author_z': -5,
              'navigate': True, 'enabled': True}
    result.update(fields)
    return result


class ReadLogsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, content):
        (self.root / 'sample.jsonl').write_text(content, encoding='utf-8')
        return read_logs(self.root)

    def test_incomplete_final_append_is_not_reported_as_corruption(self):
        report = self.write(json.dumps(row()) + '\n{"session":"s",')
        self.assertEqual(len(report['rows']), 1)
        self.assertEqual(report['malformed_log_lines'], [])
        self.assertEqual(report['partial_log_lines'][0]['kind'], 'partial_final_line')

    def test_valid_unterminated_record_is_preserved(self):
        report = self.write(json.dumps(row()))
        self.assertEqual(len(report['rows']), 1)
        self.assertFalse(report['partial_log_lines'])

    def test_corruption_between_good_rows_does_not_lose_following_records(self):
        report = self.write(json.dumps(row()) + '\n{broken}\n' + json.dumps(row(2)) + '\n')
        self.assertEqual(len(report['rows']), 2)
        self.assertEqual(report['malformed_log_lines'][0]['line'], 2)
        self.assertEqual(report['malformed_log_lines'][0]['builds'], ['new'])

    def test_nonobject_invalid_time_bad_sequence_and_nonfinite_json_are_recorded(self):
        report = self.write('\n'.join(json.dumps(value) for value in
            ([], row(time='not-a-time'), row(seq=[]), row(frame='1'), row(camera=[]), row(camera_x=float('nan')))) + '\n')
        self.assertEqual(len(report['malformed_log_lines']), 6)
        self.assertEqual(report['rows'], [])

    def test_timezone_sort_is_chronological(self):
        report = self.write(json.dumps(row(0, time='2026-10-16T02:00:00+02:00')) + '\n' +
                            json.dumps(row(1, time='2026-10-16T00:00:01Z')))
        self.assertEqual([r['seq'] for r in report['rows']], [1, 2])


class BehaviorTests(unittest.TestCase):
    def findings(self, rows):
        return analyze(rows)['behavioral_findings']

    def test_story_scene_missing_actor_is_reported_with_evidence(self):
        rows = [row(0, event='adapter_waiting', reason='player', player='none', scene='none',
                    bottom_scene='adv_savannahStreets', mode='inactive')]
        rows += [row(t, event='heartbeat', player='none', scene='none',
                     bottom_scene='adv_savannahStreets', mode='inactive') for t in (10, 20, 30)]
        finding = self.findings(rows)[0]
        self.assertEqual(finding['code'], 'adapter_wait_prolonged')
        self.assertEqual(finding['duration_seconds'], 30)
        self.assertEqual(finding['frames_advanced'], 1800)
        self.assertEqual(finding['scene'], 'adv_savannahstreets')
        self.assertEqual(finding['severity'], 'review')

    def test_menu_wait_and_short_loading_wait_are_not_flagged(self):
        rows = [row(t, event='heartbeat', player='none', mode='inactive', scene='ui_menu.scene') for t in (0, 10, 20)]
        rows += [row(30, event='adapter_waiting', reason='player', player='none', mode='inactive'),
                 row(35, event='player_attached')]
        self.assertFalse(self.findings(rows))

    def test_camera_wait_tracks_live_heartbeats_even_with_a_valid_actor(self):
        rows = [row(0, event='adapter_waiting', reason='camera', camera='none')]
        rows += [row(t, event='heartbeat', camera='none') for t in (10, 20)]
        finding = self.findings(rows)[0]
        self.assertEqual(finding['reason'], 'camera')
        self.assertEqual(finding['duration_seconds'], 20)

    def test_manual_disable_ends_adapter_wait(self):
        rows = [row(0, event='adapter_waiting', reason='camera', camera='none'),
                row(10, event='heartbeat', camera='none', enabled=False),
                row(40, event='heartbeat', camera='none', enabled=False)]
        self.assertFalse(self.findings(rows))

    def test_resumed_actor_ends_wait_and_does_not_absorb_later_heartbeats(self):
        rows = [row(0, event='adapter_waiting', reason='player', player='none'),
                row(5, event='adapter_resumed'), row(50, event='heartbeat')]
        self.assertFalse(self.findings(rows))

    def test_remote_station_and_authored_alt_view_are_expected(self):
        rows = [row(t, mode='station', camera_z=-30, author_z=-30, camera_x=2, camera_y=3) for t in (0, 2, 4)]
        rows += [row(6, camera_z=-30, author_z=-30, camera_x=2, camera_y=3)]
        self.assertFalse(self.findings(rows))

    def test_station_position_mismatch_requires_repeated_evidence(self):
        self.assertFalse(self.findings([row(mode='station')]))
        found = self.findings([row(t, mode='station') for t in (0, 2)])
        self.assertEqual([f['code'] for f in found], ['authored_view_position_mismatch'])
        self.assertGreater(found[0]['max_distance_m'], 5)

    def test_movement_without_translation_is_only_a_reproduction_candidate(self):
        found = self.findings([row(t, w=True) for t in (0, 2, 4, 6)])
        self.assertEqual([f['code'] for f in found], ['movement_without_translation'])
        self.assertIn('wall', found[0]['message'])
        self.assertEqual(found[0]['severity'], 'review')

    def test_movement_samples_require_consistent_direction_and_continuous_context(self):
        for rows in ([row(t, w=True, s=True) for t in (0, 2, 4, 6)],
                     [row(t, w=True, player_z=t, camera_z=t) for t in (0, 2, 4, 6)],
                     [row(t, w=True) for t in (0, 2, 4)] + [row(5, mode='cinematic')] + [row(6, w=True)],
                     [row(t, w=True) for t in (0, 2, 10, 12)]):
            with self.subTest(rows=rows):
                self.assertFalse(self.findings(rows))

    def test_stale_camera_and_wrong_active_camera_have_distinct_evidence(self):
        found = self.findings([row(camera_x=30, actual_camera='different')])
        self.assertEqual({f['code'] for f in found}, {'remote_actor_camera', 'active_camera_mismatch'})

    def test_fixture_motion_does_not_become_gameplay_findings(self):
        self.assertFalse(self.findings([row(t, player='twd_fp_test_player', w=True) for t in (0, 2, 4, 6)]))

    def test_actor_and_camera_displacement_is_reported_without_claiming_instant_teleport(self):
        found = self.findings([row(0), row(2, player_x=16, camera_x=16)])
        self.assertEqual([f['code'] for f in found], ['large_sampled_actor_motion'])
        self.assertEqual(found[0]['actor_distance_m'], 16)
        self.assertEqual(found[0]['camera_distance_m'], 16)
        self.assertEqual(found[0]['frame_gap'], 120)
        self.assertIn('not proof', found[0]['message'])
        self.assertIn('individual-frame', found[0]['sampling_caveat'])
        self.assertEqual(found[0]['severity'], 'review')

    def test_camera_motion_without_actor_is_distinguished(self):
        found = self.findings([row(0), row(2, camera_x=16)])
        movement = next(f for f in found if f['code'] == 'camera_displacement_without_actor')
        self.assertEqual(movement['actor_distance_m'], 0)
        self.assertEqual(movement['camera_distance_m'], 16)

    def test_authored_station_and_explicit_fallback_motion_do_not_flag_teleport(self):
        for mode, policy in [('station', 'authored'), ('cinematic', 'authored'), ('cinematic', 'authored_fallback')]:
            rows = [row(t, mode=mode, camera_policy=policy, author_x=t*5,
                        camera_x=t*5, camera_y=3, camera_z=-5) for t in (0, 2)]
            with self.subTest(mode=mode):
                self.assertFalse(self.findings(rows))

    def test_motion_across_a_scene_boundary_or_long_sample_gap_is_not_flagged(self):
        for last in (row(2, scene='adv_other.scene', player_x=16, camera_x=16),
                     row(10, player_x=16, camera_x=16)):
            with self.subTest(last=last):
                self.assertFalse(self.findings([row(0), last]))

    def test_one_frame_camera_activation_captures_focus_reset_evidence(self):
        rows = [row(0, seq=10, frame=100, event='camera_changed', camera='cam_carTailgate'),
                row(0, seq=11, frame=100, event='focus_changed', camera='cam_carTailgate'),
                row(0, seq=12, frame=101, event='camera_changed', camera='cam_lee_walk')]
        found = self.findings(rows)
        self.assertEqual([f['code'] for f in found], ['transient_camera_activation'])
        self.assertEqual(found[0]['activation_frames'], 1)
        self.assertEqual(found[0]['focus_changes_during_activation'], 1)
        self.assertIn('authored', found[0]['message'])

    def test_regular_shots_and_authored_station_camera_transitions_are_not_flagged(self):
        regular = [row(0, frame=1, event='camera_changed', camera='one'),
                   row(2, frame=121, event='camera_changed', camera='two')]
        station = [row(0, seq=1, frame=1, event='camera_changed', camera='one', mode='station'),
                   row(0, seq=2, frame=2, event='camera_changed', camera='two', mode='station')]
        self.assertFalse(self.findings(regular))
        self.assertFalse(self.findings(station))

    def test_missing_visibility_and_frame_motion_telemetry_is_explicit(self):
        entry = analyze([row()])['scene_diagnostics'][0]
        self.assertEqual(entry['telemetry']['player_visibility_samples'], 0)
        self.assertTrue(any('disappearing objects' in note for note in entry['telemetry']['limits']))
        self.assertTrue(any('teleports cannot be confirmed' in note for note in entry['telemetry']['limits']))

    def test_frame_motion_event_is_distinct_from_sparse_position_inference(self):
        rows = [row(0, event='camera_motion', kind='jump_held', reason='root_discontinuity',
                    root_distance=16.2, head_distance=0.05),
                row(1, event='camera_motion', kind='jump_settled', reason='root_discontinuity',
                    root_distance=16.2, head_distance=0.05, held_frames=2),
                row(1, event='camera_fallback', stage='enter', reason='actor_discontinuity')]
        report = analyze(rows)
        finding = report['behavioral_findings'][0]
        self.assertEqual(finding['code'], 'frame_camera_discontinuity')
        self.assertEqual(finding['evidence_kind'], 'frame_event')
        self.assertEqual(finding['root_distance'], 16.2)
        self.assertEqual(len(report['camera_motion_events']), 3)
        telemetry = report['scene_diagnostics'][0]['telemetry']
        self.assertEqual(telemetry['frame_motion_events'], 2)
        self.assertEqual(telemetry['camera_fallback_events'], 1)
        self.assertFalse(any('teleports cannot be confirmed' in note for note in telemetry['limits']))

    def test_invalid_motion_sample_is_reported_but_successful_recovery_is_not_an_error(self):
        report = analyze([row(0, event='camera_motion', kind='invalid_sample', reason='head_distance'),
                          row(1, event='camera_motion', kind='sample_recovered', reason='valid_transform')])
        self.assertEqual([f['code'] for f in report['behavioral_findings']], ['invalid_frame_motion_sample'])
        self.assertEqual(report['sessions']['session']['errors'], 0)

    def test_visibility_state_history_keeps_intentional_hides_as_observations(self):
        rows = [row(0, player_hidden=False),
                row(0, seq=2, event='visibility_override', agent='Doug', camera_hidden=True, exclusive=False),
                row(1, event='visibility_revoked', agent='Doug', reason='story_agenthide'),
                row(1, seq=4, event='visibility_state', agent='Doug', hidden=True, has_head=True),
                row(2, event='visibility_summary', visible_actors=3, hidden_actors=1, tracked=6,
                    overridden=0, pending=0, scanned=20, emitted=1)]
        report = analyze(rows)
        self.assertFalse(report['behavioral_findings'])
        self.assertEqual(len(report['visibility_events']), 4)
        telemetry = report['scene_diagnostics'][0]['telemetry']
        self.assertEqual(telemetry['player_visibility_samples'], 1)
        self.assertEqual(telemetry['visibility_state_samples'], 1)
        self.assertEqual(telemetry['latest_visibility_summary']['hidden_actors'], 1)
        self.assertTrue(any('intentional story actions' in note for note in telemetry['limits']))

    def test_repeated_hidden_actor_anchor_is_reported_only_for_first_person(self):
        found = self.findings([row(t, player_hidden=True, camera_policy='player_eye') for t in (0, 2)])
        self.assertEqual([f['code'] for f in found], ['hidden_actor_camera_anchor'])
        self.assertFalse(self.findings([row(0, player_hidden=True)]))
        authored = [row(t, player_hidden=True, camera_policy='authored', camera_x=2, camera_y=3,
                        camera_z=-5) for t in (0, 2)]
        self.assertFalse(self.findings(authored))

    def test_camera_only_body_hide_is_not_treated_as_an_offstage_avatar(self):
        intentional = [row(t, player_hidden=True, player_camera_hidden=True,
                           camera_policy='player_eye') for t in (0, 2, 4)]
        self.assertFalse(self.findings(intentional))
        # A camera-only hide also ends an earlier unconfirmed story-hidden run.
        mixed = [row(0, player_hidden=True, player_camera_hidden=False),
                 row(2, player_hidden=True, player_camera_hidden=True),
                 row(4, player_hidden=True, player_camera_hidden=False)]
        self.assertFalse(self.findings(mixed))

    def test_native_fixture_visibility_events_do_not_count_as_gameplay(self):
        report = analyze([row(0, event='visibility_summary', player='twd_fp_test_player', scanned=20)])
        self.assertFalse(report['visibility_events'])
        self.assertFalse(report['scene_diagnostics'])

    def test_eye_target_error_tracks_first_person_and_excludes_authored_fallback(self):
        rows = [row(0, eye_target_x=0, eye_target_y=1.7, eye_target_z=0.1, motion_state='tracking'),
                row(2, camera_policy='authored_fallback', camera_x=2, camera_y=3, camera_z=-5,
                    eye_target_x=0, eye_target_y=1.7, eye_target_z=0, motion_state='fallback')]
        telemetry = analyze(rows)['scene_diagnostics'][0]['telemetry']
        self.assertEqual(telemetry['max_eye_target_error_m'], 0.1)
        self.assertEqual(telemetry['motion_states'], {'tracking': 1, 'fallback': 1})

    def test_scene_vm_close_is_distinct_from_a_process_exit(self):
        report = analyze([row(event='scene_close')])
        self.assertEqual(report['sessions']['session']['closure'], 'scene_transition')
        self.assertFalse(report['sessions']['session']['clean_exit'])
        self.assertEqual(analyze([row()])['sessions']['session']['closure'], 'end_not_observed')
        self.assertEqual(analyze([row(event='session_end')])['sessions']['session']['closure'], 'session_end')


class CollectionTests(unittest.TestCase):
    def test_collection_handles_old_corruption_live_tail_and_missing_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / 'build/logs'
            logs.mkdir(parents=True)
            (root / 'build/build-manifest.json').write_text(json.dumps([{'build': 'new'}]))
            (logs / 'old.jsonl').write_text(json.dumps(row(build='old')) + '\n{bad}\n')
            (logs / 'new.jsonl').write_text(json.dumps(row()) + '\n{"unfinished"')
            with contextlib.redirect_stdout(io.StringIO()):
                report = collect(query_windows=False, root=root)
            self.assertFalse(report['malformed_log_lines'])
            self.assertEqual(len(report['partial_log_lines']), 1)
            self.assertFalse(report['windows_query_performed'])
            self.assertIn('scene_coverage_error', report)
            self.assertFalse(failed(report))
            self.assertTrue((root / 'build/diagnostics.json').exists())

    def test_invalid_since_is_rejected_before_any_windows_query(self):
        with self.assertRaisesRegex(ValueError, 'ISO timestamp'):
            collect("'; dangerous", query_windows=False)

    def test_scene_normalization_accepts_resource_and_handle_forms(self):
        self.assertEqual(scene_name('Pack\\default\\Adv_SavannahStreets.scene'), 'adv_savannahstreets')
        self.assertEqual(scene_name('adv_savannahstreets'), 'adv_savannahstreets')
        self.assertEqual(scene_name('none'), '')
