import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from near_rpc import _decode_result_payload, _parse_view_json, view_get  # noqa: E402
from por_sources import official_sources  # noqa: E402


class NearRpcDecode(unittest.TestCase):
    def test_bytes_list_payload(self):
        sample = {"exchange": "okx", "custody_risk_score": 10}
        raw = list(json.dumps(sample).encode())
        text = _decode_result_payload(raw)
        self.assertEqual(_parse_view_json(text)["exchange"], "okx")


class PorSources(unittest.TestCase):
    def test_okx_artifacts_and_page(self):
        path = ROOT / "vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json"
        assessment = json.loads(path.read_text())
        src = official_sources(assessment, path, repo_root=ROOT)
        self.assertIn("okx.com", src.get("exchangePorPage") or "")
        self.assertTrue(src.get("publicArtifacts"))
        self.assertIsNone(src.get("publicPoRApi"))  # OKX has no documented public PoR API
        binance = ROOT / "vendor/ardmere.github.io/docs/reports/binance/PR12NOV26-assessment.json"
        bsrc = official_sources(__import__("json").loads(binance.read_text()), binance, repo_root=ROOT)
        self.assertTrue((bsrc.get("publicPoRApi") or "").startswith("https://"))


@unittest.skipUnless(os.environ.get("RUN_LIVE_NEAR_RPC") == "1", "set RUN_LIVE_NEAR_RPC=1 for live RPC")
class LiveNearRpc(unittest.TestCase):
    contract = "por-digest-v7-index.ardmere-demo-1fc2.testnet"

    def test_get_okx(self):
        rec = view_get(self.contract, "okx", "508756245")
        self.assertEqual(rec["exchange"], "okx")
        self.assertEqual(int(rec["custody_risk_score"]), 15)
        self.assertEqual(int(rec.get("schema_version", 0)), 7)


if __name__ == "__main__":
    unittest.main()
