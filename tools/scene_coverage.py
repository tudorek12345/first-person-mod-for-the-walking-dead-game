"""Inventory installed story-scene resources and distinguish observation from playtesting."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import argparse
import json
from log_analysis import is_fixture, is_gameplay_sample, read_logs, row_scene, scene_name

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ('default', 'WalkingDead102', 'WalkingDead103', 'WalkingDead104', 'WalkingDead105')


def catalog(manifest):
    scenes = {}
    for archive in manifest['archives']:
        parts = PureWindowsPath(archive['path']).parts
        pack = next((i for i, part in enumerate(parts) if part.lower() == 'pack'), None)
        if pack is None or len(parts) <= pack + 2:
            continue
        episode = next((ep for ep in EPISODES if ep.lower() == parts[pack + 1].lower()), None)
        if episode is None:
            continue
        for name in archive.get('files', []):
            name = PureWindowsPath(name).name.lower()
            if name.endswith('.scene') and name.startswith(('adv_', 'env_')):
                key = (episode, name)
                sources = scenes.setdefault(key, {'episode': episode, 'scene': name, 'archives': []})['archives']
                if archive['path'] not in sources:
                    sources.append(archive['path'])
    return [scenes[key] for key in sorted(scenes)]


def summarize(scenes, rows, build):
    result = []
    for scene in scenes:
        observations = [r for r in rows if r.get('build') == build and not is_fixture(r)
                        and r.get('episode') == scene['episode']
                        and row_scene(r) == scene_name(scene['scene'])]
        positions = [r for r in observations if is_gameplay_sample(r)]
        result.append(dict(scene, status='observed' if positions else 'unobserved',
                           position_samples=len(positions),
                           scene_seen=bool(observations),
                           adapter_wait_events=sum(r.get('event') == 'adapter_waiting' for r in observations),
                           native_test_build_gameplay_samples=sum(r.get('native_test') is True for r in positions),
                           modes=sorted({r['mode'] for r in positions if r.get('mode')}),
                           cameras=sorted({r['camera'] for r in positions if r.get('camera')}),
                           errors=sum(r.get('level') == 'error' for r in observations),
                           warnings=sum(r.get('level') == 'warn' for r in observations),
                           last_observed=max((r['time'] for r in positions), default=None),
                           playthrough_verified=False))
    return {'generated': datetime.now(timezone.utc).isoformat(), 'build': build,
            'scope': 'Resource inventory, not a count of unique playable levels. Runtime observation is not progression verification.',
            'total_scene_resources': len(result),
            'observed': sum(r['status'] == 'observed' for r in result),
            'playthrough_verified': 0,
            'episodes': dict(Counter(r['episode'] for r in result)), 'scenes': result}


def generate(rows=None, build=None, *, root=ROOT):
    root = Path(root)
    manifest = json.loads((root / 'research/original/manifest.json').read_text())
    if build is None:
        build = json.loads((root / 'build/build-manifest.json').read_text())[0]['build']
    snapshot = None
    if rows is None:
        snapshot = read_logs(root / 'build/logs', root)
        rows = snapshot.pop('rows')
    report = summarize(catalog(manifest), rows, build)
    if snapshot is not None:
        report['log_read_issues'] = snapshot
    report['archives_not_indexed'] = [a['path'] for a in manifest['archives'] if 'files' not in a]
    output = root / 'build/scene-coverage.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"Scene resources: {report['observed']}/{report['total_scene_resources']} observed on build {build}; 0 full-scene playthroughs verified.")
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', help='Source build fingerprint; defaults to the last built version.')
    generate(build=parser.parse_args().build)
