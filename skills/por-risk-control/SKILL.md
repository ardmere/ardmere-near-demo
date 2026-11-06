---
name: por-risk-control
description: Score CEX custody risk from a public Proof-of-Reserves assessment, its sha256, and a NEAR digest view. Use when an agent needs a 0–100 custody risk score before a person decides whether a CEX venue is acceptable. Does not place orders, hold keys, call NEAR Intents, or decide the trade.
---

# PoR risk control

This skill scores custody risk. It does not decide whether to trade. The final trade decision stays with the user or their agent.

Run the script and read the JSON. Use `riskScore`, `riskLevel`, and `factors`. There is no `decision` field. Do not invent allow, reduce, or block.

## Read the digest from testnet

Set `POR_NEAR_CONTRACT` to the deployed testnet account. The view comes from a live `get` call, not from a recording:

```bash
POR_NEAR_CONTRACT=por-digest-anchor.ardmere-demo-1fc2.testnet \
  skills/por-risk-control/scripts/por-check.sh \
  vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Read the `near` block to see where the view came from:

| Field | Meaning |
| --- | --- |
| `near.network` | `testnet` for the live contract, `sandbox` for the recording |
| `near.live` | `true` only when a view call answered in this run |
| `near.contract` | the account the `get` was sent to |
| `near.matches` | whether the on-chain sha256 equals the file sha256 |

With `POR_NEAR_CONTRACT` unset, the script falls back to the sandbox recording in `fixtures/near-views.json`. That recording is a replay, not chain state; say so if you quote a score from it.

When the contract is live and holds no record for the snapshot, the score is `100` / `critical` with factor `NEAR_GET_MISSING`. That means "not anchored yet", not "reserves are bad". Report it that way and do not invent a risk judgement.

## Hash and manifest

The script hashes the file, compares the hex to `fixtures/digests.json`, and compares it to the NEAR `get` result. Point values are fixed in `references/decision-table.md`.

Do not place orders. Do not hold keys. Do not call NEAR Intents. Do not treat the score as a transaction.

## Who publishes

This skill only reads. Anchoring a new snapshot is a separate, owner-signed step:

```bash
python3 scripts/near_digest.py --contract <contract.testnet> reconcile          # dry run
python3 scripts/near_digest.py --contract <contract.testnet> reconcile --apply  # send
```

The reconciliation is idempotent: bytes already on chain are skipped, different bytes fail instead of overwriting. `scripts/upstream_check.py` reports drift between the submodule and the manifest and never touches NEAR.
