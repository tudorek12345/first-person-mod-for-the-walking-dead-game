"""Package only this mod's scripts and installer; never distribute game scripts."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ('default', 'WalkingDead102', 'WalkingDead103', 'WalkingDead104', 'WalkingDead105')
FORBIDDEN = {'fp_original_system.lua', 'fp_original_visibility.lua'}
PROJECT = 'first-person-mod-for-the-walking-dead-game'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generated_config(build, episode):
    return (
        'local base=os and os.getenv and os.getenv("LOCALAPPDATA")\n'
        'local directory=base and (string.gsub(base,"\\\\","/").."/First-person-mode/logs") or "."\n'
        'FP_Generated={log_dir=directory,log_path=directory.."/runtime.log",'
        f'build={json.dumps(build)},episode={json.dumps(episode)},native_test=false}}\n'
    )


def build_release(version):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', version):
        raise ValueError('Expected a version such as v0.5.1')
    compiler = ROOT / 'tools/telltale-lua/luac.exe'
    sources = sorted((ROOT / 'src').glob('*.lua'))
    if FORBIDDEN & {p.name for p in sources}:
        raise ValueError('Original game scripts must not enter the release payload')
    fingerprint = hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()[:16]
    destination = ROOT / 'build/release' / f'{PROJECT}-{version}'
    # A fresh staging directory prevents stale files leaking into a release.
    if destination.exists():
        if not destination.resolve().is_relative_to((ROOT / 'build/release').resolve()):
            raise ValueError('Release staging escaped workspace')
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    installer_files = ('Install.cmd', 'Uninstall.cmd', 'Install.ps1', 'Uninstall.ps1', 'Installer.Core.ps1')
    for name in installer_files:
        shutil.copy2(ROOT / 'installer' / name, destination / name)
    for name in ('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, destination / name)
    (destination / 'docs').mkdir()
    shutil.copy2(ROOT / 'docs/DEVELOPMENT.md', destination / 'docs/DEVELOPMENT.md')
    (destination / 'START-HERE.txt').write_text(
        'FIRST-PERSON MODE — ORIGINAL THE WALKING DEAD\n\n'
        'Windows / original Steam Season One / Episodes 1–5. Experimental.\n'
        'Not Definitive Edition or Seasons Two–Four.\n\n'
        '1. Close the game. Extract the entire ZIP first.\n'
        '2. Double-click Install.cmd and follow the prompts. Internet is needed once.\n'
        '3. Launch the game normally from Steam.\n\n'
        'If the game folder is not found, Steam > game > Manage > Browse local files;\n'
        'copy that folder path into the installer.\n'
        'If access is denied, right-click Install.cmd and Run as administrator.\n\n'
        'F6: original/first-person camera   F8: recover camera\n'
        'Alt (hold): original interaction view   G: draw/holster\n'
        '1/2/3: weapons   Left mouse: fire   Right mouse: aim   R: reload\n\n'
        'To remove: close the game and double-click Uninstall.cmd.\n'
        'Logs: paste %LOCALAPPDATA%\\First-person-mode\\logs into File Explorer.\n'
        f'Report problems: https://github.com/tudorek12345/{PROJECT}/issues\n'
        'Include episode/location, steps, and the newest fp-*.jsonl log.\n', encoding='utf-8')
    manifest = {'format': 1, 'version': version, 'build': fingerprint, 'episodes': []}
    for episode in EPISODES:
        folder = destination / 'payload' / episode
        folder.mkdir(parents=True)
        for source in sources:
            subprocess.run([str(compiler), '-o', str(folder / source.name), source.name],
                           cwd=source.parent, check=True, capture_output=True)
        generated = destination.parent / f'{episode}-generated.lua'
        generated.write_text(generated_config(fingerprint, episode), encoding='utf-8')
        subprocess.run([str(compiler), '-o', str(folder / 'fp_generated.lua'), generated.name],
                       cwd=generated.parent, check=True, capture_output=True)
        manifest['episodes'].append({'episode': episode, 'scripts': [
            {'name': p.name, 'sha256': digest(p)} for p in sorted(folder.glob('*.lua'))]})
    (destination / 'payload/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    output = ROOT / 'dist' / f'{PROJECT}-{version}-Windows.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                if path.name in FORBIDDEN or path.suffix.lower() in ('.ttarch', '.exe', '.dll', '.sav'):
                    raise ValueError(f'Forbidden release content: {path.name}')
                archive.write(path, str(Path(destination.name) / path.relative_to(destination)))
    checksum = output.with_suffix('.zip.sha256')
    checksum.write_text(f'{digest(output)}  {output.name}\n', encoding='ascii')
    print(json.dumps({'zip': str(output), 'sha256': digest(output), 'build': fingerprint,
                      'staging': str(destination), 'episodes': len(manifest['episodes'])}, indent=2))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='v0.5.1')
    build_release(parser.parse_args().version)
