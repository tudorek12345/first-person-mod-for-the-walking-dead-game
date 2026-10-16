"""Decompile extracted local scripts, caching identical bytecode by hash."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    java = next((ROOT / "tools/java").glob("jdk-21*/bin/java.exe"))
    jar = ROOT / "tools/telltale-lua/unluac.jar"
    cache = ROOT / "research/decompile-cache"
    cache.mkdir(exist_ok=True)
    files = list((ROOT / "research/original/resolved").glob("*/*.lua"))
    unique = {}
    for p in files:
        unique.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p)

    def decompile(item):
        digest, inputs = item
        result = cache / (digest + ".lua")
        if not result.exists():
            proc = subprocess.run([str(java), "-jar", str(jar), str(inputs[0])],
                                  capture_output=True, timeout=60)
            if proc.returncode or not proc.stdout:
                return {"file": str(inputs[0]), "error": proc.stderr.decode("utf-8", "replace")}
            result.write_bytes(proc.stdout)
        for p in inputs:
            target = ROOT / "research/decompiled" / p.parent.name / p.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result, target)
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        errors = [err for err in pool.map(decompile, unique.items()) if err]
    report = {"scripts": len(files), "unique": len(unique), "errors": errors}
    (ROOT / "research/decompile-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
