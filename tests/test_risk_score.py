"""Custody risk scoring matches decision-table examples."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from risk_score import (  # noqa: E402
    CUSTODY_RISK_INCONCLUSIVE,
    custody_risk_score_for_anchor,
    decode_on_chain_score,
    encode_on_chain_score,
    score_from_assessment,
)


class RiskScore(unittest.TestCase):
    def test_encode_inconclusive(self):
        self.assertEqual(encode_on_chain_score(None, conclusive=False), CUSTODY_RISK_INCONCLUSIVE)
        score, ok = decode_on_chain_score(CUSTODY_RISK_INCONCLUSIVE)
        self.assertIsNone(score)
        self.assertFalse(ok)

    def test_okx_example(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json"
        if not path.is_file():
            self.skipTest("submodule missing")
        assessment = json.loads(path.read_text())
        scored = score_from_assessment(assessment)
        self.assertEqual(scored["riskScore"], 15)
        self.assertEqual(scored["riskLevel"], "low")
        self.assertEqual(custody_risk_score_for_anchor(assessment), 15)
        self.assertIn("NO_PUBLIC_POR_API", scored["riskFlags"])

    def test_kucoin_example(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/kucoin/20261031-assessment.json"
        if not path.is_file():
            self.skipTest("submodule missing")
        assessment = json.loads(path.read_text())
        scored = score_from_assessment(assessment)
        self.assertEqual(scored["riskScore"], 100)
        self.assertEqual(scored["riskLevel"], "critical")
        self.assertEqual(scored["scoreSemantics"]["kind"], "transparency_risk")
        self.assertEqual(custody_risk_score_for_anchor(assessment), 100)

    def test_bybit_main_site_parity(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/bybit/2026102706-assessment.json"
        if not path.is_file():
            self.skipTest("submodule missing")
        assessment = json.loads(path.read_text())
        scored = score_from_assessment(assessment)
        self.assertEqual(scored["riskScore"], 100)


if __name__ == "__main__":
    unittest.main()
