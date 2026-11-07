#!/usr/bin/env python3
"""Read and reconcile por_digest_anchor records on NEAR through near-cli-rs.

Two subcommands:

    get        Print a near-views.json shaped document for one assessment file.
    reconcile  Compare fixtures/digests.json with the chain and anchor what is new.

Only testnet is accepted here. demo/run.sh owns the local sandbox, and this repo
does not write to mainnet.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGESTS = ROOT / "fixtures" / "digests.json"
ALLOWED_NETWORKS = {"testnet"}
VIEW_TIMEOUT = 120
SEND_TIMEOUT = 180


class NearError(RuntimeError):
    pass


def parse_network(value):
    if value not in ALLOWED_NETWORKS:
        raise SystemExit(
            f"near_digest: refusing network {value!r}. This script only writes and reads testnet; "
            "demo/run.sh runs the local sandbox."
        )
    return value


def run_near(args, timeout):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise NearError("near (near-cli-rs) is not installed")
    except subprocess.TimeoutExpired:
        raise NearError(f"near timed out after {timeout}s: {' '.join(args[:4])}")
    return proc


def extract_record(text):
    """Return the first decoded object that carries assessment_sha256."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            obj, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        found = find_record(obj)
        if found is not None:
            return found
    return None


def find_record(node):
    if isinstance(node, dict):
        if "assessment_sha256" in node and "exchange" in node:
            return node
        for value in node.values():
            hit = find_record(value)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for value in node:
            hit = find_record(value)
            if hit is not None:
                return hit
    return None


def view_get(contract, network, exchange, snapshot_id):
    """Return (record, missing, detail)."""
    args = [
        "near", "--quiet", "contract", "call-function", "as-read-only", contract, "get",
        "json-args", json.dumps({"exchange": exchange, "snapshot_id": snapshot_id}),
        "network-config", network, "now",
    ]
    proc = run_near(args, VIEW_TIMEOUT)
    text = f"{proc.stdout}\n{proc.stderr}"
    record = extract_record(proc.stdout)
    if record is not None:
        return record, False, ""
    if proc.returncode != 0 and "digest not found" in text:
        return None, True, "digest not found"
    if proc.returncode != 0:
        raise NearError(f"view get failed: {text.strip()[:400]}")
    return None, False, "view returned no DigestRecord"


def anchor(contract, network, row):
    args = {
        "exchange": row["exchange"],
        "snapshot_id": str(row["snapshotId"]),
        "assessment_sha256": row["sha256"],
        "por_stage": row["porStage"],
        "effective_por": bool(row["effectivePor"]),
        "methodology_version": row["methodologyVersion"],
    }
    cmd = [
        "near", "contract", "call-function", "as-transaction", contract, "anchor",
        "json-args", json.dumps(args), "prepaid-gas", "80 Tgas", "attached-deposit", "0 NEAR",
        "sign-as", contract, "network-config", network, "sign-with-legacy-keychain", "send",
    ]
    proc = run_near(cmd, SEND_TIMEOUT)
    if proc.returncode != 0:
        raise NearError(f"anchor failed for {row['exchange']} {row['snapshotId']}:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def normalize_hex(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        return None
    return text


def load_digests():
    try:
        doc = json.loads(DIGESTS.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"near_digest: cannot read {DIGESTS}: {exc}")
    rows = doc.get("assessments")
    if not isinstance(rows, list) or not rows:
        raise SystemExit("near_digest: fixtures/digests.json has no assessments")
    return doc, rows


def assessment_fields(path):
    try:
        assessment = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise NearError(f"cannot read {path}: {exc}")
    snapshot = assessment.get("snapshot") or {}
    exchange = assessment.get("exchange")
    snapshot_id = snapshot.get("id")
    if not exchange or snapshot_id is None:
        raise NearError(f"{path} is missing exchange or snapshot.id")
    return exchange, str(snapshot_id)


def cmd_get(opts):
    network = parse_network(opts.network)
    path = Path(opts.assessment)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    exchange, snapshot_id = assessment_fields(path)
    record, missing, detail = view_get(opts.contract, network, exchange, snapshot_id)
    doc = {
        "network": network,
        "live": True,
        "source": "testnet-get",
        "contract": opts.contract,
        "note": "Read from the NEAR testnet contract with a get view call.",
        "views": [],
    }
    if record is not None:
        doc["views"].append({
            "method": "get",
            "args": {"exchange": exchange, "snapshot_id": snapshot_id},
            "result": record,
        })
    else:
        doc["note"] = (
            f"No get view for {exchange} {snapshot_id} on {network} ({detail})."
            if missing else f"View returned no DigestRecord for {exchange} {snapshot_id}."
        )
    json.dump(doc, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_reconcile(opts):
    network = parse_network(opts.network)
    doc, rows = load_digests()
    source_commit = doc.get("sourceCommit")
    print(f"contract: {opts.contract}")
    print(f"network:  {network}")
    print(f"baseline: {source_commit or 'unrecorded'}")
    problems = []
    anchored = 0
    skipped = 0
    for row in rows:
        label = f"{row['exchange']} {row['snapshotId']}"
        path = ROOT / row["path"]
        if not path.is_file():
            problems.append(f"{label}: missing file {row['path']} (run git submodule update --init)")
            continue
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        listed_sha = normalize_hex(row.get("sha256"))
        if listed_sha != file_sha:
            problems.append(
                f"{label}: fixtures/digests.json sha256 {listed_sha} does not match the file {file_sha}"
            )
            continue
        before = len(problems)
        for key in ("porStage", "methodologyVersion"):
            if not row.get(key):
                problems.append(f"{label}: fixtures/digests.json is missing {key}")
        if "effectivePor" not in row:
            problems.append(f"{label}: fixtures/digests.json is missing effectivePor")
        if len(problems) != before:
            continue
        record, missing, detail = view_get(opts.contract, network, row["exchange"], str(row["snapshotId"]))
        if record is not None:
            on_chain = normalize_hex(record.get("assessment_sha256"))
            if on_chain == file_sha:
                print(f"ok       {label}: already anchored with the same bytes")
                skipped += 1
            else:
                problems.append(
                    f"{label}: on-chain sha256 {on_chain} differs from {file_sha}; "
                    "refusing to overwrite an anchored digest"
                )
            continue
        if not missing:
            problems.append(f"{label}: {detail}")
            continue
        if not opts.apply:
            print(f"would anchor {label} ({file_sha})")
            continue
        anchor(opts.contract, network, row)
        print(f"anchored {label} ({file_sha})")
        anchored += 1
    if problems:
        for line in problems:
            print(f"FAIL     {line}", file=sys.stderr)
        return 1
    print(f"done: {anchored} anchored, {skipped} already present, {len(rows)} total")
    if not opts.apply and anchored == 0:
        print("dry run: pass --apply to send anchor transactions")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--network", default="testnet")
    parser.add_argument("--contract", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    get = sub.add_parser("get", help="print a near-views.json shaped document for one assessment")
    get.add_argument("assessment", help="path to an assessment JSON")
    get.set_defaults(func=cmd_get)

    rec = sub.add_parser("reconcile", help="anchor what is missing and refuse what conflicts")
    rec.add_argument("--apply", action="store_true", help="send anchor transactions (default is dry run)")
    rec.set_defaults(func=cmd_reconcile)

    opts = parser.parse_args(argv)
    try:
        return opts.func(opts)
    except NearError as exc:
        print(f"near_digest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
