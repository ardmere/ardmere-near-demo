#!/usr/bin/env python3
"""Report how the vendored ardmere assessments differ from fixtures/digests.json.

Reads the submodule only. No network, no keys, no chain calls. Exit code 1 means the
manifest is behind the submodule, so CI can open a PR or fail a check.

    upstream_check.py                     # report drift, including assessments not yet listed
    upstream_check.py --update            # refresh changed rows and add every unlisted assessment
    upstream_check.py --update --add binance/PR04NOV26  # add only the unlisted rows this text matches
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGESTS = ROOT / "fixtures" / "digests.json"
SUB = ROOT / "vendor" / "ardmere.github.io"
REPORTS = SUB / "docs" / "reports"


def submodule_head():
    try:
        proc = subprocess.run(
            ["git", "-C", str(SUB), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None


def load_digests():
    try:
        return json.loads(DIGESTS.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"upstream_check: cannot read {DIGESTS}: {exc}")


def assessment_fields(path):
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    snapshot = doc.get("snapshot") or {}
    exchange = doc.get("exchange")
    snapshot_id = snapshot.get("id")
    if not isinstance(exchange, str) or snapshot_id is None:
        return None
    stage = doc.get("porStage")
    effective = doc.get("effectivePoR")
    methodology = doc.get("methodologyVersion")
    if not isinstance(stage, str) or not isinstance(methodology, str) or not isinstance(effective, bool):
        return None
    return {
        "exchange": exchange,
        "snapshotId": str(snapshot_id),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "porStage": stage,
        "effectivePor": effective,
        "methodologyVersion": methodology,
        "snapshotTime": snapshot.get("snapshotTime") if isinstance(snapshot.get("snapshotTime"), str) else "",
        "reportUrl": report_url(exchange, str(snapshot_id)),
    }


def report_url(exchange, snapshot_id):
    return f"https://ardmere.github.io/docs/reports/{exchange}/{snapshot_id}-transparency-report.html"


def scan():
    """Return {relative path: fields} for every assessment in the submodule."""
    found = {}
    if not REPORTS.is_dir():
        raise SystemExit("upstream_check: submodule is missing. Run: git submodule update --init --recursive")
    for path in sorted(REPORTS.rglob("*-assessment.json")):
        fields = assessment_fields(path)
        if fields is None:
            continue
        found[path.relative_to(ROOT).as_posix()] = fields
    return found


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite fixtures/digests.json")
    parser.add_argument("--add", action="append", default=[],
                        help="add assessments whose path contains this text (repeatable)")
    opts = parser.parse_args(argv)

    doc = load_digests()
    rows = doc.get("assessments")
    if not isinstance(rows, list):
        raise SystemExit("upstream_check: fixtures/digests.json has no assessments list")

    on_disk = scan()
    head = submodule_head()
    listed = {row["path"]: row for row in rows}

    new = [p for p in on_disk if p not in listed]
    gone = [p for p in listed if p not in on_disk]
    changed = [
        p for p in on_disk
        if p in listed and on_disk[p]["sha256"] != str(listed[p].get("sha256", "")).lower()
    ]

    print(f"submodule HEAD: {head or 'unknown'}")
    print(f"manifest commit: {doc.get('sourceCommit') or 'unrecorded'}")
    print(f"in submodule:   {len(on_disk)} assessments, {len(rows)} listed in the manifest")

    for path in changed:
        print(f"CHANGED  {path}")
    for path in gone:
        print(f"MISSING  {path}")
    for path in new:
        print(f"NEW      {path}")

    selected = []
    if opts.add:
        for needle in opts.add:
            hits = [p for p in new if needle in p]
            if not hits:
                print(f"upstream_check: --add {needle} matched no unlisted assessment", file=sys.stderr)
                return 2
            selected.extend(hits)
    elif opts.update:
        selected = list(new)

    drift = bool(changed or gone or new)
    if not opts.update:
        exchanges = sorted({fields["exchange"] for fields in on_disk.values()})
        print(f"exchanges in the submodule: {', '.join(exchanges)}")
        if drift:
            print("drift")
            return 1
        print("manifest lists every assessment in the submodule")
        return 0

    for row in rows:
        fields = on_disk.get(row["path"])
        if fields is not None:
            row.update(fields)

    for path in selected:
        fields = on_disk[path]
        rows = [row for row in rows if row["path"] != path]
        rows.append({"path": path, **fields})
        print(f"added {path}")

    rows.sort(key=lambda row: (row.get("exchange") or "", row.get("snapshotTime") or "", row["path"]))
    doc["assessments"] = rows
    if head:
        doc["sourceCommit"] = head
    DIGESTS.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {DIGESTS.relative_to(ROOT)} ({len(rows)} assessments)")
    if gone:
        print("warning: the manifest still lists files that are not in the submodule", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
