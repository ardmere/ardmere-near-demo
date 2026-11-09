"""Custody risk scoring table (single source for anchor time and por-check).

Mirrors skills/por-risk-control/references/decision-table.md and
vendor/ardmere.github.io/skills/por-custody-risk/scripts/risk_score.py flag deltas.
"""

from __future__ import annotations

BLOCKING = {
    "UNVERIFIABLE": 40,
    "LOGIN_WALL": 40,
    "SAMPLE_ONLY": 40,
    "BLACK_BOX_INCLUSION_PROOF": 40,
}
NONBLOCKING = {
    "STAGE_BLOCKED": 8,
    "NO_WALLET_OWNERSHIP_PROOF": 8,
    "OPAQUE_TRUSTED_SETUP": 8,
    "BUSINESS_CONSTRAINT_GAP": 8,
    "NEGATIVE_NET_WORTH_DUMMY_USER_RISK": 8,
    "IMPLEMENTATION_SEMANTICS_RISK": 8,
    "HIGH_FRICTION_INCLUSION_PROOF": 5,
    "NO_INDEPENDENT_REVIEW": 5,
    "NO_CANONICAL_ANCHOR": 5,
    "CONFLICT_OF_INTEREST_UNDISCLOSED": 5,
    "HIGH_FREQUENCY_GAP": 5,
}
SEVERITY_FALLBACK = {
    "critical": 10,
    "high": 8,
    "medium": 5,
    "low": 2,
    "info": 1,
}
NONBLOCKING_CAP = 20
SCORE_CAP = 100
RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Sepolia / NEAR schema v5: uint8 0–100, 255 = inconclusive (no score committed).
CUSTODY_RISK_INCONCLUSIVE = 255


def band(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def at_least(level: str, floor: str) -> str:
    return level if RANK[level] >= RANK[floor] else floor


def stage_below(stage) -> bool:
    if not isinstance(stage, str):
        return False
    text = stage.strip()
    lowered = text.lower()
    if lowered == "pre-stage" or lowered.startswith(("pre-stage ", "pre-stage-", "pre-stage—")):
        return True
    return text == "Stage 0" or text.startswith(("Stage 0 ", "Stage 0-", "Stage 0—"))


def cap_sum(factors: list[dict], limit: int) -> None:
    total = sum(item["delta"] for item in factors)
    if total <= limit:
        return
    overflow = total - limit
    for item in reversed(factors):
        if overflow <= 0:
            break
        cut = min(item["delta"], overflow)
        if cut:
            item["delta"] -= cut
            overflow -= cut
            item["note"] = (item["note"] + " Score capped at 100.").strip()


def score_from_assessment(assessment: dict) -> dict:
    """Return riskScore (0–100), riskLevel, and factors from assessment flags/stage."""
    stage = assessment.get("porStage")
    effective = assessment.get("effectivePoR")
    raw_flags = assessment.get("riskFlags")
    flag_rows = raw_flags if isinstance(raw_flags, list) else []
    flag_ids = [f["id"] for f in flag_rows if isinstance(f, dict) and isinstance(f.get("id"), str)]

    factors = []
    saw_blocking = False
    for flag in flag_rows:
        if not isinstance(flag, dict):
            continue
        flag_id = flag.get("id")
        if flag_id not in BLOCKING:
            continue
        saw_blocking = True
        factors.append({
            "id": flag_id,
            "delta": BLOCKING[flag_id],
            "note": flag.get("message") or "Blocking high flag.",
        })
    if stage_below(stage):
        factors.append({
            "id": "STAGE_BELOW_EFFECTIVE_POR",
            "delta": 35,
            "note": f"porStage is {stage}, below effective PoR.",
        })
    nonblocking_added = 0
    for flag in flag_rows:
        if not isinstance(flag, dict):
            continue
        flag_id = flag.get("id")
        if not isinstance(flag_id, str) or flag_id in BLOCKING:
            continue
        full = NONBLOCKING.get(flag_id)
        if full is None:
            full = SEVERITY_FALLBACK.get(str(flag.get("severity") or "").lower(), 5)
        room = NONBLOCKING_CAP - nonblocking_added
        applied = min(full, max(room, 0))
        note = flag.get("message") or "Non-blocking flag."
        if applied < full:
            note = f"{note} Non-blocking contribution capped at 20."
        factors.append({"id": flag_id, "delta": applied, "note": note})
        nonblocking_added += applied

    cap_sum(factors, SCORE_CAP)
    risk_score = sum(item["delta"] for item in factors)
    level = band(risk_score)
    if saw_blocking:
        level = at_least(level, "high")
    if stage_below(stage):
        level = at_least(level, "medium")

    return {
        "riskScore": risk_score,
        "riskLevel": level,
        "factors": factors,
        "porStage": stage,
        "effectivePoR": effective,
        "riskFlags": flag_ids,
    }


def encode_on_chain_score(risk_score: int | None, *, conclusive: bool = True) -> int:
    if not conclusive or risk_score is None:
        return CUSTODY_RISK_INCONCLUSIVE
    score = int(risk_score)
    if score < 0:
        score = 0
    if score > SCORE_CAP:
        score = SCORE_CAP
    return score


def decode_on_chain_score(value) -> tuple[int | None, bool]:
    """Map chain uint8 to (riskScore or None, conclusive)."""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None, False
    if raw == CUSTODY_RISK_INCONCLUSIVE:
        return None, False
    if 0 <= raw <= SCORE_CAP:
        return raw, True
    return None, False


def custody_risk_score_for_anchor(assessment: dict) -> int:
    """Score an assessment that is about to be anchored (always conclusive 0–100)."""
    scored = score_from_assessment(assessment)
    return encode_on_chain_score(scored["riskScore"], conclusive=True)
