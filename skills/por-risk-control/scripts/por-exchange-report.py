#!/usr/bin/env python3
"""Answer exchange-level PoR questions: latest on-chain snapshot + scored recent assessments."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIGESTS = ROOT / "fixtures" / "digests.json"
DEFAULT_CONTRACT = "por-digest-v5-index.ardmere-demo-1fc2.testnet"


def parse_iso8601(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def near_get_latest(contract: str, network: str, exchange: str) -> dict:
    proc = subprocess.run(
        [
            "near",
            "--quiet",
            "contract",
            "call-function",
            "as-read-only",
            contract,
            "get_latest",
            "json-args",
            json.dumps({"exchange": exchange}),
            "network-config",
            network,
            "now",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    text = proc.stdout
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"get_latest failed for {exchange}: {proc.stderr or proc.stdout}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise RuntimeError(f"could not parse get_latest JSON for {exchange}")


def run_por_check(assessment_path: Path, contract: str, network: str) -> dict:
    env = {**os.environ, "POR_NEAR_CONTRACT": contract, "POR_NEAR_NETWORK": network}
    proc = subprocess.run(
        [str(Path(__file__).with_name("por-check.sh")), str(assessment_path)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exchange", help="exchange id, e.g. binance")
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="only include assessments with snapshotTime within this many months before the latest manifest snapshot",
    )
    parser.add_argument("--contract", default=os.environ.get("POR_NEAR_CONTRACT", DEFAULT_CONTRACT))
    parser.add_argument("--network", default=os.environ.get("POR_NEAR_NETWORK", "testnet"))
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = parser.parse_args()
    exchange = args.exchange.strip().lower()

    manifest = json.loads(DIGESTS.read_text(encoding="utf-8"))
    rows = [item for item in manifest.get("assessments", []) if item.get("exchange") == exchange]
    if not rows:
        print(f"No assessments listed for exchange {exchange!r} in fixtures/digests.json", file=sys.stderr)
        return 1

    rows.sort(key=lambda item: parse_iso8601(item["snapshotTime"]))
    latest_row = rows[-1]
    latest_dt = parse_iso8601(latest_row["snapshotTime"])

    live = near_get_latest(args.contract, args.network, exchange)
    live_dt = datetime.fromtimestamp(int(live["snapshot_time"]), tz=timezone.utc)

    if args.months is not None and args.months > 0:
        cutoff = latest_dt - timedelta(days=30 * args.months)
        period_rows = [item for item in rows if parse_iso8601(item["snapshotTime"]) >= cutoff]
    else:
        period_rows = rows

    scored = []
    for item in period_rows:
        path = ROOT / item["path"]
        if not path.is_file():
            print(f"skip missing file: {path}", file=sys.stderr)
            continue
        score = run_por_check(path, args.contract, args.network)
        scored.append(
            {
                "snapshotId": item["snapshotId"],
                "snapshotTime": item["snapshotTime"],
                "porStage": score.get("porStage"),
                "effectivePoR": score.get("effectivePoR"),
                "riskScore": score.get("riskScore"),
                "riskLevel": score.get("riskLevel"),
                "riskFlags": score.get("riskFlags", []),
                "nearMatches": (score.get("near") or {}).get("matches"),
            }
        )

    payload = {
        "exchange": exchange,
        "contract": args.contract,
        "network": args.network,
        "latest": {
            "snapshotId": live["snapshot_id"],
            "snapshotTimeUtc": live_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "manifestSnapshotId": latest_row["snapshotId"],
            "manifestSnapshotTime": latest_row["snapshotTime"],
            "porStage": {0: "Pre-Stage", 1: "Stage 0", 2: "Stage 1", 3: "Stage 2"}.get(
                int(live.get("por_stage", 0)), str(live.get("por_stage"))
            ),
            "effectivePoR": bool(live.get("effective_por")),
            "assessmentSha256": live.get("assessment_sha256"),
        },
        "period": {
            "months": args.months,
            "count": len(scored),
            "assessments": scored,
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Exchange: {exchange}")
    print(f"NEAR contract: {args.contract} ({args.network})")
    print()
    print("Latest PoR snapshot (get_latest on chain):")
    print(f"  snapshot id:     {payload['latest']['snapshotId']}")
    print(f"  snapshot time:   {payload['latest']['snapshotTimeUtc']} (UTC)")
    print(f"  por stage:       {payload['latest']['porStage']}")
    print(f"  effective PoR:   {payload['latest']['effectivePoR']}")
    print()
    label = f"Last {args.months} months" if args.months else "All listed snapshots"
    print(f"{label} — custody risk (por-check vs live chain):")
    for row in scored:
        flags = ", ".join(row["riskFlags"][:3])
        if len(row["riskFlags"]) > 3:
            flags += ", …"
        print(
            f"  {row['snapshotId']:12}  {row['snapshotTime'][:10]}  "
            f"{row['porStage']:8}  score={row['riskScore']:3} {row['riskLevel']:8}  "
            f"near.matches={row['nearMatches']}  flags={flags}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
