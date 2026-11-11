---
name: por-risk-control
description: Score CEX custody risk from a public Proof-of-Reserves assessment, its sha256, and a NEAR digest view. Use when a user asks for an exchange's latest PoR snapshot time, a multi-month PoR summary, or a 0–100 custody risk score before choosing a CEX hedge venue. Does not place orders, hold keys, call NEAR Intents, or decide the trade.
---

# PoR risk control

This skill scores custody risk. It does not decide whether to trade. The final trade decision stays with the user or their agent.

Run the script and read the JSON. Use `riskScore`, `riskLevel`, and `factors`. There is no `decision` field. Do not invent allow, reduce, or block.

## Dependencies (read path)

| Need | Notes |
| --- | --- |
| `python3` | stdlib only for scoring + RPC |
| `bash` | `por-check.sh` wrapper |
| This repo | `fixtures/digests.json`, `vendor/ardmere.github.io` assessments |
| **Public NEAR testnet RPC** | Default `https://rpc.testnet.fastnear.com` (fallback `rpc.testnet.near.org`); override with `POR_NEAR_RPC_URL` |
| **`near` CLI** | **Not required** for read/score (`por-check`, `por-exchange-report`). Still required only for **owner** writes (`near_digest.py reconcile --apply`) |

## Read the digest from testnet

Set `POR_NEAR_CONTRACT` to the deployed testnet account. The view uses **JSON-RPC `query` + `call_function`** (`scripts/near_rpc.py`), not `near-cli`:

```bash
POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  skills/por-risk-control/scripts/por-check.sh \
  vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Default live testnet contract when unset in examples: `por-digest-v5-index.ardmere-demo-1fc2.testnet` (schema v5; `por-check.sh` sets `scoringSource: "onchain"` when `custody_risk_score` is present).

Equivalent one-liner without the script (same contract/method as README Step 1):

```bash
curl -sS -X POST "${POR_NEAR_RPC_URL:-https://rpc.testnet.fastnear.com}" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"query","params":{"request_type":"call_function","finality":"final","account_id":"por-digest-v5-index.ardmere-demo-1fc2.testnet","method_name":"get","args_base64":"'$(printf '%s' '{"exchange":"okx","snapshot_id":"508756245"}' | base64 -w0)'"}}'
```

## Official sources (verify alongside the score)

Every `por-check` JSON includes **`officialSources`** so the user can cross-check exchange-published data, not only the ardmere score:

| Field | Meaning |
| --- | --- |
| `exchangePorPage` | Exchange official PoR landing page (`config/exchanges/registry.yaml`) |
| `publicArtifacts[]` | Permissionless URLs from the assessment (`artifacts.present`: BAPI, wallet zip, …) |
| `upstreamVerifierRepos[]` | Exchange OSS verifier repos (registry) |
| `ardmereAssessment` / `ardmereTransparencyReport` | Links to the vendored public evaluation files |

When answering, **always cite** `exchangePorPage` and at least the main `publicArtifacts` URLs when giving a custody risk score, and say that the score is ardmere's recompute/chain read—not the exchange's own rating.

## Exchange questions (latest time, recent months)

When the user asks **when the latest PoR was published** or to **evaluate recent PoR reports** for one exchange, run from the repo root (after `git clone --recurse-submodules`):

```bash
POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  python3 skills/por-risk-control/scripts/por-exchange-report.py binance

POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  python3 skills/por-risk-control/scripts/por-exchange-report.py binance --months 3
```

The script calls `get_latest` over public RPC for the latest snapshot time and id, then runs `por-check.sh` on each assessment in `fixtures/digests.json` for that exchange within the window. JSON (`--json`) and text output include **`officialSources`** per snapshot. Answer in plain language:

- **Publish time** means the assessment `snapshotTime` (exchange snapshot UTC), confirmed by the chain record's `snapshot_time` for `get_latest`.
- **Scores** describe how far the public disclosure is from third-party recompute (`UNVERIFIABLE`, stage, flags). They do not prove reserves.
- Say when every row shows `near.matches: true` (file hash equals on-chain `assessment_sha256`).

Add `--json` when another tool consumes the output.

Read the `near` block to see where the view came from:

| Field | Meaning |
| --- | --- |
| `near.network` | `testnet` for the live contract, `sandbox` for the recording |
| `near.live` | `true` only when a view call answered in this run |
| `near.source` | `testnet-rpc` when read via JSON-RPC |
| `near.contract` | the account the `get` was sent to |
| `officialSources` | exchange PoR page, artifact URLs, ardmere report links (see above) |
| `near.matches` | whether the on-chain `assessment_sha256` equals the file sha256 |
| `near` record | schema v5 `SnapshotRecord`: roots, `por_stage` (0–3), coverage bps, and `custody_risk_score` (0–100, or 255 = inconclusive) |
| `near.custodyRiskScore` | same uint8 as on chain |
| `scoringSource` | `onchain` when the score is read from `custody_risk_score`; otherwise `recomputed` from the assessment file |

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

After upgrading the contract to schema v5, backfill scores on snapshots that were anchored as v4:

```bash
python3 scripts/near_digest.py --contract <contract.testnet> backfill-custody          # dry run
python3 scripts/near_digest.py --contract <contract.testnet> backfill-custody --apply  # send
```

The reconciliation is idempotent: bytes already on chain are skipped, different bytes fail instead of overwriting. `scripts/upstream_check.py` reports drift between the submodule and the manifest and never touches NEAR.

## Verifying the user's own inclusion proof

A custody score describes an exchange. It says nothing about whether *this* user's balance was in the snapshot. That is what the user's own proof is for, and it is verified locally:

```bash
skills/por-risk-control/scripts/inclusion_check.py --list-schemes
skills/por-risk-control/scripts/inclusion_check.py \
  --exchange bybit \
  --assessment vendor/ardmere.github.io/docs/reports/bybit/2026102706-assessment.json \
  ~/Downloads/myProof.json
```

The proof is the file the exchange hands a logged-in user. It contains the account id, nonce and balances, so:

- Read it from the user's own machine. Never ask them to paste it into chat, commit it, or upload it anywhere.
- The script prints verdicts only and never echoes the account id, nonce or balances.
- Nothing is written next to the proof; the script has no output file.

Supported schemes are `bitget`, `bingx`, `mexc` and `bybit`, ported from `vendor/ardmere.github.io/internal/exchanges/*/merkle` and tested against the same fixtures (see `tests/test_inclusion.py`).

Output shape:

| Field | Meaning |
| --- | --- |
| `verdict` | `PASS` or `FAIL` |
| `recomputedRoot` | the root the proof's own path produces |
| `findings[]` | `SELF_HASH_MISMATCH`, `PATH_MISMATCH`, `BALANCE_MISMATCH`, `HEIGHT_MISMATCH`, `TRUNCATED_HASH`, `ROOT_NOT_BOUND` |
| `binding` | whether `recomputedRoot` equals the merkle root the assessment publishes |
| `scope` | what a pass does and does not mean |

`binding.matches` is `null` when the assessment publishes no exchange merkle root. Do not report `null` as a match, and do not treat a `PASS` with `matches: null` as proof of anything beyond the user's own leaf. Today only Bitget's assessment carries a published root, so the other three can be verified but not bound to a snapshot.

`TRUNCATED_HASH` matters when quoting a result: Bitget keeps 64 bits and MEXC 128 bits of SHA-256, so their passes are weaker than Bybit's or BingX's full-width ones.

`ROOT_WIDTH_MISMATCH` means the assessment publishes a root of a different width than the scheme produces, so the two cannot be compared at all. Today that is true for Bitget: the assessment's `exchangeMerkleRoot` is 256 bits while its user proofs produce 64-bit roots. The upstream Go verifier compares them as strings and therefore reports a mismatch; this script reports the width problem instead of blaming the user's proof. Treat such a binding as unknown, not as a failure of the user's file.

A pass proves the user's leaf is in the tree that produced the root. It does not prove the exchange holds enough reserves for everyone, and it does not change the custody score.
