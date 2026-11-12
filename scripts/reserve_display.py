"""Human labels for selfReportedReserves tables (por-risk-control skill)."""

from __future__ import annotations

from typing import Any

UNAVAILABLE = "Unavailable"


def fmt_reserve_usd(value: Any) -> str:
    """Format USD totals; null / missing → Unavailable."""
    if value is None:
        return UNAVAILABLE
    try:
        number = float(value)
    except (TypeError, ValueError):
        return UNAVAILABLE
    if number >= 1e9:
        return f"${number / 1e9:.2f}B"
    if number >= 1e6:
        return f"${number / 1e6:.2f}M"
    return f"${number:,.0f}"


def fmt_total_reserve_ratio_pct(value: Any) -> str:
    if value is None or value == "":
        return UNAVAILABLE
    if isinstance(value, str):
        return value
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return UNAVAILABLE


def fmt_major_coin_ratio(row: dict | None) -> str:
    if not isinstance(row, dict) or not row.get("available"):
        return UNAVAILABLE
    pct = row.get("reserveRatioPct")
    if pct is None or pct == "":
        return UNAVAILABLE
    return str(pct)
