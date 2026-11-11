"""Read-only NEAR contract views over public JSON-RPC (no near-cli required)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TESTNET_RPCS = (
    "https://rpc.testnet.fastnear.com",
    "https://rpc.testnet.near.org",
)
VIEW_TIMEOUT_SEC = 120


class NearRpcError(RuntimeError):
    pass


def rpc_urls(network: str) -> tuple[str, ...]:
    if network != "testnet":
        raise NearRpcError(f"near_rpc only supports testnet, not {network!r}")
    override = os.environ.get("POR_NEAR_RPC_URL", "").strip()
    if override:
        return (override, *DEFAULT_TESTNET_RPCS)
    return DEFAULT_TESTNET_RPCS


def _decode_result_payload(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, list):
        return bytes(raw).decode("utf-8", "replace")
    if isinstance(raw, str):
        try:
            return base64.b64decode(raw).decode("utf-8", "replace")
        except Exception:
            return raw
    raise NearRpcError(f"unexpected RPC result type: {type(raw).__name__}")


def _parse_view_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise NearRpcError("empty view return")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NearRpcError(f"view return is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise NearRpcError("view return JSON is not an object")
    return value


def view_call(
    contract: str,
    method: str,
    args: dict[str, Any],
    *,
    network: str = "testnet",
    timeout: float = VIEW_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Call a view method; try each RPC until one succeeds."""
    args_b64 = base64.b64encode(json.dumps(args).encode()).decode()
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "por-view",
            "method": "query",
            "params": {
                "request_type": "call_function",
                "finality": "final",
                "account_id": contract,
                "method_name": method,
                "args_base64": args_b64,
            },
        }
    ).encode()
    errors: list[str] = []
    for url in rpc_urls(network):
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                doc = json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        if doc.get("error"):
            errors.append(f"{url}: {doc['error']}")
            continue
        result = doc.get("result") or {}
        wasm_error = result.get("error")
        if isinstance(wasm_error, str) and wasm_error.strip():
            if "snapshot not found" in wasm_error or "digest not found" in wasm_error:
                raise NearRpcError(wasm_error)
            errors.append(f"{url}: {wasm_error}")
            continue
        raw = result.get("result")
        if raw is None and not result.get("logs"):
            errors.append(f"{url}: missing result payload")
            continue
        try:
            text = _decode_result_payload(raw)
            if not text:
                errors.append(f"{url}: empty payload")
                continue
            return _parse_view_json(text)
        except NearRpcError as exc:
            errors.append(f"{url}: {exc}")
            continue
    raise NearRpcError("; ".join(errors) or "no RPC endpoints configured")


def view_get(contract: str, exchange: str, snapshot_id: str, *, network: str = "testnet") -> dict[str, Any]:
    return view_call(
        contract,
        "get",
        {"exchange": exchange, "snapshot_id": str(snapshot_id)},
        network=network,
    )


def view_get_latest(contract: str, exchange: str, *, network: str = "testnet") -> dict[str, Any]:
    return view_call(contract, "get_latest", {"exchange": exchange}, network=network)
