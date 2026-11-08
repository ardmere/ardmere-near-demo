"""Unit tests for Sepolia-aligned NEAR anchor arg packing."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from por_snapshot import build_anchor_args, decode_por_stage, encode_por_stage


class PorSnapshot(unittest.TestCase):
    def test_stage_codec(self):
        self.assertEqual(encode_por_stage("Stage 1"), 2)
        self.assertEqual(decode_por_stage(2), "Stage 1")

    def test_okx_assessment_packs_v4_fields(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json"
        assessment = json.loads(path.read_text())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        args = build_anchor_args(assessment, digest)
        self.assertEqual(args["exchange"], "okx")
        self.assertEqual(args["snapshot_id"], "508756245")
        self.assertEqual(args["por_stage"], 2)
        self.assertTrue(args["effective_por"])
        self.assertEqual(args["assessment_sha256"], digest)
        self.assertEqual(len(args["artifact_bundle_root"]), 64)
        self.assertEqual(len(args["verification_bundle_root"]), 64)
        self.assertNotEqual(args["artifact_bundle_root"], "0" * 64)


if __name__ == "__main__":
    unittest.main()
