from pathlib import Path
import unittest

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT / 'src/fp_motion.lua').read_text())
        self.motion = self.lua.globals().FP_Motion
        self.state = self.motion.new()
        self.frame = 0

    def update(self, eye=(0, 1.6, 0), root=(0, 0, 0), dt=1/60,
               identity='scene/Lee', authored=False, frame=None, **config):
        def vector(values):
            return self.lua.table_from(dict(zip(('x', 'y', 'z'), values)))
        sample = self.lua.table_from({'eye': vector(eye), 'root': vector(root),
                                      'identity': identity, 'authored': authored})
        if frame is None:
            self.frame += 1
            frame = self.frame
        result = self.motion.update(self.state, sample, dt, frame, self.lua.table_from(config))
        position, event = result if isinstance(result, tuple) else (result, None)
        return position, event

    def test_player_root_translation_has_no_lag(self):
        self.update()
        pos, _ = self.update(eye=(.2, 1.6, 0), root=(.2, 0, 0))
        self.assertAlmostEqual(pos.x, .2)

    def test_small_head_jitter_is_attenuated(self):
        self.update()
        pos, _ = self.update(eye=(0, 1.65, 0))
        self.assertGreater(pos.y, 1.6)
        self.assertLess(pos.y, 1.63)

    def test_same_frame_does_not_advance_filter_or_emit_event_twice(self):
        self.update()
        first, _ = self.update(eye=(0, 1.7, 0), frame=2)
        second, event = self.update(eye=(0, 1.7, 0), frame=2)
        self.assertEqual(first.y, second.y)
        self.assertIsNone(event)

    def test_smoothed_result_is_consistent_across_frame_rates(self):
        final = []
        for fps in (30, 60, 144):
            self.motion.reset(self.state)
            self.update()
            for _ in range(fps):
                pos, _ = self.update(eye=(0, 1.7, 0), dt=1/fps)
            final.append(pos.y)
        self.assertLess(max(final)-min(final), 1e-7)

    def test_fast_pose_change_lag_is_bounded(self):
        self.update()
        pos, _ = self.update(eye=(0, 1.1, 0))
        self.assertLessEqual(abs(pos.y-1.1), .120001)

    def test_one_frame_head_outlier_does_not_move_camera(self):
        self.update()
        pos, event = self.update(eye=(0, .4, 0))
        self.assertAlmostEqual(pos.y, 1.6)
        self.assertEqual(event.kind, 'jump_held')
        pos, event = self.update()
        self.assertAlmostEqual(pos.y, 1.6)
        self.assertEqual(event.kind, 'jump_rejected')

    def test_bad_head_frame_does_not_block_valid_root_movement(self):
        self.update()
        pos, _ = self.update(eye=(.1, .4, 0), root=(.1, 0, 0))
        self.assertAlmostEqual(pos.x, .1)
        self.assertAlmostEqual(pos.y, 1.6)

    def test_one_frame_root_outlier_is_rejected(self):
        self.update()
        pos, event = self.update(eye=(30, 1.6, 0), root=(30, 0, 0))
        self.assertEqual(pos.x, 0)
        self.assertEqual(event.kind, 'jump_held')
        pos, event = self.update()
        self.assertEqual(pos.x, 0)
        self.assertEqual(event.kind, 'jump_rejected')

    def test_sustained_teleport_settles_without_sweeping(self):
        self.update()
        samples = []
        for _ in range(10):
            pos, event = self.update(eye=(30, 1.6, 0), root=(30, 0, 0))
            samples.append(pos.x)
            if event and event.kind == 'jump_settled':
                self.assertLessEqual(event.held_seconds, .1)
                break
        self.assertEqual(samples[-1], 30)
        self.assertTrue(all(value in (0, 30) for value in samples))

    def test_slow_frame_still_requires_second_sample_before_teleport(self):
        self.update()
        pos, _ = self.update(eye=(30, 1.6, 0), root=(30, 0, 0), dt=1)
        self.assertEqual(pos.x, 0)
        pos, event = self.update(eye=(30, 1.6, 0), root=(30, 0, 0), dt=1)
        self.assertEqual(pos.x, 30)
        self.assertEqual(event.kind, 'jump_settled')

    def test_authored_station_cuts_are_immediate_even_in_same_frame(self):
        self.update()
        pos, _ = self.update(eye=(30, 3, 0), authored=True, frame=1)
        self.assertEqual(pos.x, 30)
        pos, _ = self.update(eye=(-50, 6, 4), authored=True, frame=1)
        self.assertEqual(pos.x, -50)
        pos, _ = self.update(frame=1)
        self.assertEqual(pos.x, 0)

    def test_player_identity_change_resets_without_using_other_actors_history(self):
        self.update()
        pos, event = self.update(eye=(30, 1, 0), root=(30, 0, 0), identity='scene/Clementine')
        self.assertEqual(pos.x, 30)
        self.assertEqual(event.kind, 'reset')

    def test_invalid_transforms_preserve_last_good_pose_and_report_once(self):
        self.update()
        pos, event = self.update(root=(float('nan'), 0, 0))
        self.assertAlmostEqual(pos.y, 1.6)
        self.assertEqual(event.kind, 'invalid_sample')
        _, event = self.update(root=(float('nan'), 0, 0))
        self.assertIsNone(event)
        _, event = self.update()
        self.assertEqual(event.kind, 'sample_recovered')

    def test_unreasonable_head_distance_cannot_enter_smoothing_history(self):
        self.update()
        pos, event = self.update(eye=(0, 50, 0))
        self.assertAlmostEqual(pos.y, 1.6)
        self.assertEqual(event.reason, 'head_distance')

    def test_reset_discards_pending_failure_and_frame_cache(self):
        self.update()
        self.update(eye=(30, 1.6, 0), root=(30, 0, 0))
        self.motion.reset(self.state)
        pos, event = self.update(eye=(30, 1.6, 0), root=(30, 0, 0), frame=1)
        self.assertEqual(pos.x, 30)
        self.assertEqual(event.kind, 'reset')

    def test_alternating_destinations_never_confirm_even_after_elapsed_window(self):
        for fps in (20, 60):
            self.motion.reset(self.state)
            self.update()
            events = []
            for i in range(fps):
                x = 20 if i % 2 == 0 else 35
                pos, event = self.update(eye=(x, 1.6, 0), root=(x, 0, 0), dt=1/fps)
                self.assertEqual(pos.x, 0)
                if event:
                    events.append(event.kind)
            self.assertEqual(events, ['jump_held'])
            self.assertIsNotNone(self.state.pending)
            self.assertEqual(self.state.pending.resets, fps-1)

    def test_destination_change_restarts_confirmation_timer(self):
        self.update()
        for _ in range(4):
            self.update(eye=(20, 1.6, 0), root=(20, 0, 0), dt=1/60)
        pos, event = self.update(eye=(35, 1.6, 0), root=(35, 0, 0), dt=1/60)
        self.assertEqual(pos.x, 0)
        self.assertIsNone(event)
        self.assertEqual(self.state.pending.frames, 1)
        for _ in range(4):
            pos, event = self.update(eye=(35, 1.6, 0), root=(35, 0, 0), dt=1/60)
        self.assertEqual(pos.x, 35)
        self.assertEqual(event.kind, 'jump_settled')
        self.assertEqual(event.candidate_resets, 1)
        self.assertEqual(event.held_frames, 9)
        self.assertEqual(event.confirmation_frames, 5)
        self.assertGreater(event.held_seconds, event.confirmation_seconds)

    def test_head_offset_changes_cannot_reuse_old_root_confirmation(self):
        self.update()
        for _ in range(4):
            self.update(eye=(20, 1.6, 0), root=(20, 0, 0), dt=1/60)
        pos, _ = self.update(eye=(20, .5, 0), root=(20, 0, 0), dt=1/60)
        self.assertEqual(pos.x, 0)
        self.assertEqual(self.state.pending.frames, 1)
        self.assertEqual(self.state.pending.resets, 1)

    def test_invalid_interval_breaks_consecutive_destination_evidence(self):
        self.update()
        for _ in range(4):
            self.update(eye=(20, 1.6, 0), root=(20, 0, 0), dt=1/60)
        self.update(eye=(20, 1.6, 0), root=(float('nan'), 0, 0), dt=1/60)
        pos, event = self.update(eye=(20, 1.6, 0), root=(20, 0, 0), dt=1/60)
        self.assertEqual(pos.x, 0)
        self.assertIsNone(event)
        self.assertEqual(self.state.pending.frames, 1)
        self.assertEqual(self.state.pending.resets, 1)

    def test_consistent_walking_at_new_destination_can_settle(self):
        for fps in (20, 60):
            self.motion.reset(self.state)
            self.update()
            settled = None
            for i in range(fps):
                x = 20 + i * 3/fps
                pos, event = self.update(eye=(x, 1.6, 0), root=(x, 0, 0), dt=1/fps)
                if event and event.kind == 'jump_settled':
                    settled = event
                    self.assertAlmostEqual(pos.x, x)
                    break
            self.assertIsNotNone(settled)
            self.assertEqual(settled.candidate_resets, 0)
            self.assertLessEqual(settled.held_seconds, .1)

    def test_return_to_original_root_after_unstable_samples_rejects_pending_jump(self):
        self.update()
        for i in range(10):
            x = 20 if i % 2 == 0 else 35
            self.update(eye=(x, 1.6, 0), root=(x, 0, 0))
        pos, event = self.update()
        self.assertEqual(pos.x, 0)
        self.assertEqual(event.kind, 'jump_rejected')
        self.assertEqual(event.candidate_resets, 9)
        self.assertEqual(event.held_frames, 10)
        self.assertIsNone(self.state.pending)


if __name__ == '__main__':
    unittest.main()
