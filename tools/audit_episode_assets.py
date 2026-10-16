"""Audit configured mod resources against original archive indexes, not gameplay."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ('default', 'WalkingDead102', 'WalkingDead103', 'WalkingDead104', 'WalkingDead105')


def resource_name(name):
    return PureWindowsPath(name).name.lower()


def load_config(path):
    from lupa import lua51
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(path.read_text(encoding='utf-8'))
    cfg = lua.globals().FP_Config
    return {'head_meshes': {name: list(meshes.values()) for name, meshes in cfg.head_meshes.items()},
            'weapons': [{'id': w.id, 'props': list(w.props.values()), 'flash': w.flash,
                         'sound': w.sound} for w in cfg.weapons.values()]}


def audit(manifest, config):
    index = {ep: defaultdict(list) for ep in EPISODES}
    unindexed = {ep: [] for ep in EPISODES}
    for archive in manifest['archives']:
        parts = PureWindowsPath(archive['path']).parts
        if len(parts) < 3 or parts[0].lower() != 'pack' or parts[1] not in index:
            continue
        episode = parts[1]
        if 'files' not in archive:
            unindexed[episode].append(archive['path'])
        for name in archive.get('files', []):
            index[episode][resource_name(name)].append(archive['path'])

    def evidence(episode, name):
        name = resource_name(name)
        local = sorted(index[episode].get(name, []))
        elsewhere = {ep: sorted(index[ep][name]) for ep in EPISODES
                     if ep != episode and name in index[ep]}
        status = 'indexed_in_episode' if local else (
            'indexed_in_other_episode_only' if elsewhere else 'not_indexed')
        return {'resource': name, 'status': status, 'archives': local,
                'other_episodes': elsewhere, 'runtime_verified': False}

    episodes = []
    for episode in EPISODES:
        heads = []
        for prefab, meshes in sorted(config['head_meshes'].items()):
            prefab_evidence = evidence(episode, prefab)
            heads.append({'prefab': prefab_evidence,
                          'applicable_to_indexed_prefab': bool(prefab_evidence['archives']),
                          'meshes': [evidence(episode, mesh + '.d3dmesh') for mesh in meshes]})
        weapons = []
        for weapon in config['weapons']:
            candidates = [evidence(episode, p) for p in weapon['props']]
            weapons.append({'id': weapon['id'], 'candidates': candidates,
                            'has_indexed_prefab_candidate': any(c['archives'] for c in candidates),
                            'flash': evidence(episode, weapon['flash']),
                            'sound': evidence(episode, weapon['sound'])})
        mapped = {resource_name(n) for n in config['head_meshes']}
        unmapped = sorted(n for n in index[episode] if n not in mapped
                          and re.fullmatch(r'sk\d+_(?:lee|clementine)[^.]*\.prop', n))
        episodes.append({'episode': episode, 'indexed_resource_count': len(index[episode]),
                         'archives_not_indexed': sorted(unindexed[episode]),
                         'helpers': [evidence(episode, n) for n in ('module_null.prop', 'ui_text.prop')],
                         'head_variants': heads, 'unmapped_actor_prefabs': unmapped,
                         'weapons': weapons})
    return {'generated': datetime.now(timezone.utc).isoformat(),
            'scope': 'Archive filename evidence only. Cross-episode mounting, prefab dependencies, '
                     'mesh visibility, sound playback and story progression require runtime checks. '
                     'Not indexed means unverified; unindexed archives may contain the resource.',
            'runtime_verified': False, 'episodes': episodes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'research/original/manifest.json')
    parser.add_argument('--config', type=Path, default=ROOT / 'src/fp_config.lua')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/episode-assets.json')
    args = parser.parse_args()
    report = audit(json.loads(args.manifest.read_text(encoding='utf-8')), load_config(args.config))
    report['config_sha256'] = hashlib.sha256(args.config.read_bytes()).hexdigest()
    report['manifest_sha256'] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for episode in report['episodes']:
        missing = [w['id'] for w in episode['weapons'] if not w['has_indexed_prefab_candidate']]
        sounds = sum(w['sound']['status'] == 'indexed_in_episode' for w in episode['weapons'])
        print(f"{episode['episode']}: weapon prefab candidates not indexed: {', '.join(missing) or 'none'}; "
              f"sounds indexed: {sounds}/{len(episode['weapons'])}; "
              f"unindexed archives: {len(episode['archives_not_indexed'])}")
    print(f'Resource inventory written to {args.output}; gameplay verification remains separate.')


if __name__ == '__main__':
    main()
