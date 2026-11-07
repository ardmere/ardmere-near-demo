"""Tests for the local inclusion proof verifier.

The fixtures under vendor/ardmere.github.io/fixtures are the ones the upstream Go
verifiers test against, and the expected roots are the constants in those Go tests.
If these cases pass, the Python ports agree with the shipped implementations.

Run: python3 -m unittest discover -s tests -v
"""

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "por-risk-control" / "scripts" / "inclusion_check.py"
FIXTURES = ROOT / "vendor" / "ardmere.github.io" / "fixtures"

CASES = [
    # exchange, fixture, expected root from the upstream Go test
    ("bitget", "bitget/merkel_tree_bg.json", "ca89456bb711c913"),
    ("bingx", "bingx/mock_user_proof.json", "e12dba68a58da352b4fd8901f3d989e361cba37ce1fc4b28319b285c42244347"),
    ("mexc", "mexc/merkle_proof.json", "35d01ffef2beec3ff0166c03f3d9b0cc"),
    ("bybit", "bybit/mock_user_merkle_tree_path_40_v5.json",
     "c91d5de0554f97244e4d9f8056fad70fa0cb2cdb23c290ec597a042645dcbc03"),
]


def run(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


class ParityWithUpstream(unittest.TestCase):
    def test_upstream_fixtures_recompute_the_known_roots(self):
        for exchange, fixture, expected in CASES:
            with self.subTest(exchange=exchange):
                path = FIXTURES / fixture
                if not path.is_file():
                    self.skipTest(f"{path} is absent; run git submodule update --init")
                proc = run("--exchange", exchange, str(path))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                doc = json.loads(proc.stdout)
                self.assertEqual(doc["verdict"], "PASS")
                self.assertEqual(doc["recomputedRoot"], expected)

    def test_truncated_schemes_say_so(self):
        for exchange, fixture, _root in CASES:
            if exchange not in ("bitget", "mexc"):
                continue
            with self.subTest(exchange=exchange):
                path = FIXTURES / fixture
                if not path.is_file():
                    self.skipTest(f"{path} is absent")
                doc = json.loads(run("--exchange", exchange, str(path)).stdout)
                ids = [f["id"] for f in doc["findings"]]
                self.assertIn("TRUNCATED_HASH", ids)

    def test_every_verdict_carries_its_scope(self):
        for exchange, fixture, _root in CASES:
            with self.subTest(exchange=exchange):
                path = FIXTURES / fixture
                if not path.is_file():
                    self.skipTest(f"{path} is absent")
                doc = json.loads(run("--exchange", exchange, str(path)).stdout)
                self.assertIn("does not prove the exchange holds enough reserves", doc["scope"])


class NegativeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = ROOT / "tests" / ".tmp"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        for path in self.tmp.glob("*.json"):
            path.unlink()
        if self.tmp.is_dir() and not any(self.tmp.iterdir()):
            self.tmp.rmdir()

    def write(self, name, doc):
        path = self.tmp / name
        path.write_text(json.dumps(doc))
        return path

    def test_tampered_leaf_fails(self):
        source = FIXTURES / "bingx" / "mock_user_proof.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        proof = json.loads(source.read_text())
        # One character of the leaf changes; the path can no longer reach the root.
        proof["merkleLeaf"] = proof["merkleLeaf"][:-1] + ("0" if proof["merkleLeaf"][-1] != "0" else "1")
        path = self.write("tampered-bingx.json", proof)
        proc = run("--exchange", "bingx", str(path))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["verdict"], "FAIL")

    def test_tampered_bitget_balance_fails(self):
        source = FIXTURES / "bitget" / "merkel_tree_bg.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        proof = json.loads(source.read_text())
        asset = sorted(proof["balances"])[0]
        proof["balances"][asset] = str(float(proof["balances"][asset]) + 1)
        path = self.write("tampered-bitget.json", proof)
        proc = run("--exchange", "bitget", str(path))
        self.assertEqual(proc.returncode, 1)

    def test_absent_root_fails_rather_than_passing(self):
        path = self.write("no-root.json", {"merkleLeaf": "ab" * 32, "merklePath": "", "merkleRoot": ""})
        proc = run("--exchange", "bingx", str(path))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("merkleRoot", proc.stderr)

    def test_unknown_exchange_is_refused(self):
        path = self.write("unknown.json", {})
        proc = run("--exchange", "kraken", str(path))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unsupported exchange", proc.stderr)

    def test_missing_file_is_refused(self):
        proc = run("--exchange", "bingx", str(self.tmp / "absent.json"))
        self.assertEqual(proc.returncode, 1)


class BindingToAssessment(unittest.TestCase):
    def setUp(self):
        self.tmp = ROOT / "tests" / ".tmp"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        for path in self.tmp.glob("*.json"):
            path.unlink()
        if self.tmp.is_dir() and not any(self.tmp.iterdir()):
            self.tmp.rmdir()

    def write(self, name, doc):
        path = self.tmp / name
        path.write_text(json.dumps(doc))
        return path

    def test_root_mismatch_with_assessment_fails(self):
        source = FIXTURES / "bitget" / "merkel_tree_bg.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        # Same width as the scheme's own roots (16 hex chars), different bytes.
        assessment = self.write("bitget-assessment.json", {
            "exchange": "bitget",
            "snapshot": {"id": "202605", "exchangeMerkleRoot": "ab" * 8},
        })
        proc = run("--exchange", "bitget", "--assessment", str(assessment), str(source))
        self.assertEqual(proc.returncode, 1)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["verdict"], "FAIL")
        self.assertFalse(doc["binding"]["matches"])
        self.assertIn("ROOT_NOT_BOUND", [f["id"] for f in doc["findings"]])

    def test_root_width_mismatch_is_not_a_hash_mismatch(self):
        """A published root of a different width cannot be compared; say that, do not fail the proof."""
        source = FIXTURES / "bitget" / "merkel_tree_bg.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        assessment = self.write("bitget-wide.json", {
            "exchange": "bitget",
            "snapshot": {"id": "20261021", "exchangeMerkleRoot": "00" * 24 + "1ef42111598bd71b"},
        })
        proc = run("--exchange", "bitget", "--assessment", str(assessment), str(source))
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["verdict"], "PASS")
        self.assertTrue(doc["binding"]["widthsDiffer"])
        self.assertIsNone(doc["binding"]["matches"])
        self.assertIn("ROOT_WIDTH_MISMATCH", [f["id"] for f in doc["findings"]])

    def test_root_match_with_assessment_passes(self):
        source = FIXTURES / "bitget" / "merkel_tree_bg.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        root = json.loads(source.read_text())["root"]["hash"]
        assessment = self.write("bitget-assessment-ok.json", {
            "exchange": "bitget",
            "snapshot": {"id": "20261021", "exchangeMerkleRoot": root},
        })
        proc = run("--exchange", "bitget", "--assessment", str(assessment), str(source))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(json.loads(proc.stdout)["binding"]["matches"])

    def test_assessment_without_a_root_does_not_claim_a_match(self):
        source = FIXTURES / "bitget" / "merkel_tree_bg.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        assessment = self.write("kucoin-assessment.json", {
            "exchange": "bitget",
            "snapshot": {"id": "20261031", "exchangeMerkleRoot": ""},
        })
        proc = run("--exchange", "bitget", "--assessment", str(assessment), str(source))
        self.assertEqual(proc.returncode, 0)
        binding = json.loads(proc.stdout)["binding"]
        self.assertIsNone(binding["matches"])
        self.assertIn("publishes no exchange merkle root", binding["note"])


class NoSecretsEchoed(unittest.TestCase):
    def test_output_does_not_repeat_account_identifiers(self):
        """A proof carries the user's account id; the verdict must not echo it."""
        source = FIXTURES / "mexc" / "merkle_proof.json"
        if not source.is_file():
            self.skipTest("submodule missing")
        proof = json.loads(source.read_text())
        account = proof["self"]["accountId"]
        proc = run("--exchange", "mexc", str(source))
        self.assertNotIn(account, proc.stdout)
        self.assertNotIn(account, proc.stderr)


if __name__ == "__main__":
    unittest.main()
