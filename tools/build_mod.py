"""Build and optionally install the mod as isolated classic TTARCH patches."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import struct
import re
from ttarch_patch import pack
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\The Walking Dead")
PATCH_NAME = "0_00_firstperson.ttarch"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode("utf-8", "replace"))
    return result


def assert_game_closed():
    result = run(["tasklist", "/FI", "IMAGENAME eq WalkingDead101.exe", "/FO", "CSV", "/NH"])
    if b'WalkingDead101.exe' in result.stdout:
        raise RuntimeError("Close The Walking Dead before installing or uninstalling the mod.")


def build(game, install=False, native_test=False):
    if install:
        assert_game_closed()
    compiler = ROOT / "tools/telltale-lua/luac.exe"
    archiver = ROOT / "tools/ttarchext/ttarchext.exe"
    records = []
    for episode in sorted((ROOT / "research/original/resolved").iterdir()):
        original = episode / "_system.lua"
        if not original.exists():
            continue
        stage = ROOT / "build/stage" / episode.name
        stage.mkdir(parents=True, exist_ok=True)
        # Only remove generated flat script files from our own staging folder.
        for stale in stage.glob("*.lua"):
            stale.unlink()
        shutil.copy2(original, stage / "fp_original_system.lua")
        visibility = episode / "module_visibility.lua"
        if not visibility.exists():
            raise RuntimeError(f"Missing original visibility module: {visibility}")
        shutil.copy2(visibility, stage / "fp_original_visibility.lua")
        for source in (ROOT / "src").glob("*.lua"):
            run([compiler, "-o", stage / source.name, source])
        generated = ROOT / "build" / "fp_generated.lua"
        log_path = (ROOT / "build/runtime.log").as_posix()
        logs = ROOT / "build/logs"
        logs.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "src").glob("*.lua")))).hexdigest()[:16]
        generated.write_text("FP_Generated={log_path=" + json.dumps(log_path) +
            ",log_dir=" + json.dumps(logs.as_posix()) + ",build=" + json.dumps(source_hash) +
            ",episode=" + json.dumps(episode.name) + ",native_test=" + str(native_test).lower() + "}\n", encoding="utf-8")
        run([compiler, "-o", stage / "fp_generated.lua", generated])
        output = ROOT / "dist/Pack" / episode.name / PATCH_NAME
        output.parent.mkdir(parents=True, exist_ok=True)
        intermediate = ROOT / "build" / "encrypted-v8.ttarch"
        run([archiver, "-o", "-b", "-x", "-V", "8", "52", intermediate, stage])
        v8 = intermediate.read_bytes()
        if struct.unpack_from("<5I", v8) != (8, 1, 2, 1, 0):
            raise RuntimeError("Unexpected uncompressed archive header")
        listing = run([archiver, "-l", "52", intermediate, ROOT]).stdout.decode("utf-8", "replace")
        entries = re.findall(r"^\s+([0-9a-fA-F]{8})\s+(\d+)\s+(.+)$", listing, re.M)
        if len(entries) != len(list(stage.glob("*.lua"))):
            raise RuntimeError("Encrypted archive entry count mismatch")
        output.write_bytes(pack({name.strip(): v8[int(offset, 16):int(offset, 16) + int(size)]
                                 for offset, size, name in entries}))
        # Verify every compiled and preserved script survived archive encryption.
        verify = ROOT / "build/verify" / episode.name
        verify.mkdir(parents=True, exist_ok=True)
        run([archiver, "-o", "52", output, verify])
        for source in stage.glob("*.lua"):
            if source.read_bytes() != (verify / source.name).read_bytes():
                raise RuntimeError(f"Archive round-trip mismatch: {source}")
        record = {"episode": episode.name, "archive": str(output.relative_to(ROOT)),
                  "sha256": digest(output), "original_system_sha256": digest(original),
                  "original_visibility_sha256": digest(visibility),
                  "scripts": len(list(stage.glob('*.lua'))), "build": source_hash,
                  "native_test": native_test}
        records.append(record)
        print(f"Built and round-trip verified {episode.name}: {output.stat().st_size} bytes")
    if install:
        # Only our own new archive is installed. Existing game archives are untouched.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for record in records:
            source = ROOT / record["archive"]
            target = game / "Pack" / record["episode"] / PATCH_NAME
            if target.exists():
                backup = ROOT / "build/install-backups" / stamp / record["episode"] / PATCH_NAME
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            shutil.copy2(source, target)
            if digest(source) != digest(target):
                raise RuntimeError(f"Install verification failed: {target}")
        print(f"Installed {len(records)} isolated patch archives in {game}")
    (ROOT / "build/build-manifest.json").write_text(json.dumps(records, indent=2))


def uninstall(game):
    assert_game_closed()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for episode in ("default", "WalkingDead102", "WalkingDead103", "WalkingDead104", "WalkingDead105"):
        target = (game / "Pack" / episode / PATCH_NAME).resolve()
        if not target.is_relative_to(game.resolve()):
            raise RuntimeError("Patch path escaped the game directory")
        if target.exists():
            backup = ROOT / "build/uninstalled" / stamp / episode / PATCH_NAME
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(backup))
            print(f"Removed mod patch from {episode}; retained backup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--native-test", action="store_true")
    args = parser.parse_args()
    if args.uninstall:
        uninstall(args.game)
    else:
        build(args.game, args.install, args.native_test)
