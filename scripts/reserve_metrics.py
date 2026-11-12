"""Self-reported reserve totals and major-coin ratios for PoR skill output."""

from __future__ import annotations

from typing import Any

# Same four majors as assessment schema and v7 on-chain bps fields.
DISPLAY_COINS = ("BTC", "ETH", "USDT", "USDC")

BPS_UNAVAILABLE = 65535
USD_UNAVAILABLE = 0


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _pct_from_rate(rate: float | None) -> str | None:
    if rate is None:
        return None
    return f"{rate * 100:.2f}%"


def _bps_from_rate(rate: float | None) -> int | None:
    if rate is None:
        return None
    bps = int(round(rate * 10000))
    if bps < 0:
        return None
    if bps > 65534:
        return 65534
    return bps


def _rates_by_coin(assessment: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    rows = assessment.get("majorCoinReserveRates")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        coin = str(row.get("coin") or "").upper()
        if not coin:
            continue
        rate = _num(row.get("reserveRate"))
        out[coin] = {
            "reserveRate": rate,
            "reserveRatioPct": _pct_from_rate(rate),
            "basis": row.get("basis"),
            "selfReported": row.get("selfReported"),
        }
    return out


def _on_chain_bps(near: dict | None, coin: str) -> int | None:
    if not isinstance(near, dict):
        return None
    key = f"{coin.lower()}_reserve_ratio_bps"
    raw = near.get(key)
    try:
        bps = int(raw)
    except (TypeError, ValueError):
        return None
    if bps == BPS_UNAVAILABLE:
        return None
    return bps


def build_reserve_metrics(assessment: dict, *, near_record: dict | None = None) -> dict:
    """Return JSON-friendly self-reported reserves + optional on-chain parity hints."""
    liab = _num(assessment.get("totalLiabilityUsd"))
    res = _num(assessment.get("totalReserveUsd"))
    total_ratio = None
    if liab is not None and liab > 0 and res is not None and res > 0:
        total_ratio = res / liab

    rates = _rates_by_coin(assessment)
    majors = []
    for coin in DISPLAY_COINS:
        row = rates.get(coin)
        rate = row.get("reserveRate") if row else None
        bps_assessed = _bps_from_rate(rate)
        bps_chain = _on_chain_bps(near_record, coin)
        chain_match = None
        if bps_assessed is not None and bps_chain is not None:
            chain_match = bps_assessed == bps_chain
        majors.append(
            {
                "coin": coin,
                "available": rate is not None,
                "reserveRate": rate,
                "reserveRatioPct": _pct_from_rate(rate),
                "basis": row.get("basis") if row else None,
                "onChainBps": bps_chain,
                "onChainMatchesAssessment": chain_match,
            }
        )

    chain_liab = None
    chain_res = None
    if isinstance(near_record, dict):
        try:
            chain_liab = int(near_record.get("total_liability_usd"))
            chain_res = int(near_record.get("total_reserve_usd"))
        except (TypeError, ValueError):
            chain_liab = chain_res = None
        if chain_liab == USD_UNAVAILABLE:
            chain_liab = None
        if chain_res == USD_UNAVAILABLE:
            chain_res = None

    return {
        "semantics": "self_reported",
        "note": (
            "Totals and coin ratios come from the exchange-published assessment JSON "
            "(and matching v7 on-chain fields when anchored). Not verified solvency."
        ),
        "totalLiabilityUsd": liab,
        "totalReserveUsd": res,
        "totalReserveRatio": total_ratio,
        "totalReserveRatioPct": _pct_from_rate(total_ratio),
        "unpricedCoins": assessment.get("unpricedCoins") if isinstance(assessment.get("unpricedCoins"), list) else [],
        "majorCoinReserveRates": majors,
        "onChainTotalLiabilityUsd": chain_liab,
        "onChainTotalReserveUsd": chain_res,
    }
