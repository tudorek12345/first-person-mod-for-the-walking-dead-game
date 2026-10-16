"""Collect mod errors, behavioral symptoms, scene coverage and Windows crashes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import base64
import json
import subprocess

from log_analysis import analyze, read_logs, timestamp
from scene_coverage import generate as scene_coverage

ROOT = Path(__file__).resolve().parents[1]


def powershell_json(script):
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    try:
        run = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', encoded],
                             capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'query_error': str(exc)}
    if run.returncode:
        return {'query_error': run.stderr.decode('utf-8', 'replace')}
    output = run.stdout.decode('utf-8-sig', 'replace').strip()
    try:
        return json.loads(output) if output else []
    except json.JSONDecodeError as exc:
        return {'query_error': str(exc), 'output': output[:500]}


def latest_build(root, rows):
    manifest = root / 'build/build-manifest.json'
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
        return data[0]['build'], None
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        fallback = next((r['build'] for r in reversed(rows) if isinstance(r.get('build'), str)), None)
        return fallback, str(exc)


def collect(since=None, all_builds=False, build=None, *, query_windows=True, root=ROOT):
    root = Path(root)
    since_time = timestamp(since) if since else None
    if since and since_time is None:
        raise ValueError('--since must be an ISO timestamp')
    snapshot = read_logs(root / 'build/logs', root)
    rows = snapshot.pop('rows')
    manifest_build, manifest_error = latest_build(root, rows)
    latest = build or manifest_build
    if not all_builds:
        rows = [r for r in rows if r.get('build') == latest]
        for key in ('malformed_log_lines', 'partial_log_lines'):
            snapshot[key] = [i for i in snapshot[key] if not i.get('builds') or latest in i['builds']]
    if since_time:
        rows = [r for r in rows if timestamp(r['time']) >= since_time]
    begin = (since_time or (timestamp(rows[0]['time']) if rows else datetime.now(timezone.utc))).isoformat()
    # begin has been parsed and serialized as an ISO timestamp, never raw input.
    windows = powershell_json("""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
try {
  $events=Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001,1002;StartTime=[datetime]'""" + begin + """'} |
    Where-Object {$_.Message -match 'WalkingDead101\\.exe'} |
    ForEach-Object {[pscustomobject]@{time=$_.TimeCreated.ToUniversalTime().ToString('o');id=$_.Id;message=$_.Message}}
  ConvertTo-Json -InputObject @($events) -Depth 4 -Compress
} catch {
  if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { '[]' }
  else { @{query_error=$_.Exception.Message} | ConvertTo-Json -Compress }
}
""") if query_windows else []
    analysis = analyze(rows)
    report = {
        'generated': datetime.now(timezone.utc).isoformat(), 'since': begin, 'build': latest,
        'builds_included': sorted({r['build'] for r in rows if isinstance(r.get('build'), str)}),
        'all_builds': all_builds,
        'scope': 'Logged Lua boundaries and sampled behavior; observations do not prove progression or full playthrough coverage.',
        'windows_scope': 'Application events since the selected log window; event records alone cannot identify the mod build.',
        **analysis,
        'errors': [r for r in rows if r.get('level') == 'error'],
        'warnings': [r for r in rows if r.get('level') == 'warn'],
        'native_tests': [r for r in rows if r.get('event') in ('native_test_result', 'native_tests_finished', 'native_test_skipped')],
        'recovery_events': [r for r in rows if 'recover' in r.get('event', '')],
        'recent_positions': [r for r in rows if r.get('event') == 'position_sample'][-50:],
        'windows_events': windows, 'windows_query_performed': query_windows,
        'manifest_read_error': manifest_error,
        **snapshot,
    }
    output = root / 'build/diagnostics.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        coverage = scene_coverage(rows, latest, root=root)
        report['scene_coverage'] = {'path': str(root / 'build/scene-coverage.json'),
                                    'observed': coverage['observed'],
                                    'total_scene_resources': coverage['total_scene_resources']}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report['scene_coverage_error'] = str(exc)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"Build {latest}: {len(report['sessions'])} script sessions, {len(report['errors'])} error records, {len(report['warnings'])} warnings")
    print(f"Behavioral findings requiring review: {len(report['behavioral_findings'])}")
    if query_windows:
        if isinstance(windows, list):
            print(f"Windows game crash/hang events since {begin}: {len(windows)}")
        else:
            print('Windows event query failed; see report')
    print(f"Report: {output}")
    return report


def failed(report):
    """Suspected behavior and a partial live append do not fail a diagnostic run."""
    return bool(report['errors'] or report['windows_events'] or report['malformed_log_lines']
                or report['unreadable_log_files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', help='ISO UTC timestamp, e.g. 2026-10-15T23:40:00Z')
    parser.add_argument('--all-builds', action='store_true')
    parser.add_argument('--build', help='Inspect a particular source build fingerprint.')
    parser.add_argument('--no-windows', action='store_true', help='Read Lua logs only; record that Windows events were not checked.')
    args = parser.parse_args()
    try:
        report = collect(args.since, args.all_builds, args.build, query_windows=not args.no_windows)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(1 if failed(report) else 0)
