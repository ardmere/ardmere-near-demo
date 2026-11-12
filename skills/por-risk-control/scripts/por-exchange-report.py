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
sys.path.insert(0, str(ROOT / "scripts"))
from near_rpc import NearRpcError, view_get_latest  # noqa: E402
from por_sources import official_sources  # noqa: E402
DIGESTS = ROOT / "fixtures" / "digests.json"
DEFAULT_CONTRACT = "por-digest-v7-index.ardmere-demo-1fc2.testnet"


def _yn(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "—"


def _fmt_usd(value) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number >= 1e9:
        return f"${number / 1e9:.2f}B"
    if number >= 1e6:
        return f"${number / 1e6:.2f}M"
    return f"${number:,.0f}"


def _print_reserve_block(reserves: dict | None) -> None:
    if not isinstance(reserves, dict):
        return
    print("### Self-reported reserves (exchange disclosure)\n")
    print("| Metric | Value |")
    print("| --- | --- |")
    print(f"| Total liability (USD) | {_fmt_usd(reserves.get('totalLiabilityUsd'))} |")
    print(f"| Total reserve (USD) | {_fmt_usd(reserves.get('totalReserveUsd'))} |")
    ratio = reserves.get("totalReserveRatioPct") or "—"
    print(f"| Total reserve ratio | {ratio} |")
    print()
    print("| Coin | Reserve ratio |")
    print("| --- | ---: |")
    for row in reserves.get("majorCoinReserveRates") or []:
        if not isinstance(row, dict):
            continue
        pct = row.get("reserveRatioPct") if row.get("available") else "—"
        print(f"| {row.get('coin', '?')} | {pct} |")
    print()
    print("_Self-reported only; not verified solvency. Coin rows follow BTC, ETH, USDT, USDC, BNB display order._\n")


def _factor_summary(factors, limit: int = 5) -> str:
    if not isinstance(factors, list) or not factors:
        return "—"
    parts = []
    for row in factors[:limit]:
        if not isinstance(row, dict):
            continue
        fid = row.get("id") or "?"
        delta = row.get("delta")
        parts.append(f"{fid} (+{delta})" if delta is not None else fid)
    if len(factors) > limit:
        parts.append(f"+{len(factors) - limit} more")
    return ", ".join(parts)


def print_markdown_report(payload: dict, period_label: str) -> None:
    exchange = payload["exchange"]
    latest = payload["latest"]
    src = latest.get("officialSources") or {}

    print(f"## {exchange} · PoR transparency risk\n")
    print("| Item | Value |")
    print("| --- | --- |")
    print(f"| NEAR contract | `{payload['contract']}` ({payload['network']}) |")
    print(f"| Latest snapshot (chain) | `{latest['snapshotId']}` |")
    print(f"| Snapshot time (UTC) | {latest['snapshotTimeUtc']} |")
    print(f"| PoR stage | {latest['porStage']} |")
    print(f"| Effective PoR | {_yn(latest['effectivePoR'])} |")
    print(f"| Assessment SHA256 | `{latest.get('assessmentSha256') or '—'}` |")
    print()

    print("### Official sources (user verification)\n")
    print("| Kind | URL |")
    print("| --- | --- |")
    if src.get("exchangePorPage"):
        print(f"| Exchange PoR page | {src['exchangePorPage']} |")
    for art in src.get("publicArtifacts") or []:
        print(f"| {art.get('kind', 'artifact')} | {art.get('url', '—')} |")
    for repo in src.get("upstreamVerifierRepos") or [][:3]:
        print(f"| OSS ({repo.get('role', 'verifier')}) | {repo.get('url', '—')} |")
    if src.get("ardmereTransparencyReport"):
        print(f"| ardmere transparency report | {src['ardmereTransparencyReport']} |")
    if src.get("ardmereAssessment"):
        print(f"| ardmere assessment JSON | {src['ardmereAssessment']} |")
    print()

    manifest_id = latest.get("manifestSnapshotId")
    latest_reserves = None
    for row in payload["period"]["assessments"]:
        if row.get("snapshotId") == manifest_id:
            latest_reserves = row.get("selfReportedReserves")
            break
    _print_reserve_block(latest_reserves)

    rows = payload["period"]["assessments"]
    print(f"### {period_label} ({len(rows)} snapshots)\n")
    print("| Snapshot | Date | Stage | Risk | Level | Hash OK | Scoring | Top factors |")
    print("| --- | --- | --- | ---: | --- | :---: | --- | --- |")
    for row in rows:
        flags = row.get("riskFlags") or []
        flag_cell = ", ".join(flags[:3])
        if len(flags) > 3:
            flag_cell += ", …"
        print(
            f"| `{row['snapshotId']}` | {row['snapshotTime'][:10]} | {row.get('porStage') or '—'} "
            f"| **{row.get('riskScore')}** | {row.get('riskLevel') or '—'} "
            f"| {_yn(row.get('nearMatches'))} | {row.get('scoringSource') or '—'} "
            f"| {_factor_summary(row.get('factors')) or flag_cell} |"
        )
    print()
    print("_Scores are **transparency risk** (higher = worse disclosure), not reserve adequacy._")


def parse_iso8601(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def near_get_latest(contract: str, network: str, exchange: str) -> dict:
    try:
        return view_get_latest(contract, exchange, network=network)
    except NearRpcError as exc:
        raise RuntimeError(f"get_latest failed for {exchange}: {exc}") from exc


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
    parser.add_argument(
        "--format",
        choices=("markdown", "plain"),
        default="markdown",
        help="human layout: markdown tables (default) or plain lines",
    )
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
    latest_assessment_path = ROOT / latest_row["path"]
    latest_assessment = json.loads(latest_assessment_path.read_text(encoding="utf-8"))
    latest_sources = official_sources(latest_assessment, latest_assessment_path, repo_root=ROOT)

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
        assessment = json.loads(path.read_text(encoding="utf-8"))
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
                "factors": score.get("factors", []),
                "scoringSource": score.get("scoringSource"),
                "nearMatches": (score.get("near") or {}).get("matches"),
                "selfReportedReserves": score.get("selfReportedReserves"),
                "officialSources": official_sources(assessment, path, repo_root=ROOT),
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
            "officialSources": latest_sources,
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

    period_label = f"Last {args.months} months" if args.months else "All listed snapshots"
    if args.format == "markdown":
        print_markdown_report(payload, period_label)
        return 0

    print(f"Exchange: {exchange}")
    print(f"NEAR contract: {args.contract} ({args.network})")
    print()
    print("Latest (chain get_latest):")
    print(f"  snapshot: {payload['latest']['snapshotId']}  @ {payload['latest']['snapshotTimeUtc']} UTC")
    print(f"  stage: {payload['latest']['porStage']}  effectivePoR: {payload['latest']['effectivePoR']}")
    src = payload["latest"].get("officialSources") or {}
    if src.get("exchangePorPage"):
        print(f"  por page: {src['exchangePorPage']}")
    print()
    print(f"{period_label}:")
    for row in scored:
        print(
            f"  {row['snapshotId']:14} {row['snapshotTime'][:10]}  "
            f"score={row['riskScore']} {row['riskLevel']}  match={row['nearMatches']}  "
            f"src={row.get('scoringSource')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
