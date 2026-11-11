# ardmere NEAR demo

## What this gives NEAR

Ardmere gives NEAR Intents solvers a framework and data to assess CEX custodial risk, and anchors each PoR snapshot on NEAR so verification rests on a consistent on-chain digest.

A NEAR Intents solver is a principal, not a matcher. Its own terms of use put it plainly: the solver "provides and maintains its own Liquidity, at its own cost and under its own control" and "bears all market, inventory, hedging, network, execution, and settlement risk as principal" ([Solver Terms of Use](https://docs.near-intents.org/integration/market-makers/solver-terms-of-use), §7.1 and §7.4).

Filling an intent leaves the solver holding the asset the user sold. It quotes slightly worse than the price it can get by selling that asset elsewhere, and keeps the difference as spread. The venue it sells into is usually a centralized exchange, because that is where depth and latency are. Industry write-ups of intent-based market making describe CEXs as "the primary hedging layer" that "introduces custodial risk and a single point of failure" ([ChainScore](https://chainscorelabs.com/blog/trading/intent-based-architectures/inventory-risk-for-market-makers), [Flip](https://flipdex.co/notes/solver-economics)).

So the solver carries two exposures, and only one of them is on chain:

| Stage | Exposure | Does a reserve assessment help? |
| --- | --- | --- |
| User ↔ solver | none: the swap settles atomically, or it refunds | no |
| Solver ↔ exchange, when hedging | **custodial**: the solver's own capital sits at the venue | **yes** |

The second one is why a reserve assessment has a reader here. A solver choosing where to hedge is choosing where to leave capital, and the 57 assessments vendored in this repo say what is currently checkable about those venues: 50 of 57 are Stage 0 with `UNVERIFIABLE`, meaning a third party cannot recompute the disclosure. That is a fact a solver can cite when picking a hedge venue — the same fact whether the reader is a solver, an agent, or a person.

Ardmere anchors the sha256 of each exchange-published snapshot on NEAR (`por-digest-v5-index.ardmere-demo-1fc2.testnet`, schema v5 with `custody_risk_score`). Anyone verifying a hedge venue can hash the local assessment file and compare it to that on-chain digest — without calling the exchange's API.

What NEAR contributes to this, and what it does not:

- **Contributes:** the record is readable with a `view` call, with no account, no key and no payment ([step 1](#try-it-in-three-steps) below is exactly that). A hosted API can rate-limit, go down, or change its answer; a `view` call at a block height cannot.
- **Contributes:** a named account such as `por-digest-v5-index.ardmere-demo-1fc2.testnet` is checkable by reading it, not by trusting a hex string.
- **Does not contribute:** the record does not verify reserves and does not make any exchange's disclosure recomputable. It records how much is checkable.

The chain is not what makes a solver safer. It is where the measurement about hedge venues can be read by anyone who needs it, without asking permission.

---

Public Proof-of-Reserves from mainstream exchanges, in the assessments vendored here, is mostly not something a third party can recompute. At submodule commit `e4400bd` there are 57 snapshots across 19 exchanges: 50 are Stage 0 and carry `UNVERIFIABLE`. OKX is the only exchange at Stage 1 (7 snapshots), and every one of those still carries `NO_CANONICAL_ANCHOR`.

NEAR stores the sha256 of each listed assessment. A view call returns the same 32 bytes, so the measurement can be re-hashed and re-queried. The contract does not verify reserves. Anchoring a digest does not make a disclosure verifiable, and it is not a record that exchange disclosure advanced.

One contract stores the digest. One skill turns the public flags into a 0–100 score of how far a snapshot is from being recomputable. One page shows that score beside the file hash and the NEAR view.

## Try it in three steps

Judges and machines: these run from a fresh clone, in order, with no account and no key.

**Step 1 — read the on-chain record.** No clone, no toolchain, no credentials. This is a `view` call to NEAR testnet through the public RPC:

```bash
curl -sS -X POST https://rpc.testnet.fastnear.com \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"query","params":{
        "request_type":"call_function","finality":"final",
        "account_id":"por-digest-v5-index.ardmere-demo-1fc2.testnet",
        "method_name":"get_latest",
        "args_base64":"eyJleGNoYW5nZSI6Im9reCJ9"}}'
```

Expected: a `result.result` array that decodes to a `SnapshotRecord` such as `{"exchange":"okx","snapshot_id":"508756245","assessment_sha256":"708b8b8a…ef9a0","custody_risk_score":10,"por_stage":2,"schema_version":5,…}` (`por_stage` 2 = Stage 1). `args_base64` is the base64 of `{"exchange":"okx"}`.

Other read-only methods on the same contract include `get` (exchange + plaintext audit id), `expected_snapshot_id` (Sepolia v6 `expectedSnapshotId` = `keccak256(lowercase exchange ++ 0x00 ++ auditId)`), `get_snapshot_count`, `get_snapshot_id_at`, and `get_snapshot` (exchange tag + snapshot id hash — accepts composite or legacy `keccak256(auditId)`). Each row in `fixtures/digests.json` carries `expectedSnapshotId` for cross-checks; `scripts/snapshot_id.py` computes the same value offline. After `near_digest.py reconcile --apply`, `point_latest` sets which snapshot `get_latest` returns for scoring.

**Step 2 — hash the file the digest claims to cover.** After `git clone --recurse-submodules` (see [Baseline](#baseline)):

```bash
sha256sum vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Expected: `708b8b8aa6a8178df04bcbc2714d0ff8323e37f274f309edc8bc670c377ef9a0`, the same hex Step 1 returned. That is the whole claim: the bytes you hashed are the bytes the chain names.

**Step 3 — score it, against the chain rather than a recording.**

```bash
POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  skills/por-risk-control/scripts/por-check.sh \
  vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Expected: JSON with `"riskScore": 10`, `"riskLevel": "low"`, and `"near": {"live": true, "matches": true, ...}`. `live: true` means the `get` came from the contract in this run, not from `fixtures/near-views.json`.

Swap the file for any row in `fixtures/digests.json` to score another exchange; all 57 listed snapshots are anchored on the same contract.

### What a judge cannot conclude

Step 2 proves the chain names the same bytes as the file. It does not prove the exchange holds reserves. See `THESIS.md` for the claim, what argues against it, and what result would drop it.

## Baseline

Assessment JSON comes from the **git submodule** [`vendor/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io), pinned to the same baseline commit as `fixtures/digests.json` (`sourceCommit`). `fixtures/digests.json` lists every `*-assessment.json` in that submodule, so every exchange the upstream repo has published can be scored and, once anchored, read back with `get` / `get_latest`. The upstream assessment registry stays in that repo. This repo is the NEAR slice plus the skill and dashboard.

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/ardmere/ardmere-near-demo.git
# or, on an existing checkout:
git submodule update --init --recursive
```

To move the submodule to a newer upstream commit, update the checkout under `vendor/ardmere.github.io`, refresh `fixtures/digests.json` paths and sha256 entries, then commit both the submodule pointer and this repo.

### Hackathon baseline disclosure

The assessment methodology and the assessment JSON are **pre-existing work**, not built here. They live in [`ardmere/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io), which also holds the assessment registry. This repo pins that work as a submodule and does not modify it.

This repository's own history starts at 2026-11-05, inside the hackathon window, so every commit here falls in the judged period. The first commit imported the NEAR demo from a branch of `ardmere.github.io`, and the import is disclosed here rather than presented as new authorship: the contract, the scoring script, the dashboard and `demo/run.sh` arrived in that import, and were then extended in this repo.

Changes made in this repo after the import:

- `scripts/near_digest.py`, `scripts/upstream_check.py` — testnet publishing and drift checks.
- `skills/por-risk-control/scripts/inclusion_check.py` and `tests/` — local verification of a user's own inclusion proof.
- `contracts/por_digest_anchor` — `point_latest`, and the tests that pin `get_latest` behaviour.
- `.github/workflows/` — the two pipelines.
- The manifest now covers every assessment the submodule pins (57 across 19 exchanges), and all of them are anchored on testnet.

Baseline, not judged as new work: the upstream assessments and the PoR Stage methodology in `ardmere.github.io`. No third-party libraries are vendored into `src`; the contract depends on `near-sdk` from crates.io, and the Python tests use only the standard library.

## Cursor: `por-risk-control` skill

This repo ships a symlink so Cursor can discover the skill in place:

- `.cursor/skills/por-risk-control` → `skills/por-risk-control` (same `SKILL.md` and `scripts/` as the CLI)

Open this folder as the workspace root in Cursor; the agent can use it when you ask for a custody risk score, the latest PoR snapshot time for an exchange, or a multi-month summary. Runnable checks:

```bash
POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  skills/por-risk-control/scripts/por-check.sh \
  vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json

POR_NEAR_CONTRACT=por-digest-v5-index.ardmere-demo-1fc2.testnet \
  python3 skills/por-risk-control/scripts/por-exchange-report.py binance --months 3
```

## Checking your own inclusion proof

`por-check.sh` scores an exchange. It cannot tell you whether *your* balance was in the snapshot. For that, the skill verifies the proof file your exchange gives you, locally:

```bash
skills/por-risk-control/scripts/inclusion_check.py --list-schemes
skills/por-risk-control/scripts/inclusion_check.py --exchange bybit ~/Downloads/myProof.json
# bind it to what the assessment published, when a root is published:
skills/por-risk-control/scripts/inclusion_check.py --exchange bitget \
  --assessment vendor/ardmere.github.io/docs/reports/bitget/20261021-assessment.json \
  ~/Downloads/merkel_tree_bg.json
```

| Exchange | Scheme | Root width |
| --- | --- | --- |
| `bitget` | self + path, balances folded | 64 bits (truncated) |
| `bingx` | leaf + path, no fold | 256 bits |
| `mexc` | self + path, balances folded | 128 bits (truncated) |
| `bybit` | 40-asset vector, height in preimage | 256 bits |

The proof contains your account id, nonce and balances. Keep it on your machine: the script prints verdicts only, writes nothing, and never echoes those fields. Parity with the Go verifiers in `vendor/ardmere.github.io/internal` is covered by `python3 -m unittest discover -s tests`.

A pass means your leaf is in the tree that produced that root. It is not a solvency proof and it does not move the custody score. When the assessment publishes no exchange merkle root, `binding.matches` is `null` — that is "not bound", not "matched".

Bitget needs one caveat: its assessment publishes a 256-bit `exchangeMerkleRoot` but its user proofs produce 64-bit roots. The two cannot be compared, so the script reports `ROOT_WIDTH_MISMATCH` and leaves `matches` as `null` rather than calling your proof wrong.

## Who publishes a snapshot to NEAR

Three separate roles. Nothing here writes to mainnet.

| Role | Command | Key |
| --- | --- | --- |
| Detect upstream drift | `python3 scripts/upstream_check.py` | none |
| Anchor what is missing on testnet | `python3 scripts/near_digest.py --contract <c.testnet> reconcile --apply` | owner |
| Read a score | `POR_NEAR_CONTRACT=<c.testnet> skills/por-risk-control/scripts/por-check.sh <file>` | none |

`scripts/upstream_check.py` only reads the submodule and the manifest. `scripts/near_digest.py` is idempotent: a snapshot already on chain with the same bytes is skipped, and different bytes fail instead of overwriting. Neither is a timer that re-sends transactions; the trigger is a manifest change, not a clock.

Schema v5 (aligned with Sepolia `custodyRiskScore`) stores `custody_risk_score` on each `SnapshotRecord`: **0–100** at anchor time (computed by `scripts/risk_score.py` from the same decision table as `por-check.sh`), **255** = inconclusive.

**Schema v7 is code-ready and not deployed.** `contracts/por_digest_anchor` now matches Sepolia v7: `total_liability_usd` and `total_reserve_usd` (`u128`, `0` = unavailable, whole USD) and `btc` / `eth` / `usdt` / `usdc` `_reserve_ratio_bps` (`u16`, `10000` = 100%, `65535` = unavailable). `get_snapshot` / `get` return those fields. `schema_version()` returns `7`. Do **not** deploy this WASM onto `por-digest-v5-index` — the borsh layout changed and existing state will not deserialize. A future account would be a new subaccount. `scripts/por_snapshot.py` packs the fields from assessment JSON (`totalLiabilityUsd`, `totalReserveUsd`, `majorCoinReserveRates`); sending those args to the live v5 account will fail to deserialize.

**Testnet contracts:** **`por-digest-v5-index.ardmere-demo-1fc2.testnet`** is the default live account (schema **v5**, 57 snapshots, **`custody_risk_score` on chain**). Set `POR_NEAR_CONTRACT` and `vars.NEAR_CONTRACT_ID` (CI) to this account. Legacy **`por-digest-v4-index.ardmere-demo-1fc2.testnet`** remains schema v4 (digest-only reads; no on-chain custody score). Do **not** deploy v5 WASM onto the v4-index account — state will not deserialize. New deploys use a **new** subaccount, `new()`, then `reconcile --apply`.

Two workflows wire this up:

- `.github/workflows/upstream-check.yml` runs nightly, advances the submodule in the CI checkout, and opens `cursor/upstream-sync` when a listed assessment changed. No secrets.
- `.github/workflows/anchor-testnet.yml` runs on `main` when the manifest or the submodule pointer moves, and anchors only what testnet is missing. It defaults `NEAR_CONTRACT_ID` to `por-digest-v5-index.ardmere-demo-1fc2.testnet` (override with `vars.NEAR_CONTRACT_ID`), needs `secrets.NEAR_TESTNET_OWNER_KEY` for the **v5-index owner**, writes the key to a temporary keychain, and deletes it afterwards.

Merging the sync PR is a human decision about which snapshots this demo vouches for, and it is what triggers anchoring. The demo therefore becomes the publisher of the NEAR records it serves; the upstream repo stays the source of the assessments.

## Reading live versus sandbox

`fixtures/near-views.json` is a sandbox recording. With `POR_NEAR_CONTRACT` unset, the skill reads that file; the `near.live` field is `false`. Set `POR_NEAR_CONTRACT` to a testnet account and the `get` comes from the chain with `near.live` `true`. Quote which one produced a number before quoting the number.

## Tracks

- `thesis` (primary). `THESIS.md` states the claim, the evidence for it, the evidence against it, and the result that would drop it. The page is the re-runnable evidence.
- `defi`. The same check a trading agent would read before treating a CEX as a venue: a 0–100 custody risk score and the factors for one snapshot. The agent or the person decides whether to trade.
- `security`. The same check. A hash mismatch or a blocking flag raises the score. The score is the signal. It does not place orders or move funds.

## Toolchain

`demo/run.sh` expects these on your `PATH`:

| Tool | Role |
| --- | --- |
| `cargo`, `rustup` | Build the contract WASM |
| `wasm32-unknown-unknown` (rustup target) | Contract compile target |
| `near` ([near-cli-rs](https://github.com/near/near-cli-rs)) | Deploy and view calls against the local sandbox |
| `near-sandbox` **or** `npx` | Local NEAR node (`npx` runs `near-sandbox@0.3.5` if the binary is missing) |
| `python3`, `curl` | Fixture checks and HTTP helpers |

### Linux (Debian / Ubuntu)

System packages for building `near-cli-rs` (including `hidapi`):

```bash
sudo apt-get update
sudo apt-get install -y curl pkg-config libssl-dev libudev-dev
```

Rust (stable; `near-cli-rs` needs a recent compiler):

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup update stable
rustup default stable
rustup target add wasm32-unknown-unknown
```

`near` CLI:

```bash
cargo install near-cli-rs --locked
```

Node.js with `npx` is enough for the sandbox; install Node from your distro or [nodejs.org](https://nodejs.org/) if `npx` is missing. Optionally install a `near-sandbox` binary instead; the script prefers it when present.

Verify:

```bash
cargo --version
rustup target list --installed | grep wasm32-unknown-unknown
near --version
command -v npx || command -v near-sandbox
```

## Reproduce

From the repo root:

```bash
./demo/run.sh
```

`fixtures/near-views.json` in git is a sandbox recording, not a live chain. The script is the check.

The manifest covers every snapshot from the 19 exchanges in the submodule: Binance, BingX, Bitget, Bitunix, BTCC, Bybit, CoinEx, CoinW, Gate, HTX, Kraken, KuCoin, MEXC, OKX, Ourbit, Phemex, Poloniex, Toobit, and WOOX. Two examples: OKX `508756245` scores 10, `low` (`NO_CANONICAL_ANCHOR` +5 and `HIGH_FREQUENCY_GAP` +5). KuCoin `20261031` scores 99, `critical` (blocking + stage + derived disclosure gaps; same scorer as ardmere.github.io). `fixtures/near-views.json` in git is a sandbox recording of those two snapshots. A full `./demo/run.sh` rewrites it for every listed snapshot. `THESIS.md` states the claim, the evidence for it, the evidence against it, and what result would drop the claim.

Accounts the script prints exist only inside that sandbox process. They are not mainnet accounts.
