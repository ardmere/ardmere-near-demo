---
name: por-risk-control
description: Score CEX custody risk from a public Proof-of-Reserves assessment, its sha256, and an optional NEAR digest view. Use when an agent needs a 0–100 custody risk score before a person decides whether a CEX venue is acceptable. Does not place orders, hold keys, call NEAR Intents, or decide the trade.
---

# PoR risk control

This skill scores custody risk. It does not decide whether to trade. The final trade decision stays with the user or their agent.

Run the script and read the JSON. Use `riskScore`, `riskLevel`, and `factors`. There is no `decision` field. Do not invent allow, reduce, or block.

```bash
skills/por-risk-control/scripts/por-check.sh vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

The script hashes that file, compares the hex to `fixtures/digests.json`, and compares it to the NEAR `get` result in `fixtures/near-views.json` when that view is present. Point values are fixed in `references/decision-table.md`.

Do not place orders. Do not hold keys. Do not call NEAR Intents. Do not treat the score as a transaction.
