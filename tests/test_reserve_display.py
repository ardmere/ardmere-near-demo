import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from reserve_display import (  # noqa: E402
    UNAVAILABLE,
    fmt_major_coin_ratio,
    fmt_reserve_usd,
    fmt_total_reserve_ratio_pct,
)


class ReserveDisplayTest(unittest.TestCase):
    def test_missing_usd(self):
        self.assertEqual(fmt_reserve_usd(None), UNAVAILABLE)

    def test_total_ratio(self):
        self.assertEqual(fmt_total_reserve_ratio_pct(None), UNAVAILABLE)
        self.assertEqual(fmt_total_reserve_ratio_pct("105.33%"), "105.33%")

    def test_major_coin(self):
        self.assertEqual(
            fmt_major_coin_ratio({"available": True, "reserveRatioPct": "100.50%"}),
            "100.50%",
        )
        self.assertEqual(fmt_major_coin_ratio({"available": False}), UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
