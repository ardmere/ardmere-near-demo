#!/usr/bin/env python3
"""Verify a proof-of-reserves user inclusion proof locally.

The proof file is the one the exchange gives a logged-in user (myProof.json and
friends). It contains the user's account id, nonce and balances, so this script
prints verdicts only and never writes the proof anywhere else.

Each exchange hashes and folds its own way; the adapters below reproduce the
schemes that ardmere already validates in Go (vendor/ardmere.github.io/internal).
Parity with those Go implementations is checked against the upstream fixtures in
tests/test_inclusion.py.

    inclusion_check.py --exchange bitget <proof.json>
    inclusion_check.py --list-schemes
"""

import argparse
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMES = {}
# Root width in bytes for each scheme, used when comparing against a published root.
ROOT_WIDTH = {
    "bitget": 8,   # SHA-256 truncated to 16 hex chars
    "bingx": 32,   # full SHA-256
    "mexc": 16,    # SHA-256 truncated to 32 hex chars
    "bybit": 32,   # full SHA-256
}


class ProofError(ValueError):
    pass


def sha256_hex(text):
    return hashlib.sha256(text.encode()).hexdigest()


def truncated(text, hex_len):
    return sha256_hex(text)[:hex_len]


def dec(value):
    """Parse a balance the way shopspring/decimal does, tolerating junk as zero."""
    if value is None:
        return Decimal(0)
    text = str(value).strip()
    if not text:
        return Decimal(0)
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal(0)


def plain(value):
    """Format like shopspring Decimal.String(): no exponent, no trailing zeros."""
    amount = dec(value)
    if amount == 0:
        return "0"
    text = format(amount.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fixed(value, scale):
    """Render a balance at a fixed scale, like shopspring Decimal.StringFixed (never exponent)."""
    quantum = Decimal(1).scaleb(-scale)
    return format(dec(value).quantize(quantum), "f")


def scheme(*names):
    def register(fn):
        for name in names:
            SCHEMES[name] = fn
        return fn
    return register


def result(exchange, verdict, root, detail, findings, extra=None):
    doc = {
        "exchange": exchange,
        "verdict": verdict,
        "rootWidth": ROOT_WIDTH.get(exchange),
        "recomputedRoot": root,
        "detail": detail,
        "findings": findings,
    }
    if extra:
        doc.update(extra)
    return doc


# --- bitget: SHA-256 truncated to 64 bits, balances folded with the path ---------

BITGET_HEX = 16


def bitget_json_balances(balances):
    keys = sorted(balances)
    parts = [f'"{k}":"{plain(balances[k])}"' for k in keys]
    return "{" + ",".join(parts) + "}"


def bitget_leaf(encrypt_uid, nonce, balances):
    return truncated(f"{encrypt_uid},{nonce},{bitget_json_balances(balances)}", BITGET_HEX)


def bitget_inner(left, right, balances, level):
    return truncated(f"{left}{right},{bitget_json_balances(balances)},{level}", BITGET_HEX)


def bitget_add(a, b):
    out = dict(a)
    for key, value in b.items():
        out[key] = plain(dec(out.get(key, 0)) + dec(value))
    return out


@scheme("bitget")
def verify_bitget(proof):
    findings = []
    uid = proof.get("encryptUid") or ""
    nonce = proof.get("nonce") or ""
    balances = proof.get("balances") or {}
    path = proof.get("merkelPath") or proof.get("merklePath") or []
    root = (proof.get("root") or {}).get("hash") or ""

    if not uid or not nonce or not balances:
        raise ProofError("proof is missing encryptUid, nonce or balances")
    if not path or not root:
        raise ProofError("proof is missing merkelPath or root.hash")

    current = bitget_leaf(uid, nonce, balances)
    declared = proof.get("hash") or ""
    if declared and declared != current:
        return result("bitget", "FAIL", None, "self hash does not match encryptUid+nonce+balances",
                      findings + [{"id": "SELF_HASH_MISMATCH", "note": "recomputed leaf differs from proof.hash"}])

    running = dict(balances)
    for sibling in path:
        sibling_balances = sibling.get("balances") or {}
        sib_hash = sibling.get("hash") or ""
        level = sibling.get("level") or 0
        if not sib_hash or level <= 0:
            raise ProofError("path node is missing hash or level")
        running = bitget_add(running, sibling_balances)
        position = str(sibling.get("position") or "").strip().lower()
        if position in ("left", "l"):
            current = bitget_inner(sib_hash, current, running, level)
        else:
            current = bitget_inner(current, sib_hash, running, level)

    root_balances = (proof.get("root") or {}).get("balances") or {}
    if current != root:
        return result("bitget", "FAIL", current, "path does not recompute to root.hash",
                      findings + [{"id": "PATH_MISMATCH", "note": f"expected {root}"}])
    if {k: plain(v) for k, v in running.items()} != {k: plain(v) for k, v in root_balances.items()}:
        return result("bitget", "FAIL", current, "folded balances differ from the root node balances",
                      findings + [{"id": "BALANCE_MISMATCH", "note": "sum along the path does not equal root balances"}])

    findings.append({
        "id": "TRUNCATED_HASH",
        "note": f"Bitget truncates SHA-256 to {BITGET_HEX} hex chars (64 bits); a pass is weak evidence",
    })
    return result("bitget", "PASS", current, "path recomputes to the proof root and balances add up",
                  findings, {"auditId": proof.get("auditId")})


# --- bingx: plain SHA-256 concatenation, no balance fold ------------------------


def bingx_path_entries(path_text):
    for part in str(path_text).split(","):
        part = part.strip()
        if not part:
            continue
        chunks = [c.strip().lower() for c in part.split(":")]
        if len(chunks) != 2:
            raise ProofError(f"path entry must be side:hash or hash:side, got {part!r}")
        first, second = chunks
        if first in ("l", "r"):
            yield first, second
        elif second in ("l", "r"):
            yield second, first
        else:
            raise ProofError(f"path entry has no side marker: {part!r}")


@scheme("bingx")
def verify_bingx(proof):
    leaf = proof.get("merkleLeaf") or ""
    if not leaf and proof.get("assetLine"):
        leaf = sha256_hex(proof["assetLine"])
    if not leaf:
        raise ProofError("proof is missing merkleLeaf (or assetLine to hash)")
    root = str(proof.get("merkleRoot") or "").strip().lower()
    root = root[2:] if root.startswith("0x") else root
    if not root:
        raise ProofError("proof is missing merkleRoot to compare against")

    current = leaf.lower()
    for side, sibling in bingx_path_entries(proof.get("merklePath") or ""):
        current = sha256_hex(sibling + current) if side == "l" else sha256_hex(current + sibling)

    if current != root:
        return result("bingx", "FAIL", current, "path does not recompute to merkleRoot",
                      [{"id": "PATH_MISMATCH", "note": f"expected {root}"}])
    return result("bingx", "PASS", current, "leaf and path recompute to merkleRoot",
                  [], {"auditId": proof.get("auditId")})


# --- mexc: SHA-256 truncated to 128 bits, balances folded -----------------------

MEXC_HEX = 32
MEXC_ASSETS = ("BTC", "USDT", "ETH", "USDC")


def mexc_raw_balances(balances):
    return ",".join(f"{k}:{balances[k]}" for k in sorted(balances))


def mexc_plain_balances(balances):
    return ",".join(f"{k}:{plain(balances[k])}" for k in sorted(balances))


def mexc_inner(left, right, balances, hex_len=MEXC_HEX):
    return truncated(f"{left},{right},{mexc_plain_balances(balances)}", hex_len)


def mexc_merge(a, b):
    out = dict(a)
    for key, value in b.items():
        out[key] = plain(dec(out.get(key, 0)) + dec(value))
    return out


@scheme("mexc")
def verify_mexc(proof):
    path = proof.get("pathList") or []
    self_node = proof.get("self") or {}
    if not path or not self_node.get("hash"):
        raise ProofError("proof is missing pathList or self.hash")
    if not self_node.get("proofId") or not self_node.get("accountId"):
        raise ProofError("proof is missing self.proofId or self.accountId")

    balances = self_node.get("balances") or {}
    content = f"{self_node['proofId']},{self_node['accountId']},{mexc_raw_balances(balances)}"
    if truncated(content, MEXC_HEX) != self_node["hash"]:
        return result("mexc", "FAIL", None, "self hash does not match proofId+accountId+balances",
                      [{"id": "SELF_HASH_MISMATCH", "note": "recomputed leaf differs from self.hash"}])

    root_node = path[-1]
    root_hash = root_node.get("hash") or ""
    if not root_hash:
        raise ProofError("proof is missing the root hash")
    depth = root_node.get("level") or 0

    level_map = {node.get("level"): node for node in path}
    current = {
        "level": self_node.get("level") or 0,
        "type": self_node.get("type") or 1,
        "hash": self_node["hash"],
        "balances": dict(balances),
    }
    left = right = None
    for level in range(depth):
        sibling = level_map.get(level)
        if sibling is None:
            sib_type = 2 if current["type"] == 1 else 1
            sib = {"type": sib_type, "hash": "", "balances": {}}
        else:
            sib = {
                "type": sibling.get("type") or 1,
                "hash": sibling.get("hash") or "",
                "balances": dict(sibling.get("balances") or {}),
            }
        if current["type"] == 1:
            left, right = current, sib
        else:
            left, right = sib, current

        parent_level = level + 1
        parent = level_map.get(parent_level)
        if parent is None:
            parent_type = 1
        else:
            parent_type = 2 if (parent.get("type") or 1) == 1 else 1

        folded = mexc_merge(left["balances"], {})
        if str(right.get("hash") or "").strip():
            for asset in MEXC_ASSETS:
                folded.setdefault(asset, "0")
            folded = mexc_merge(folded, right["balances"])
        current = {
            "level": parent_level,
            "type": parent_type,
            "hash": mexc_inner(left["hash"], right["hash"], folded),
            "balances": folded,
        }

    if left is None:
        raise ProofError("path is empty")

    computed = mexc_inner(left["hash"], right["hash"], mexc_merge(left["balances"], right.get("balances") or {}))
    if computed != root_hash:
        return result("mexc", "FAIL", computed, "path does not recompute to the root hash",
                      [{"id": "PATH_MISMATCH", "note": f"expected {root_hash}"}])
    findings = [{
        "id": "TRUNCATED_HASH",
        "note": f"MEXC truncates SHA-256 to {MEXC_HEX} hex chars (128 bits); a pass is weak evidence",
    }]
    return result("mexc", "PASS", computed, "leaf and path recompute to the root hash",
                  findings, {"proofId": self_node.get("proofId")})


# --- bybit: 40-asset vector, SHA-256, height carried in the preimage ------------

BYBIT_ASSETS = [
    "AGLA", "APT", "ATOM", "AVAX", "MNT", "BTC", "DOGE", "DOT", "DYDX", "A",
    "ETH", "S", "LTC", "POL", "SOL", "USDC", "USDT", "XRP", "SHIB", "OP",
    "SAND", "LDO", "LINK", "COMP", "UNI", "MANA", "CRV", "BLUR", "SUSHI", "PEPE",
    "WLD", "BEAM", "AGI", "FET", "IMX", "RENDER", "GALA", "APEX", "SHRAP", "USDE",
]
BYBIT_SCALE = 8


def bybit_vector(balances):
    missing = [asset for asset in BYBIT_ASSETS if asset not in balances]
    if missing:
        raise ProofError(f"balance map is missing {len(missing)} of the 40 assets, first: {missing[0]}")
    return {asset: fixed(balances[asset], BYBIT_SCALE) for asset in BYBIT_ASSETS}


def bybit_concat(vector):
    return "".join(vector[asset] for asset in BYBIT_ASSETS)


def bybit_add(a, b):
    return {asset: fixed(dec(a[asset]) + dec(b[asset]), BYBIT_SCALE) for asset in BYBIT_ASSETS}


def bybit_combine(left_hash, right_hash, balances, height):
    return sha256_hex(left_hash + right_hash + bybit_concat(balances) + str(height))


def bybit_sibling_type(sibling):
    if sibling.get("type") == 3:
        return 3
    if sibling.get("type") == 1:
        return 2
    return 1


@scheme("bybit")
def verify_bybit(proof):
    self_node = proof.get("self") or {}
    path = proof.get("path") or []
    if not self_node.get("userHash") or not path:
        raise ProofError("proof is missing self.userHash or path")

    self_balances = bybit_vector(self_node.get("balance") or {})
    expected_self = sha256_hex(self_node["userHash"] + bybit_concat(self_balances))
    if expected_self != self_node.get("hash"):
        return result("bybit", "FAIL", None, "self hash does not match userHash+balances",
                      [{"id": "SELF_HASH_MISMATCH", "note": "recomputed leaf differs from self.hash"}])

    first = path[0]
    if first.get("type") == self_node.get("type"):
        raise ProofError("first path node shares the self node's side")
    path0_balances = bybit_vector(first.get("balance") or {})

    if self_node.get("type") == 1:
        left, right = self_node["hash"], first["hash"]
    else:
        left, right = first["hash"], self_node["hash"]

    node_type = bybit_sibling_type(path[1]) if len(path) > 1 else 0
    node_hash = bybit_combine(left, right, bybit_add(self_balances, path0_balances), 2)
    node_balances = bybit_add(self_balances, path0_balances)
    height = 1

    for index in range(1, len(path) - 1):
        height += 1
        sibling = path[index]
        sib_balances = bybit_vector(sibling.get("balance") or {})
        if sibling.get("type") == 1:
            left, right = sibling["hash"], node_hash
        else:
            left, right = node_hash, sibling["hash"]
        node_type = bybit_sibling_type(path[index + 1])
        node_balances = bybit_add(node_balances, sib_balances)
        node_hash = bybit_combine(left, right, node_balances, height + 1)

    root = path[-1]
    root_balances = bybit_vector(root.get("balance") or {})
    root_hash = root.get("hash") or ""
    findings = []
    if node_hash != root_hash:
        return result("bybit", "FAIL", node_hash, "path does not recompute to the root hash",
                      [{"id": "PATH_MISMATCH", "note": f"expected {root_hash}"}])
    if node_balances != root_balances:
        return result("bybit", "FAIL", node_hash, "folded balances differ from the root node",
                      [{"id": "BALANCE_MISMATCH", "note": "sum along the path does not equal root balances"}])
    if height + 1 != root.get("height"):
        return result("bybit", "FAIL", node_hash, "path height does not reach the root height",
                      [{"id": "HEIGHT_MISMATCH", "note": f"expected {root.get('height')}"}])

    audit = self_node.get("auditId")
    return result("bybit", "PASS", node_hash, "path recomputes to the root hash and balances add up",
                  findings, {"auditId": audit})


# --- binding the proof root to what the assessment published -------------------


def normalize_root(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not text or any(c not in "0123456789abcdef" for c in text):
        return None
    return text


def bind_to_assessment(doc, assessment_path, exchange):
    """Compare the proof root with the merkle root the assessment published, if any."""
    binding = {"assessment": str(assessment_path), "publishedRoot": None, "matches": None, "note": None}
    path = Path(assessment_path)
    if not path.is_file():
        binding["note"] = "assessment file not found; the proof was verified but not bound to a snapshot"
        return binding
    try:
        assessment = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        binding["note"] = "assessment file is unreadable; the proof was verified but not bound"
        return binding
    if assessment.get("exchange") != exchange:
        binding["note"] = f"assessment is for {assessment.get('exchange')!r}, not {exchange!r}; not bound"
        return binding
    snapshot = assessment.get("snapshot") or {}
    published = normalize_root(snapshot.get("exchangeMerkleRoot"))
    binding["snapshotId"] = str(snapshot.get("id")) if snapshot.get("id") is not None else None
    if published is None:
        binding["note"] = "this assessment publishes no exchange merkle root; the proof is not bound to the snapshot"
        return binding
    binding["publishedRoot"] = published
    width = doc.get("rootWidth")
    if isinstance(width, int) and width * 2 != len(published):
        binding["widthsDiffer"] = True
        binding["note"] = (
            f"the assessment publishes a {len(published) * 4}-bit root but this proof scheme "
            f"produces {width * 8}-bit roots; they cannot be compared directly"
        )
    return binding


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("proof", nargs="?", help="path to the proof JSON the exchange gave you")
    parser.add_argument("--exchange", help="bitget, bingx, mexc or bybit")
    parser.add_argument("--assessment", help="assessment JSON to bind the proof root against")
    parser.add_argument("--list-schemes", action="store_true", help="print the supported schemes")
    opts = parser.parse_args(argv)

    if opts.list_schemes:
        print("\n".join(sorted(SCHEMES)))
        return 0
    if not opts.proof or not opts.exchange:
        parser.error("a proof path and --exchange are required")

    exchange = opts.exchange.strip().lower()
    if exchange not in SCHEMES:
        print(f"inclusion_check: unsupported exchange {exchange!r}; try: {', '.join(sorted(SCHEMES))}",
              file=sys.stderr)
        return 2
    try:
        proof = json.loads(Path(opts.proof).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"inclusion_check: cannot read the proof: {exc}", file=sys.stderr)
        return 1
    if not isinstance(proof, dict):
        print("inclusion_check: the proof must be a JSON object", file=sys.stderr)
        return 1

    try:
        doc = SCHEMES[exchange](proof)
    except ProofError as exc:
        print(f"inclusion_check: {exc}", file=sys.stderr)
        return 1

    if opts.assessment:
        binding = bind_to_assessment(doc, opts.assessment, exchange)
        if binding.get("publishedRoot") and doc.get("recomputedRoot") and not binding.get("widthsDiffer"):
            binding["matches"] = normalize_root(doc["recomputedRoot"]) == binding["publishedRoot"]
        doc["binding"] = binding
        if binding.get("widthsDiffer"):
            doc["findings"].append({
                "id": "ROOT_WIDTH_MISMATCH",
                "note": binding["note"],
            })
        elif binding.get("matches") is False:
            doc["verdict"] = "FAIL"
            doc["detail"] = "proof root differs from the merkle root the assessment publishes"
            doc["findings"].append({
                "id": "ROOT_NOT_BOUND",
                "note": f"assessment publishes {binding['publishedRoot']}",
            })

    doc["scope"] = (
        "Proves this account's leaf is in the tree that produced the proof root. "
        "It does not prove the exchange holds enough reserves for everyone."
    )
    json.dump(doc, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if doc["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
