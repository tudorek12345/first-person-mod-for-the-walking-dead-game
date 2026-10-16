"""Read live JSONL snapshots and describe observable camera/adapter symptoms.

Findings are diagnostics, not proof of failed story progression. In particular,
station cameras may intentionally be remote, walls may block walking, a VM may
end on a scene transition, and a live log may end halfway through an append.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import dist, isfinite
from pathlib import Path
import json


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except ValueError:
        return None


def scene_name(value):
    """Native APIs return both resource names and extensionless scene handles."""
    if not isinstance(value, str):
        return ''
    value = value.replace('\\', '/').rsplit('/', 1)[-1].lower()
    if value in ('', 'none', 'nil', 'unknown'):
        return ''
    return value[:-6] if value.endswith('.scene') else value


def row_scene(row):
    for key in ('scene', 'bottom_scene', 'opened_scene', 'detected_scene'):
        if result := scene_name(row.get(key)):
            return result
    return ''


def is_fixture(row):
    return row.get('native_fixture') is True or any(
        isinstance(row.get(key), str) and row[key].lower().startswith('twd_fp_test_')
        for key in ('player', 'camera'))


def is_gameplay_sample(row):
    if row.get('event') != 'position_sample' or is_fixture(row):
        return False
    # native_test marks the entire build, even after fixtures finish or skip.
    # Count a real attached actor, while conservatively excluding old fixture
    # records that lacked actor identity.
    return not row.get('native_test') or row.get('player') not in (None, '', 'none', 'nil')


def _reject_constant(value):
    raise ValueError('Non-finite JSON number: ' + value)


def read_logs(directory, root=None):
    """Snapshot files once; retain good rows around malformed lines.

    A broken unterminated final line is a partial append, not a proven corrupt
    log. Schema errors and terminated invalid JSON are recorded separately.
    """
    rows, malformed, partial, unreadable = [], [], [], []
    for file in sorted(Path(directory).glob('*.jsonl')):
        try:
            name = str(file.relative_to(root)) if root else str(file)
        except ValueError:
            name = str(file)
        try:
            raw = file.read_bytes()
        except OSError as exc:
            unreadable.append({'file': name, 'message': str(exc)})
            continue
        lines = raw.splitlines(keepends=True)
        file_builds = set()
        file_issues = []
        for number, raw_line in enumerate(lines, 1):
            text = raw_line.decode('utf-8-sig' if number == 1 else 'utf-8', errors='replace').strip()
            if not text:
                continue
            issue = {'file': name, 'line': number, 'text': text[:300]}
            try:
                record = json.loads(text, parse_constant=_reject_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                issue['message'] = str(exc)
                if number == len(lines) and not raw_line.endswith((b'\n', b'\r')):
                    issue['kind'] = 'partial_final_line'
                    partial.append(issue)
                else:
                    issue['kind'] = 'invalid_json'
                    malformed.append(issue)
                file_issues.append(issue)
                continue
            invalid = None
            if not isinstance(record, dict):
                invalid = 'Log record must be an object'
            elif not isinstance(record.get('session'), str) or not record['session']:
                invalid = 'Missing or invalid session identity'
            elif not isinstance(record.get('event'), str):
                invalid = 'Missing or invalid event name'
            elif timestamp(record.get('time')) is None:
                invalid = 'Missing or invalid timestamp'
            elif not isinstance(record.get('seq'), int) or isinstance(record.get('seq'), bool):
                invalid = 'Missing or invalid sequence number'
            elif any(key in record and not isinstance(record[key], str) for key in
                     ('build', 'episode', 'level', 'mode', 'scene', 'bottom_scene', 'opened_scene',
                      'detected_scene', 'camera', 'actual_camera', 'player', 'reason')):
                invalid = 'Invalid text field type'
            elif 'frame' in record and (not isinstance(record['frame'], int) or isinstance(record['frame'], bool)
                                        or record['frame'] < 0):
                invalid = 'Invalid frame count'
            if invalid:
                issue.update(kind='invalid_record', message=invalid)
                malformed.append(issue)
                file_issues.append(issue)
                continue
            record['_file'], record['_line'] = name, number
            rows.append(record)
            if isinstance(record.get('build'), str):
                file_builds.add(record['build'])
        for issue in file_issues:
            issue['builds'] = sorted(file_builds)
    rows.sort(key=lambda row: (timestamp(row['time']), row['session'], row['seq']))
    return {'rows': rows, 'malformed_log_lines': malformed,
            'partial_log_lines': partial, 'unreadable_log_files': unreadable}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _position(row, prefix):
    values = tuple(row.get(prefix + '_' + axis) for axis in 'xyz')
    return values if all(_number(v) for v in values) else None


def _reference(row):
    return {k: row[k] for k in ('_file', '_line', 'time', 'frame', 'seq', 'camera',
                              'actual_camera', 'mode', 'player', 'camera_policy') if k in row}


def _authored(row):
    policy = row.get('camera_policy')
    return ((isinstance(policy, str) and policy.startswith('authored')) or row.get('mode') in ('station', 'peek')
            or row.get('interaction_view') is True)


def _elapsed(first, last):
    a, b = timestamp(first.get('time')), timestamp(last.get('time'))
    return max(0, (b - a).total_seconds()) if a and b else 0


def analyze(rows):
    """Return deterministic, evidence-linked symptoms plus per-scene totals."""
    sessions, scenes, findings = {}, {}, []
    by_session = defaultdict(list)
    for row in rows:
        by_session[row.get('session', 'unknown')].append(row)

    def finding(code, first, last, message, **facts):
        item = {'code': code, 'severity': 'review', 'session': first.get('session'),
                'episode': first.get('episode', 'unknown'), 'scene': row_scene(first),
                'message': message, 'duration_seconds': _elapsed(first, last),
                'first': _reference(first), 'last': _reference(last)}
        item.update(facts)
        findings.append(item)

    for session, records in sorted(by_session.items()):
        records.sort(key=lambda row: (timestamp(row.get('time')) or datetime.min.replace(tzinfo=timezone.utc),
                                      row.get('seq', 0)))
        first, last = records[0], records[-1]
        ended = any(r.get('event') == 'session_end' for r in records)
        transition = any(r.get('event') == 'scene_close' for r in records)
        sessions[session] = {
            'first': first.get('time'), 'last': last.get('time'), 'records': len(records),
            'last_event': last.get('event'),
            'errors': sum(r.get('level') == 'error' for r in records),
            'warnings': sum(r.get('level') == 'warn' for r in records),
            'frames': max((r['frame'] for r in records if _number(r.get('frame'))), default=0),
            'clean_exit': ended,
            'closure': 'session_end' if ended else 'scene_transition' if transition else 'end_not_observed',
            'closure_note': 'A missing session_end is not evidence of a game crash; script VMs also end on transitions.',
            'scenes': sorted({row_scene(r) for r in records if row_scene(r)}),
            'modes': sorted({r['mode'] for r in records if isinstance(r.get('mode'), str)}),
            'builds': sorted({r['build'] for r in records if isinstance(r.get('build'), str)}),
        }
        wait_start = None
        wait_last = None

        def finish_wait():
            if wait_start is None or wait_last is None:
                return
            if _elapsed(wait_start, wait_last) >= 15 and row_scene(wait_start).startswith(('adv_', 'env_')):
                finding('adapter_wait_prolonged', wait_start, wait_last,
                        'Adapter is waiting while a story scene continues ticking. Check actor/scene identity and loading state; this does not prove progression is blocked.',
                        reason=wait_start.get('reason', 'player'),
                        frames_advanced=max(0, (wait_last.get('frame', 0) or 0) - (wait_start.get('frame', 0) or 0)))

        for row in records:
            if is_fixture(row):
                continue
            event = row.get('event')
            if event == 'camera_motion' and row.get('kind') == 'jump_held':
                facts = {key: row[key] for key in ('kind', 'reason', 'root_distance', 'head_distance') if key in row}
                finding('frame_camera_discontinuity', row, row,
                        'The frame monitor detected a discontinuous actor/root or head transform and held the eye position. The event identifies a frame discontinuity, not which chore or system caused it.',
                        evidence_kind='frame_event', **facts)
            elif event == 'camera_motion' and row.get('kind') == 'invalid_sample':
                finding('invalid_frame_motion_sample', row, row,
                        'The frame monitor rejected an invalid camera/actor transform; inspect its recovery and fallback events.',
                        reason=row.get('reason'), evidence_kind='frame_event')
            if wait_start is not None and (row.get('enabled') is False or row.get('closed') is True):
                finish_wait()
                wait_start = wait_last = None
            waiting = (event == 'adapter_waiting' or
                       (event == 'heartbeat' and row.get('mode') == 'inactive' and row.get('enabled') is True
                        and row.get('player') in (None, '', 'none') and row.get('closed') is not True))
            if waiting:
                if wait_start is not None and row_scene(wait_start) != row_scene(row):
                    finish_wait()
                    wait_start = None
                if wait_start is None:
                    wait_start = row
                wait_last = row
            elif wait_start is not None and event == 'heartbeat' and row_scene(wait_start) == row_scene(row):
                wait_last = row
            elif event in ('adapter_resumed', 'player_attached', 'session_end', 'scene_close'):
                finish_wait()
                wait_start = wait_last = None
        finish_wait()

        samples = [r for r in records if is_gameplay_sample(r)]
        hidden_run = []

        def finish_hidden():
            if len(hidden_run) >= 2:
                finding('hidden_actor_camera_anchor', hidden_run[0], hidden_run[-1],
                        'The first-person camera remained attached to an actor logged as hidden. Hidden actors can be intentionally offstage; check whether this shot needs an authored fallback.',
                        samples=len(hidden_run), evidence_kind='visibility_samples')

        for sample in samples:
            previous_hidden = hidden_run[-1] if hidden_run else None
            contiguous = (previous_hidden is None or
                          (row_scene(previous_hidden) == row_scene(sample)
                           and previous_hidden.get('player') == sample.get('player')
                           and _elapsed(previous_hidden, sample) <= 5))
            # Camera visibility rules may intentionally hide the body around a
            # first-person eye. That is distinct from a story-hidden/offstage
            # avatar and must not trigger the unsafe anchor candidate.
            hidden_offstage = sample.get('player_hidden') is True and sample.get('player_camera_hidden') is not True
            if not contiguous or not hidden_offstage or _authored(sample):
                finish_hidden()
                hidden_run = []
            if hidden_offstage and not _authored(sample):
                hidden_run.append(sample)
        finish_hidden()
        # Chores can relocate an actor between shots, even if the same camera
        # agent remains active. Sparse samples prove displacement, not an
        # instantaneous teleport or its cause. Keep those claims separate.
        for before, after in zip(samples, samples[1:]):
            gap = _elapsed(before, after)
            if not (0 < gap <= 3.5 and row_scene(before) == row_scene(after)
                    and before.get('player') == after.get('player') and not _authored(before) and not _authored(after)):
                continue
            positions = [_position(r, p) for r in (before, after) for p in ('camera', 'player')]
            if any(p is None for p in positions):
                continue
            camera_before, actor_before, camera_after, actor_after = positions
            camera_distance, actor_distance = dist(camera_before, camera_after), dist(actor_before, actor_after)
            if camera_distance < 5:
                continue
            author_before, author_after = _position(before, 'author'), _position(after, 'author')
            facts = {'camera_distance_m': round(camera_distance, 3), 'actor_distance_m': round(actor_distance, 3),
                     'evidence_kind': 'periodic_samples',
                     'frame_gap': after.get('frame', 0) - before.get('frame', 0),
                     'same_camera': before.get('camera') == after.get('camera'),
                     'camera_changes_between_samples': sum(r.get('event') == 'camera_changed'
                         and before.get('seq', 0) < r.get('seq', 0) <= after.get('seq', 0) for r in records),
                     'sampling_caveat': 'Two-second position samples cannot resolve individual-frame motion or identify who moved the actor.'}
            if author_before and author_after:
                facts['authored_distance_m'] = round(dist(author_before, author_after), 3)
            if actor_distance >= 5:
                finding('large_sampled_actor_motion', before, after,
                        'Camera and attached actor both moved over 5 metres between samples. Inspect the chore/cut and frame-level motion evidence; this is not proof of an instantaneous teleport.', **facts)
            elif actor_distance < 1:
                finding('camera_displacement_without_actor', before, after,
                        'Camera moved over 5 metres while the attached actor moved less than 1 metre, outside an authored interaction view. Check bone coordinates and camera ownership.', **facts)

        changes = [r for r in records if r.get('event') == 'camera_changed' and not is_fixture(r)]
        for before, after in zip(changes, changes[1:]):
            if (before.get('camera') != after.get('camera') and row_scene(before) == row_scene(after)
                    and not _authored(before) and not _authored(after)
                    and _number(before.get('frame')) and _number(after.get('frame'))
                    and after['frame'] - before['frame'] == 1 and _elapsed(before, after) <= 2):
                finding('transient_camera_activation', before, after,
                        'The active camera was replaced after one engine frame. This can be an authored transient shot; check whether camera/focus reset makes it visible in first person.',
                        activation_frames=1, transient_camera=before.get('camera'), next_camera=after.get('camera'),
                        focus_changes_during_activation=sum(r.get('event') == 'focus_changed'
                            and before.get('seq', 0) <= r.get('seq', 0) < after.get('seq', 0) for r in records))

        grouped = defaultdict(list)
        for index, sample in enumerate(samples):
            grouped[(row_scene(sample), sample.get('mode'), sample.get('camera'))].append((index, sample))
        for (scene, mode, camera), group in grouped.items():
            previous = None
            previous_index = -1
            motion_run = []
            mismatch_run = []

            def finish_motion():
                if len(motion_run) >= 3 and _elapsed(motion_run[0], motion_run[-1]) >= 6:
                    finding('movement_without_translation', motion_run[0], motion_run[-1],
                            'Directional input was sampled repeatedly without measurable actor displacement. A wall, scripted lock, or transition may explain this; reproduce before changing movement.',
                            samples=len(motion_run), tolerance_m=0.025)

            def finish_mismatch():
                if len(mismatch_run) >= 2:
                    finding('authored_view_position_mismatch', mismatch_run[0], mismatch_run[-1],
                            'An interaction view diverged from the saved authored camera position. Check station camera ownership and projection.',
                            samples=len(mismatch_run), max_distance_m=round(max(
                                dist(_position(r, 'camera'), _position(r, 'author')) for r in mismatch_run), 3))

            for index, sample in group:
                gap = _elapsed(previous, sample) if previous else 0
                if previous and (gap > 5 or index != previous_index + 1):
                    finish_motion(); finish_mismatch()
                    motion_run, mismatch_run = [], []
                camera_pos, author_pos, player_pos = (_position(sample, p) for p in ('camera', 'author', 'player'))
                if sample.get('camera') not in (None, 'none') and sample.get('actual_camera') not in (None, 'none', sample.get('camera')):
                    finding('active_camera_mismatch', sample, sample,
                            'The camera edited by the adapter differs from the active scene camera.',
                            adapter_camera=sample.get('camera'), active_camera=sample.get('actual_camera'))
                if camera_pos and author_pos and _authored(sample):
                    if dist(camera_pos, author_pos) > 0.25:
                        mismatch_run.append(sample)
                    else:
                        finish_mismatch(); mismatch_run = []
                elif mismatch_run:
                    finish_mismatch(); mismatch_run = []
                if camera_pos and player_pos and not _authored(sample):
                    distance = dist(camera_pos, player_pos)
                    # Alt intentionally restores the authored remote projection;
                    # its pose is observable even in builds without an Alt flag.
                    is_authored = author_pos is not None and dist(camera_pos, author_pos) <= 0.01
                    if distance > 5 and not is_authored:
                        finding('remote_actor_camera', sample, sample,
                                'Camera is over 5 metres from the attached actor outside an authored interaction view. Check stale bones or actor selection.',
                                distance_m=round(distance, 3))
                held = tuple(k for k in ('w', 'a', 's', 'd') if sample.get(k) is True)
                opposing = ('w' in held and 's' in held) or ('a' in held and 'd' in held)
                eligible = mode == 'explore' and sample.get('navigate') is True and held and not opposing and player_pos
                if eligible and (not motion_run or (held == tuple(k for k in ('w', 'a', 's', 'd') if motion_run[0].get(k) is True)
                                                   and dist(player_pos, _position(motion_run[0], 'player')) <= 0.025)):
                    motion_run.append(sample)
                else:
                    finish_motion()
                    motion_run = [sample] if eligible else []
                previous = sample
                previous_index = index
            finish_motion(); finish_mismatch()

    for row in rows:
        scene = row_scene(row)
        if not scene or is_fixture(row):
            continue
        key = (row.get('episode', 'unknown'), scene)
        entry = scenes.setdefault(key, {'episode': key[0], 'scene': scene, 'records': 0,
            'position_samples': 0, 'errors': 0, 'warnings': 0, 'sessions': set(), 'modes': Counter(),
            'cameras': Counter(), 'camera_changes': 0, 'focus_changes': 0, 'first': row.get('time'), 'last': row.get('time'),
            'telemetry': {'player_visibility_samples': 0, 'frame_motion_events': 0, 'visibility_events': 0,
                          'visibility_state_samples': 0, 'camera_fallback_events': 0,
                          'motion_kinds': Counter(), 'motion_states': Counter(), 'visibility_kinds': Counter()}})
        entry['records'] += 1
        entry['errors'] += row.get('level') == 'error'
        entry['warnings'] += row.get('level') == 'warn'
        entry['sessions'].add(row.get('session'))
        entry['last'] = row.get('time')
        entry['camera_changes'] += row.get('event') == 'camera_changed'
        entry['focus_changes'] += row.get('event') == 'focus_changed'
        if row.get('event') == 'camera_motion':
            entry['telemetry']['frame_motion_events'] += 1
            kind = row.get('kind') if isinstance(row.get('kind'), str) else 'unknown'
            entry['telemetry']['motion_kinds'][kind] += 1
        if row.get('event') == 'camera_fallback':
            entry['telemetry']['camera_fallback_events'] += 1
        if row.get('event') in ('visibility_override', 'visibility_restored', 'visibility_revoked',
                                'visibility_state', 'visibility_summary'):
            entry['telemetry']['visibility_events'] += 1
            entry['telemetry']['visibility_kinds'][row['event']] += 1
            entry['telemetry']['visibility_state_samples'] += row['event'] == 'visibility_state'
            if row['event'] == 'visibility_summary':
                entry['telemetry']['latest_visibility_summary'] = {
                    key: row[key] for key in ('time', 'frame', 'visible_actors', 'hidden_actors', 'tracked',
                                              'overridden', 'pending', 'scanned', 'emitted', 'hooks') if key in row}
        if is_gameplay_sample(row):
            entry['position_samples'] += 1
            entry['modes'][row.get('mode', 'unknown')] += 1
            entry['cameras'][row.get('camera', 'unknown')] += 1
            if isinstance(row.get('player_hidden'), bool):
                entry['telemetry']['player_visibility_samples'] += 1
            if isinstance(row.get('motion_state'), str):
                entry['telemetry']['motion_states'][row['motion_state']] += 1
            camera_pos, actor_pos, eye_target = (_position(row, p) for p in ('camera', 'player', 'eye_target'))
            if camera_pos and actor_pos:
                entry['telemetry']['max_camera_actor_distance_m'] = max(
                    entry['telemetry'].get('max_camera_actor_distance_m', 0), round(dist(camera_pos, actor_pos), 3))
            if camera_pos and eye_target and not _authored(row):
                entry['telemetry']['max_eye_target_error_m'] = max(
                    entry['telemetry'].get('max_eye_target_error_m', 0), round(dist(camera_pos, eye_target), 3))
    for entry in scenes.values():
        entry['sessions'] = sorted(entry['sessions'])
        entry['modes'], entry['cameras'] = dict(entry['modes']), dict(entry['cameras'])
        entry['telemetry']['motion_kinds'] = dict(entry['telemetry']['motion_kinds'])
        entry['telemetry']['motion_states'] = dict(entry['telemetry']['motion_states'])
        entry['telemetry']['visibility_kinds'] = dict(entry['telemetry']['visibility_kinds'])
        entry['findings'] = [f['code'] for f in findings if f['episode'] == entry['episode'] and f['scene'] == entry['scene']]
        entry['telemetry']['limits'] = []
        if not entry['telemetry']['player_visibility_samples']:
            entry['telemetry']['limits'].append('Player visibility was not logged; hidden/offstage actor selection cannot be assessed.')
        if not entry['telemetry']['visibility_events']:
            entry['telemetry']['limits'].append('NPC/object visibility changes were not logged; disappearing objects cannot be diagnosed from positions alone.')
        else:
            entry['telemetry']['limits'].append('Visibility scans are bounded and changed-state sampling is selective; hidden states can be intentional story actions.')
        if not entry['telemetry']['frame_motion_events']:
            entry['telemetry']['limits'].append('Only periodic position samples are available; individual-frame teleports cannot be confirmed.')
    return {'sessions': sessions, 'behavioral_findings': findings,
            'scene_diagnostics': [scenes[key] for key in sorted(scenes)],
            'camera_motion_events': [r for r in rows if r.get('event') in ('camera_motion', 'camera_fallback') and not is_fixture(r)],
            'visibility_events': [r for r in rows if r.get('event') in (
                'visibility_override', 'visibility_restored', 'visibility_revoked', 'visibility_state', 'visibility_summary') and not is_fixture(r)]}
