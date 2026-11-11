"""Build Sepolia-aligned NEAR anchor args from an assessment JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from risk_score import custody_risk_score_for_anchor

STAGE_TO_U8 = {
    "Pre-Stage": 0,
    "Stage 0": 1,
    "Stage 1": 2,
    "Stage 2": 3,
}


def encode_por_stage(stage: Any) -> int:
    if isinstance(stage, int):
        return stage if 0 <= stage <= 3 else 0
    if not isinstance(stage, str):
        return 0
    return STAGE_TO_U8.get(stage.strip(), 0)


def decode_por_stage(value: Any) -> str:
    mapping = {0: "Pre-Stage", 1: "Stage 0", 2: "Stage 1", 3: "Stage 2"}
    try:
        return mapping.get(int(value), f"unknown({value})")
    except (TypeError, ValueError):
        return f"unknown({value})"


def normalize_root(value: Any, *, allow_empty: bool = True, allow_invalid: bool = False) -> str:
    if value is None:
        return "0" * 64 if allow_empty else ""
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if text == "" and allow_empty:
        return "0" * 64
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        if allow_invalid:
            return "0" * 64
        raise ValueError(f"invalid 32-byte hex root: {value!r}")
    return text


def parse_snapshot_time(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value.strip():
        return 0
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return 0


def summarize_verifications(verifier_results: Any) -> tuple[int, int]:
    """Mirror upstream SummarizeVerifications: bitfield + deprecated coverageBps."""
    summary = 0
    max_cov = 0.0
    rows = verifier_results if isinstance(verifier_results, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cov = row.get("coverage")
        if isinstance(cov, (int, float)) and cov > max_cov:
            max_cov = float(cov)
        verifier_id = row.get("verifierId") or row.get("id")
        verdict = str(row.get("verdict") or row.get("status") or "").lower()
        passed = verdict in {"pass", "passed", "ok", "success"}
        if not passed:
            continue
        if verifier_id == "internal-consistency":
            summary |= 1 << 0
        elif verifier_id == "onchain-balance-hot":
            summary |= 1 << 1
        elif verifier_id == "solvency-claim":
            summary |= 1 << 2
    if summary & (1 << 0):
        summary |= 1 << 3
    return summary, int(max_cov * 10000)


def as_u16(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 0:
        return 0
    if number > 65535:
        return 65535
    return number


USD_UNAVAILABLE = 0
RATIO_UNAVAILABLE = 65535
_MAJOR = ("BTC", "ETH", "USDT", "USDC")


def whole_usd(value: Any) -> int:
    """Nearest whole USD. None / non-positive → 0 (unavailable). Tiny positives encode as 1."""
    if value is None:
        return USD_UNAVAILABLE
    try:
        number = float(value)
    except (TypeError, ValueError):
        return USD_UNAVAILABLE
    if number != number or number <= 0:
        return USD_UNAVAILABLE
    rounded = int(round(number))
    if rounded < 1:
        return 1
    return rounded


def major_ratio_bps(assessment: dict, coin: str) -> int:
    rows = assessment.get("majorCoinReserveRates") or []
    if not isinstance(rows, list):
        return RATIO_UNAVAILABLE
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("coin") or "").upper() != coin:
            continue
        try:
            rate = float(row.get("reserveRate"))
        except (TypeError, ValueError):
            return RATIO_UNAVAILABLE
        if rate < 0:
            return RATIO_UNAVAILABLE
        bps = int(round(rate * 10000))
        if bps > 65534:
            return 65534
        return bps
    return RATIO_UNAVAILABLE


def build_anchor_args(assessment: dict, assessment_sha256: str) -> dict:
    """Return json-args for por_digest_anchor::anchor (schema v7 + assessment digest)."""
    snapshot = assessment.get("snapshot") if isinstance(assessment.get("snapshot"), dict) else {}
    artifacts = assessment.get("artifacts") if isinstance(assessment.get("artifacts"), dict) else {}
    exchange = assessment.get("exchange")
    snapshot_id = snapshot.get("id")
    if not exchange or snapshot_id is None:
        raise ValueError("assessment is missing exchange or snapshot.id")
    methodology = assessment.get("methodologyVersion")
    if not methodology:
        raise ValueError("assessment is missing methodologyVersion")
    artifact_root = normalize_root(artifacts.get("artifactBundleRoot"), allow_empty=False)
    verification_root = normalize_root(artifacts.get("verificationBundleRoot"), allow_empty=False)
    exchange_root = normalize_root(
        snapshot.get("exchangeMerkleRoot"), allow_empty=True, allow_invalid=True
    )
    verdict_summary, coverage_bps = summarize_verifications(assessment.get("verifierResults"))
    if "coverageBps" in assessment:
        coverage_bps = as_u16(assessment.get("coverageBps"), coverage_bps)
    return {
        "exchange": str(exchange).lower(),
        "snapshot_id": str(snapshot_id),
        "period_seq": int(snapshot.get("periodSeq") or 0),
        "snapshot_time": parse_snapshot_time(snapshot.get("snapshotTime")),
        "btc_block_height": int(snapshot.get("btcBlockHeight") or 0),
        "exchange_merkle_root": exchange_root,
        "artifact_bundle_root": artifact_root,
        "verification_bundle_root": verification_root,
        "verdict_summary": int(verdict_summary),
        "coverage_bps": as_u16(coverage_bps),
        "por_stage": encode_por_stage(assessment.get("porStage")),
        "effective_por": bool(assessment.get("effectivePoR")),
        "wallet_coverage_bps": as_u16(assessment.get("walletCoverageBps")),
        "reserve_coverage_bps": as_u16(assessment.get("reserveCoverageBps")),
        "assessment_sha256": normalize_root(assessment_sha256, allow_empty=False),
        "methodology_version": str(methodology),
        "custody_risk_score": custody_risk_score_for_anchor(assessment),
        "total_liability_usd": whole_usd(assessment.get("totalLiabilityUsd")),
        "total_reserve_usd": whole_usd(assessment.get("totalReserveUsd")),
        "btc_reserve_ratio_bps": major_ratio_bps(assessment, "BTC"),
        "eth_reserve_ratio_bps": major_ratio_bps(assessment, "ETH"),
        "usdt_reserve_ratio_bps": major_ratio_bps(assessment, "USDT"),
        "usdc_reserve_ratio_bps": major_ratio_bps(assessment, "USDC"),
    }
