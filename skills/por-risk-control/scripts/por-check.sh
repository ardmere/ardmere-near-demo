#!/usr/bin/env bash
# Hash one assessment file, compare fixtures/digests.json and a NEAR get, print a risk score.
# The NEAR view comes from a live testnet contract when POR_NEAR_CONTRACT is set, otherwise
# from the sandbox recording in fixtures/near-views.json.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
export POR_ROOT="$ROOT"
if [[ -z "${POR_DIGESTS+x}" ]]; then
  export POR_DIGESTS="$ROOT/fixtures/digests.json"
fi

if [[ $# -ne 1 ]]; then
  echo "usage: por-check.sh <assessment.json>" >&2
  echo "  POR_NEAR_CONTRACT=<account.testnet> reads the get view from that testnet contract" >&2
  echo "  otherwise the sandbox recording in fixtures/near-views.json is used" >&2
  exit 2
fi

LIVE_VIEW=""
if [[ -n "${POR_NEAR_CONTRACT-}" ]]; then
  _tmp="$(mktemp "${TMPDIR:-/tmp}/por-near-views-XXXXXX")"
  LIVE_VIEW="${_tmp}.json"
  mv "$_tmp" "$LIVE_VIEW"
  trap 'rm -f "$LIVE_VIEW"' EXIT
  python3 "$ROOT/scripts/near_digest.py" \
    --network "${POR_NEAR_NETWORK:-testnet}" \
    --contract "$POR_NEAR_CONTRACT" \
    get "$1" >"$LIVE_VIEW"
  export POR_NEAR_VIEWS="$LIVE_VIEW"
elif [[ -z "${POR_NEAR_VIEWS+x}" ]]; then
  export POR_NEAR_VIEWS="$ROOT/fixtures/near-views.json"
fi

exec python3 - "$1" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

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
RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def band(score):
    if score >= 80:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def at_least(level, floor):
    return level if RANK[level] >= RANK[floor] else floor


def normalize_hex(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        return None
    return text


def stage_below(stage):
    if not isinstance(stage, str):
        return False
    text = stage.strip()
    lowered = text.lower()
    if lowered == "pre-stage" or lowered.startswith(("pre-stage ", "pre-stage-", "pre-stage—")):
        return True
    return text == "Stage 0" or text.startswith(("Stage 0 ", "Stage 0-", "Stage 0—"))


def cap_sum(factors, limit):
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


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def path_matches(listed, given, root):
    listed_posix = str(listed).replace("\\", "/")
    given_path = Path(given)
    candidates = [given_path.as_posix()]
    try:
        candidates.append(given_path.resolve().relative_to(root).as_posix())
    except (OSError, ValueError):
        pass
    for candidate in candidates:
        if candidate == listed_posix or candidate.endswith("/" + listed_posix):
            return True
    return False


def find_digest_row(digests, assessment_path, root):
    rows = digests.get("assessments") if isinstance(digests, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and path_matches(row.get("path", ""), assessment_path, root):
            return row
    return None


def find_get(near_doc, exchange, snapshot):
    if not isinstance(near_doc, dict):
        return None
    for view in near_doc.get("views") or []:
        if not isinstance(view, dict) or view.get("method") != "get":
            continue
        args = view.get("args") or {}
        if args.get("exchange") == exchange and str(args.get("snapshot_id")) == str(snapshot):
            return view
    return None


def integrity(factor_id, note, exchange, snapshot, stage, effective, flags, file_sha, digests_sha, near_obj):
    return {
        "exchange": exchange,
        "snapshot": snapshot,
        "riskScore": 100,
        "riskLevel": "critical",
        "factors": [{"id": factor_id, "delta": 100, "note": note}],
        "porStage": stage,
        "effectivePoR": effective,
        "riskFlags": flags,
        "assessmentSha256": file_sha,
        "digestsSha256": digests_sha,
        "near": near_obj,
    }


def score(assessment_path):
    root = Path(os.environ["POR_ROOT"])
    digests_path = os.environ.get("POR_DIGESTS") or ""
    near_path = os.environ.get("POR_NEAR_VIEWS") or ""
    path = Path(assessment_path)
    digests = load_json(digests_path) if digests_path else None
    near_doc = None
    near_readable = True
    if near_path and Path(near_path).exists():
        near_doc = load_json(near_path)
        near_readable = near_doc is not None

    file_sha = None
    assessment = None
    if path.is_file():
        raw = path.read_bytes()
        file_sha = hashlib.sha256(raw).hexdigest()
        try:
            assessment = json.loads(raw)
        except json.JSONDecodeError:
            assessment = None

    exchange = assessment.get("exchange") if isinstance(assessment, dict) else None
    snapshot_obj = assessment.get("snapshot") if isinstance(assessment, dict) else None
    snapshot = snapshot_obj.get("id") if isinstance(snapshot_obj, dict) else None
    if snapshot is not None:
        snapshot = str(snapshot)
    stage = assessment.get("porStage") if isinstance(assessment, dict) else None
    effective = assessment.get("effectivePoR") if isinstance(assessment, dict) else None
    raw_flags = assessment.get("riskFlags") if isinstance(assessment, dict) else None
    flags = []
    flag_rows = raw_flags if isinstance(raw_flags, list) else []
    for flag in flag_rows:
        if isinstance(flag, dict) and isinstance(flag.get("id"), str):
            flags.append(flag["id"])

    row = find_digest_row(digests, assessment_path, root) if isinstance(digests, dict) else None
    digests_sha = normalize_hex(row.get("sha256")) if isinstance(row, dict) else None
    if isinstance(row, dict):
        if exchange is None:
            exchange = row.get("exchange")
        if snapshot is None and row.get("snapshotId") is not None:
            snapshot = str(row.get("snapshotId"))

    view = find_get(near_doc, exchange, snapshot) if exchange and snapshot else None
    result = view.get("result") if isinstance(view, dict) else None
    near_sha = normalize_hex(result.get("assessment_sha256")) if isinstance(result, dict) else None
    near_present = isinstance(view, dict)
    near_obj = {
        "network": near_doc.get("network") if isinstance(near_doc, dict) else None,
        "source": near_doc.get("source") if isinstance(near_doc, dict) else None,
        "live": near_doc.get("live") if isinstance(near_doc, dict) else None,
        "contract": near_doc.get("contract") if isinstance(near_doc, dict) else None,
        "matches": None,
        "assessmentSha256": near_sha,
    }
    if near_present and file_sha and near_sha:
        near_obj["matches"] = near_sha == file_sha
    elif near_present and file_sha and not near_sha:
        near_obj["matches"] = False

    if not path.is_file():
        return integrity(
            "FILE_MISSING",
            "Assessment file is missing.",
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            None,
            digests_sha,
            near_obj,
        )
    if not digests_path or not Path(digests_path).is_file() or not isinstance(digests, dict):
        return integrity(
            "DIGESTS_UNREADABLE",
            "fixtures/digests.json is missing or unreadable.",
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            file_sha,
            None,
            near_obj,
        )
    if digests_sha is None or digests_sha != file_sha or not isinstance(row, dict):
        note = "File sha256 does not match fixtures/digests.json."
        if near_present and near_sha and near_sha != file_sha:
            note += " NEAR get also disagrees."
        return integrity(
            "DIGEST_MISMATCH",
            note,
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            file_sha,
            digests_sha,
            near_obj,
        )
    if near_path and Path(near_path).exists() and not near_readable:
        return integrity(
            "NEAR_GET_MISMATCH",
            "NEAR view document is unreadable.",
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            file_sha,
            digests_sha,
            near_obj,
        )
    live_source = isinstance(near_doc, dict) and near_doc.get("live") is True
    if live_source and not near_present:
        return integrity(
            "NEAR_GET_MISSING",
            near_doc.get("note") or "The live NEAR contract has no get record for this snapshot.",
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            file_sha,
            digests_sha,
            near_obj,
        )
    if near_present and near_sha != file_sha:
        return integrity(
            "NEAR_GET_MISMATCH",
            "NEAR get assessment_sha256 does not match the file sha256.",
            exchange,
            snapshot,
            stage,
            effective,
            flags,
            file_sha,
            digests_sha,
            near_obj,
        )

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

    cap_sum(factors, 100)
    risk_score = sum(item["delta"] for item in factors)
    level = band(risk_score)
    if saw_blocking:
        level = at_least(level, "high")
    if stage_below(stage):
        level = at_least(level, "medium")
    return {
        "exchange": exchange,
        "snapshot": snapshot,
        "riskScore": risk_score,
        "riskLevel": level,
        "factors": factors,
        "porStage": stage,
        "effectivePoR": effective,
        "riskFlags": flags,
        "assessmentSha256": file_sha,
        "digestsSha256": digests_sha,
        "near": near_obj,
    }


result = score(sys.argv[1])
if "decision" in result:
    raise SystemExit("refusing to print a decision field")
json.dump(result, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
