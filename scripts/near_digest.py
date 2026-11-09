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
sys.path.insert(0, str(ROOT / "scripts"))
from por_snapshot import build_anchor_args  # noqa: E402
from risk_score import CUSTODY_RISK_INCONCLUSIVE  # noqa: E402

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
        if "assessment_sha256" in node and "exchange" in node and "artifact_bundle_root" in node:
            return node
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
    if proc.returncode != 0 and (
        "snapshot not found" in text or "digest not found" in text
    ):
        return None, True, "snapshot not found"
    if proc.returncode != 0:
        raise NearError(f"view get failed: {text.strip()[:400]}")
    return None, False, "view returned no SnapshotRecord"


def point_latest(contract, network, exchange, snapshot_id):
    cmd = [
        "near", "contract", "call-function", "as-transaction", contract, "point_latest",
        "json-args", json.dumps({"exchange": exchange, "snapshot_id": snapshot_id}),
        "prepaid-gas", "30 Tgas", "attached-deposit", "0 NEAR",
        "sign-as", contract, "network-config", network, "sign-with-legacy-keychain", "send",
    ]
    proc = run_near(cmd, SEND_TIMEOUT)
    if proc.returncode != 0:
        raise NearError(f"point_latest failed for {exchange} {snapshot_id}:\n{proc.stdout}{proc.stderr}")


def load_assessment(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise NearError(f"cannot read {path}: {exc}")


def anchor(contract, network, assessment, assessment_sha256):
    try:
        args = build_anchor_args(assessment, assessment_sha256)
    except ValueError as exc:
        raise NearError(str(exc))
    cmd = [
        "near", "contract", "call-function", "as-transaction", contract, "anchor",
        "json-args", json.dumps(args), "prepaid-gas", "80 Tgas", "attached-deposit", "0 NEAR",
        "sign-as", contract, "network-config", network, "sign-with-legacy-keychain", "send",
    ]
    proc = run_near(cmd, SEND_TIMEOUT)
    if proc.returncode != 0:
        raise NearError(
            f"anchor failed for {args['exchange']} {args['snapshot_id']}:\n{proc.stdout}{proc.stderr}"
        )
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


def same_integrity(record, args):
    return (
        normalize_hex(record.get("assessment_sha256")) == args["assessment_sha256"]
        and normalize_hex(record.get("artifact_bundle_root")) == args["artifact_bundle_root"]
        and normalize_hex(record.get("verification_bundle_root")) == args["verification_bundle_root"]
        and normalize_hex(record.get("exchange_merkle_root")) == args["exchange_merkle_root"]
        and int(record.get("custody_risk_score", CUSTODY_RISK_INCONCLUSIVE))
        == int(args["custody_risk_score"])
    )


def roots_match(record, args):
    return (
        normalize_hex(record.get("assessment_sha256")) == args["assessment_sha256"]
        and normalize_hex(record.get("artifact_bundle_root")) == args["artifact_bundle_root"]
        and normalize_hex(record.get("verification_bundle_root")) == args["verification_bundle_root"]
        and normalize_hex(record.get("exchange_merkle_root")) == args["exchange_merkle_root"]
    )


def needs_custody_backfill(record, args):
    on_chain = record.get("custody_risk_score")
    if on_chain is None:
        return True
    try:
        return int(on_chain) != int(args["custody_risk_score"])
    except (TypeError, ValueError):
        return True


def set_custody_risk_score(contract, network, exchange, snapshot_id, score):
    cmd = [
        "near",
        "contract",
        "call-function",
        "as-transaction",
        contract,
        "set_custody_risk_score",
        "json-args",
        json.dumps({
            "exchange": exchange,
            "snapshot_id": snapshot_id,
            "custody_risk_score": score,
        }),
        "prepaid-gas",
        "40 Tgas",
        "attached-deposit",
        "0 NEAR",
        "sign-as",
        contract,
        "network-config",
        network,
        "sign-with-legacy-keychain",
        "send",
    ]
    proc = run_near(cmd, SEND_TIMEOUT)
    if proc.returncode != 0:
        raise NearError(
            f"set_custody_risk_score failed for {exchange} {snapshot_id}:\n{proc.stdout}{proc.stderr}"
        )


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
    assessment = load_assessment(path)
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
            if missing else f"View returned no SnapshotRecord for {exchange} {snapshot_id}."
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
        try:
            assessment = load_assessment(path)
            args = build_anchor_args(assessment, file_sha)
        except (NearError, ValueError) as exc:
            problems.append(f"{label}: {exc}")
            continue
        record, missing, detail = view_get(opts.contract, network, row["exchange"], str(row["snapshotId"]))
        if record is not None:
            if same_integrity(record, args):
                print(f"ok       {label}: already anchored with the same bytes")
                skipped += 1
            else:
                problems.append(
                    f"{label}: on-chain record differs from assessment roots/digest; "
                    "refusing to overwrite an anchored snapshot"
                )
            continue
        if not missing:
            problems.append(f"{label}: {detail}")
            continue
        if not opts.apply:
            print(f"would anchor {label} ({file_sha})")
            continue
        anchor(opts.contract, network, assessment, file_sha)
        print(f"anchored {label} ({file_sha})")
        anchored += 1
    if opts.apply and not problems:
        newest = {}
        for row in rows:
            newest[row["exchange"]] = str(row["snapshotId"])
        for exchange, snapshot_id in newest.items():
            point_latest(opts.contract, network, exchange, snapshot_id)
            print(f"latest   {exchange} {snapshot_id}")
    if problems:
        for line in problems:
            print(f"FAIL     {line}", file=sys.stderr)
        return 1
    print(f"done: {anchored} anchored, {skipped} already present, {len(rows)} total")
    if not opts.apply and anchored == 0:
        print("dry run: pass --apply to send anchor transactions")
    return 0


def cmd_backfill_custody(opts):
    network = parse_network(opts.network)
    _doc, rows = load_digests()
    print(f"contract: {opts.contract}")
    print(f"network:  {network}")
    updated = 0
    problems = []
    for row in rows:
        label = f"{row['exchange']} {row['snapshotId']}"
        path = ROOT / row["path"]
        if not path.is_file():
            problems.append(f"{label}: missing file {row['path']}")
            continue
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            assessment = load_assessment(path)
            args = build_anchor_args(assessment, file_sha)
        except (NearError, ValueError) as exc:
            problems.append(f"{label}: {exc}")
            continue
        record, missing, detail = view_get(opts.contract, network, row["exchange"], str(row["snapshotId"]))
        if missing:
            problems.append(f"{label}: snapshot not on chain ({detail})")
            continue
        if record is None:
            problems.append(f"{label}: {detail}")
            continue
        if not roots_match(record, args):
            problems.append(f"{label}: roots/digest differ; refusing custody backfill")
            continue
        if not needs_custody_backfill(record, args):
            print(f"ok       {label}: custody_risk_score already {args['custody_risk_score']}")
            continue
        if not opts.apply:
            print(
                f"would set custody_risk_score {args['custody_risk_score']} on {label} "
                f"(was {record.get('custody_risk_score', 'missing')})"
            )
            continue
        set_custody_risk_score(
            opts.contract,
            network,
            row["exchange"],
            str(row["snapshotId"]),
            args["custody_risk_score"],
        )
        print(f"updated  {label}: custody_risk_score -> {args['custody_risk_score']}")
        updated += 1
    if problems:
        for line in problems:
            print(f"FAIL     {line}", file=sys.stderr)
        return 1
    print(f"done: {updated} custody scores updated, {len(rows)} total")
    if not opts.apply and updated == 0:
        print("dry run: pass --apply to send set_custody_risk_score transactions")
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

    backfill = sub.add_parser(
        "backfill-custody",
        help="set custody_risk_score on existing v4 snapshots after contract upgrade (schema v5)",
    )
    backfill.add_argument("--apply", action="store_true", help="send set_custody_risk_score transactions")
    backfill.set_defaults(func=cmd_backfill_custody)

    opts = parser.parse_args(argv)
    try:
        return opts.func(opts)
    except NearError as exc:
        print(f"near_digest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
