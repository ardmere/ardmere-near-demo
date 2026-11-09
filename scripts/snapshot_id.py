"""Sepolia-aligned snapshot id hashing for NEAR por_digest_anchor (stdlib only)."""

from __future__ import annotations

_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROT = {
    (0, 0): 0, (1, 0): 1, (2, 0): 62, (3, 0): 28, (4, 0): 27,
    (0, 1): 36, (1, 1): 44, (2, 1): 6, (3, 1): 55, (4, 1): 20,
    (0, 2): 3, (1, 2): 10, (2, 2): 43, (3, 2): 25, (4, 2): 39,
    (0, 3): 41, (1, 3): 45, (2, 3): 15, (3, 3): 21, (4, 3): 8,
    (0, 4): 18, (1, 4): 2, (2, 4): 61, (3, 4): 56, (4, 4): 14,
}
_MASK = (1 << 64) - 1


def _rotl(value, shift):
    if not shift:
        return value
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def _keccak_f(state):
    for rnd in range(24):
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(state[x + 5 * y], _ROT[(x, y)])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (
                    b[x + 5 * y]
                    ^ ((~b[(x + 1) % 5 + 5 * y]) & _MASK & b[(x + 2) % 5 + 5 * y])
                )
        state[0] ^= _RC[rnd]
    return state


def keccak256(data: bytes) -> bytes:
    rate = 136
    block = bytearray(data) + b"\x01"
    while len(block) % rate:
        block.append(0)
    block[-1] ^= 0x80
    state = [0] * 25
    for offset in range(0, len(block), rate):
        chunk = block[offset:offset + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(chunk[i * 8:i * 8 + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


def keccak_hex_lower(data: bytes) -> str:
    return keccak256(data).hex()


def exchange_tag_hex(exchange: str) -> str:
    return keccak_hex_lower(str(exchange).encode())


def legacy_snapshot_id_hex(audit_id: str) -> str:
    """Pre–v6 Sepolia / legacy NEAR: keccak256(utf8(auditId))."""
    return keccak_hex_lower(str(audit_id).encode())


def expected_snapshot_id_hex(exchange: str, audit_id: str) -> str:
    """Sepolia v6 expectedSnapshotId: keccak256(lowercase exchange \\x00 auditId)."""
    exchange_lower = str(exchange).lower()
    payload = exchange_lower.encode() + b"\x00" + str(audit_id).encode()
    return keccak_hex_lower(payload)
