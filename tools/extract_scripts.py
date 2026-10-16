"""Extract locally installed TWD scripts without modifying the installation.

The lowest lexical archive name has patch priority in classic Telltale games.
Keep each archive separately and record origins instead of losing provenance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\The Walking Dead")


def extract(game: Path):
    exe = ROOT / "tools/ttarchext/ttarchext.exe"
    out = ROOT / "research/original"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"game": str(game), "archives": [], "episodes": {}}
    for episode in sorted((game / "Pack").iterdir()):
        if not episode.is_dir():
            continue
        resolved = out / "resolved" / episode.name
        resolved.mkdir(parents=True, exist_ok=True)
        origins = {}
        for archive in sorted(episode.glob("*.ttarch"), reverse=True):
            # The mod's own archive must never become an extraction input.
            if "firstperson" in archive.name.lower():
                continue
            probe = subprocess.run([str(exe), "-l", "52", str(archive), "."], capture_output=True)
            listing = (probe.stdout + probe.stderr).decode("utf-8", "replace")
            if probe.returncode:
                manifest["archives"].append({"path": str(archive.relative_to(game)),
                                             "error": listing})
                print(f"Cannot index {archive.name}; recorded error", flush=True)
                continue
            entries = re.findall(r"^\s+([0-9a-fA-F]{8})\s+(\d+)\s+(.+)$", listing, re.M)
            names = [name.strip() for _, _, name in entries]
            record = {"path": str(archive.relative_to(game)), "size": archive.stat().st_size,
                      "files": names}
            manifest["archives"].append(record)
            if not any(n.endswith((".lenc", ".lua")) for n in names):
                continue
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            record["sha256"] = digest
            folder = out / "archives" / digest
            if not folder.exists():
                folder.mkdir(parents=True)
                for suffix in ("*.lenc", "*.lua"):
                    p = subprocess.run([str(exe), "-o", "-f", suffix, "52", str(archive), str(folder)],
                                       capture_output=True, check=True)
                    (folder / (suffix[2:] + "-extract.log")).write_bytes(p.stdout + p.stderr)
            for script in folder.glob("*.lua"):
                shutil.copy2(script, resolved / script.name)
                origins[script.name] = record["path"]
        manifest["episodes"][episode.name] = origins
        print(f"{episode.name}: {len(origins)} resolved scripts", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    args = parser.parse_args()
    extract(args.game)
