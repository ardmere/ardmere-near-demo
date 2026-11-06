# Custody risk score

The skill scores custody risk. It does not decide whether to trade. There is no `decision` field and no allow / reduce / block output. `por-check.sh` and the dashboard both use this table. A second run has to land on the same integers.

`riskScore` is an integer from 0 to 100. Sum the applied `factors[].delta` values. If that sum is above 100, reduce deltas from the last factor backward until the sum is 100, and say so in the note. `riskScore` is that sum.

`riskLevel` starts from the score, then a floor can raise it:

| Score | Level |
| --- | --- |
| 0–24 | `low` |
| 25–49 | `medium` |
| 50–79 | `high` |
| 80–100 | `critical` |

Floors, applied after the band: a blocking flag raises the level to at least `high`. Stage below effective PoR raises the level to at least `medium`. A hash failure is `critical`.

## Hash failure

If the assessment file is missing, `fixtures/digests.json` cannot be read, the file sha256 differs from `fixtures/digests.json`, or a NEAR `get` result is present and its `assessment_sha256` differs from the file sha256: one factor, delta **100**, level `critical`. Flag points are not added. The factor id is the first failure in this order:

| Id | When |
| --- | --- |
| `FILE_MISSING` | The assessment path does not exist |
| `DIGESTS_UNREADABLE` | `fixtures/digests.json` is missing or is not the expected JSON |
| `DIGEST_MISMATCH` | The file sha256 differs from the `digests.json` row, or the row is missing |
| `NEAR_GET_MISMATCH` | A `get` view for this exchange and snapshot is present and the hash differs |
| `NEAR_GET_MISSING` | The view came from a live contract (`near.live` is `true`) and that contract holds no record for this snapshot |

A missing NEAR view from the sandbox recording is not a mismatch. The recording is optional, so its silence says nothing about the chain. `NEAR_GET_MISSING` applies only to a live `get` that answered "not found": the snapshot is not anchored yet. Comparison is on the 32-byte hex, case-insensitive, `0x` ignored.

## Blocking flags

These ids are the public framework's high flags that block a stage. Each occurrence in `riskFlags` adds **40**.

| Id | Delta |
| --- | --- |
| `UNVERIFIABLE` | 40 |
| `LOGIN_WALL` | 40 |
| `SAMPLE_ONLY` | 40 |
| `BLACK_BOX_INCLUSION_PROOF` | 40 |

## Stage below effective PoR

If the hash matches and `porStage` is `Stage 0` or `Pre-Stage` (the exact value, or that value followed by a space, hyphen, or em dash), add one factor:

| Id | Delta |
| --- | --- |
| `STAGE_BELOW_EFFECTIVE_POR` | 35 |

## Non-blocking flags

Applied only when the hash matches. Each remaining `riskFlags` entry adds the delta below. The sum of these deltas is capped at **20**. That cap is the base 0–20 for a matching hash with `effectivePoR` true and no blocking flag. Points come from the flag id. Severity is only the fallback for an id that is not in this table.

| Id | Delta |
| --- | --- |
| `STAGE_BLOCKED` | 8 |
| `NO_WALLET_OWNERSHIP_PROOF` | 8 |
| `OPAQUE_TRUSTED_SETUP` | 8 |
| `BUSINESS_CONSTRAINT_GAP` | 8 |
| `NEGATIVE_NET_WORTH_DUMMY_USER_RISK` | 8 |
| `IMPLEMENTATION_SEMANTICS_RISK` | 8 |
| `HIGH_FRICTION_INCLUSION_PROOF` | 5 |
| `NO_INDEPENDENT_REVIEW` | 5 |
| `NO_CANONICAL_ANCHOR` | 5 |
| `CONFLICT_OF_INTEREST_UNDISCLOSED` | 5 |
| `HIGH_FREQUENCY_GAP` | 5 |

Fallback when the id is not listed above and is not blocking:

| Severity on the flag | Delta |
| --- | --- |
| `critical` | 10 |
| `high` | 8 |
| `medium` | 5 |
| `low` | 2 |
| `info` | 1 |
| missing or anything else | 5 |

## Order

1. Hash failure, if any, and stop.
2. Blocking flags, in `riskFlags` order.
3. Stage factor, if the stage is below effective PoR.
4. Non-blocking flags, in `riskFlags` order, capped at 20.

The note on a flag factor is the assessment's `message` when it has one.

## Fixtures copied from github.io `57a5bcd`

These are the scores of the unmodified files. Do not edit the JSON to change them.

| File | Flags | Score | Level |
| --- | --- | --- | --- |
| OKX `508756245` | `NO_CANONICAL_ANCHOR` +5, `HIGH_FREQUENCY_GAP` +5. Stage 1, `effectivePoR` true, hash matches | 10 | `low` |
| KuCoin `20261031` | `UNVERIFIABLE` +40, `STAGE_BELOW_EFFECTIVE_POR` +35. Stage 0, `effectivePoR` false, hash matches | 75 | `high` |
