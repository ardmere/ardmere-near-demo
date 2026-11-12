import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from reserve_metrics import build_reserve_metrics  # noqa: E402


class ReserveMetricsTest(unittest.TestCase):
    def test_okx_latest_totals_and_majors(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json"
        assessment = json.loads(path.read_text())
        metrics = build_reserve_metrics(assessment)
        self.assertGreater(metrics["totalLiabilityUsd"], 0)
        self.assertGreater(metrics["totalReserveRatio"], 1.0)
        available = [r for r in metrics["majorCoinReserveRates"] if r["available"]]
        self.assertEqual(len(available), 4)
        self.assertFalse(metrics["majorCoinReserveRates"][4]["available"])  # BNB placeholder


if __name__ == "__main__":
    unittest.main()
