# PoR transparency risk score

The skill scores **transparency / disclosure risk** for a published PoR assessment. **Higher `riskScore` = higher risk** (worse public verification posture). It is **not** reserve adequacy, solvency, or “exchange safety.” There is no `decision` field. `por-check.sh` and `scripts/risk_score.py` match **`ardmere.github.io` `skills/por-custody-risk`** (including `derive_disclosure_factors`).

Every JSON output includes **`scoreSemantics`**: `kind: transparency_risk`, `scale` explains higher = worse.

`riskScore` is the sum of `factors[].delta`, capped at **100** by trimming from the last factor backward.

| Score | Level |
| --- | --- |
| 0–24 | `low` |
| 25–49 | `medium` |
| 50–79 | `high` |
| 80–100 | `critical` |

Floors: blocking flag → at least `high`; stage below effective PoR → at least `medium`.

## Order

1. File / digest / NEAR hash integrity (`por-check.sh`). Stop on failure.
2. Blocking flags in `riskFlags` order (+40 each).
3. `STAGE_BELOW_EFFECTIVE_POR` (+35) when applicable.
4. **Derived disclosure gaps** (`derive_disclosure_factors`): `NO_PUBLIC_WALLET_ADDRESS_LIST` (+16), derived `NO_WALLET_OWNERSHIP_PROOF` (+8).
5. Remaining non-blocking `riskFlags`, sum capped at **20**.

## NEAR digest integrity

When `POR_NEAR_CONTRACT` is set, `por-check.sh` compares the file sha256 to `fixtures/digests.json` and to the live `get.assessment_sha256`. Failures use delta **100** (`FILE_MISSING`, `DIGEST_MISMATCH`, `NEAR_GET_MISMATCH`, `NEAR_GET_MISSING`, …). Sandbox `fixtures/near-views.json` without `near.live` does not imply a mismatch.

When the file matches the chain digest but **`custody_risk_score` on NEAR differs** from the recomputed (main-site) score, the output keeps **`scoringSource: recomputed`** and records `near.custodyRiskScoreMismatch`. Re-anchor with `reconcile --apply` after scorer upgrades to refresh on-chain scores.

## Blocking / stage / derived / non-blocking tables

Same integers as [upstream decision-table](https://github.com/ardmere/ardmere.github.io/blob/main/skills/por-custody-risk/references/decision-table.md): blocking +40; stage +35; derived list +16; non-blocking cap 20.

Non-blocking flags include **`NO_PUBLIC_POR_API` (+5)** when `publicPoRApi` is null (no documented permissionless PoR HTTP API).

## Reference scores (file-only, main-site scorer)

| File | Score | Level |
| --- | --- | --- |
| OKX `508756245` | 15 | `low` |
| KuCoin `20261031` | 100 | `critical` |
| Bybit `2026102706` | 100 | `critical` |
| Bitget `20261021` | 100 | `critical` |
| Binance `PR04NOV26` | 91 | `critical` |

Do not treat the number as “exchange safety”; read `factors[]` and `officialSources`.
