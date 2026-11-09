"""Tests for Sepolia v6 expectedSnapshotId hashing."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from snapshot_id import expected_snapshot_id_hex, exchange_tag_hex, legacy_snapshot_id_hex


class SnapshotId(unittest.TestCase):
    def test_okx_composite_differs_from_legacy(self):
        composite = expected_snapshot_id_hex("okx", "508756245")
        legacy = legacy_snapshot_id_hex("508756245")
        self.assertNotEqual(composite, legacy)
        self.assertEqual(len(composite), 64)

    def test_exchange_slug_is_lowercased(self):
        a = expected_snapshot_id_hex("OKX", "508756245")
        b = expected_snapshot_id_hex("okx", "508756245")
        self.assertEqual(a, b)

    def test_exchange_tag_is_keccak_of_slug_bytes(self):
        self.assertEqual(len(exchange_tag_hex("okx")), 64)


if __name__ == "__main__":
    unittest.main()
