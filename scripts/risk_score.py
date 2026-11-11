"""PoR transparency risk scoring (aligned with ardmere.github.io por-custody-risk).

Single source for anchor-time custody_risk_score and por-check recomputation.
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
DISCLOSURE_GAP = 16  # NO_PUBLIC_WALLET_ADDRESS_LIST; not subject to non-blocking cap
SCORE_CAP = 100
RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

SCORE_SEMANTICS = {
    "kind": "transparency_risk",
    "label": "PoR transparency risk",
    "interpretation": (
        "Higher riskScore means worse public disclosure and verification posture "
        "(missing artifacts, anchor gaps, unverifiable dimensions). "
        "It is not reserve adequacy, solvency, or a trading recommendation."
    ),
    "scale": "0=lowest transparency risk in this table, 100=highest",
}

LIST_BLOCK_RULE_IDS = frozenset({
    "floor_no_public_wallet_address_list",
    "floor_no_snapshot_wallet_address_list",
    "floor_no_machine_readable_wallet_list",
})

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


def _checklist_item(assessment: dict, item_id: str):
    for row in assessment.get("checklist") or []:
        if isinstance(row, dict) and row.get("id") == item_id:
            return row
    return None


def has_public_wallet_zip(assessment: dict) -> bool:
    if not isinstance(assessment, dict):
        return False
    present = (assessment.get("artifacts") or {}).get("present") or []
    for art in present:
        if not isinstance(art, dict):
            continue
        kind = str(art.get("kind") or "").lower()
        if "walletzip" in kind.replace("_", ""):
            return True
    return False


def derive_disclosure_factors(assessment: dict, flag_ids: list[str]) -> list[dict]:
    """Supplemental factors from stageBlockedReasons, checklist, and verifierResults."""
    extra: list[dict] = []
    if not isinstance(assessment, dict):
        return extra

    if not has_public_wallet_zip(assessment):
        list_note = None
        for row in assessment.get("stageBlockedReasons") or []:
            if not isinstance(row, dict):
                continue
            if row.get("ruleId") in LIST_BLOCK_RULE_IDS:
                list_note = row.get("reason") or "No public wallet_address_list."
                break
        if list_note is None:
            s1_1 = _checklist_item(assessment, "S1-1")
            if s1_1 and s1_1.get("status") in ("fail", "unverifiable"):
                list_note = s1_1.get("notes") or "wallet_address_list not public or on-chain verifiable."
        if list_note is not None:
            extra.append({
                "id": "NO_PUBLIC_WALLET_ADDRESS_LIST",
                "delta": DISCLOSURE_GAP,
                "note": list_note,
            })

    if "NO_WALLET_OWNERSHIP_PROOF" not in flag_ids:
        own_note = None
        for verdict in assessment.get("verifierResults") or []:
            if not isinstance(verdict, dict):
                continue
            vid = str(verdict.get("verifierId") or "")
            if not vid.startswith("address-ownership"):
                continue
            if verdict.get("verdict") in ("FAIL", "UNVERIFIABLE"):
                own_note = verdict.get("reason") or "address-ownership verifier did not PASS."
                break
        if own_note is None:
            s1_2 = _checklist_item(assessment, "S1-2")
            if s1_2 and s1_2.get("status") in ("fail", "unverifiable"):
                own_note = s1_2.get("notes") or "wallet_ownership_proof not batch-verifiable."
        if own_note is not None:
            extra.append({
                "id": "NO_WALLET_OWNERSHIP_PROOF",
                "delta": NONBLOCKING["NO_WALLET_OWNERSHIP_PROOF"],
                "note": own_note,
            })

    return extra


def attach_score_semantics(payload: dict) -> dict:
    payload["scoreSemantics"] = dict(SCORE_SEMANTICS)
    return payload


def score_from_assessment(assessment: dict) -> dict:
    """Return riskScore (0–100), riskLevel, and factors from assessment flags/stage."""
    stage = assessment.get("porStage")
    effective = assessment.get("effectivePoR")
    raw_flags = assessment.get("riskFlags")
    flag_rows = raw_flags if isinstance(raw_flags, list) else []
    flag_ids = [f["id"] for f in flag_rows if isinstance(f, dict) and isinstance(f.get("id"), str)]

    factors: list[dict] = []
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
    derived_ids: set[str] = set()
    for item in derive_disclosure_factors(assessment, flag_ids):
        factors.append(item)
        derived_ids.add(item["id"])
    nonblocking_added = 0
    for flag in flag_rows:
        if not isinstance(flag, dict):
            continue
        flag_id = flag.get("id")
        if not isinstance(flag_id, str) or flag_id in BLOCKING:
            continue
        if flag_id in derived_ids:
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

    return attach_score_semantics({
        "riskScore": risk_score,
        "riskLevel": level,
        "conclusive": True,
        "factors": factors,
        "porStage": stage,
        "effectivePoR": effective,
        "riskFlags": flag_ids,
    })


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
