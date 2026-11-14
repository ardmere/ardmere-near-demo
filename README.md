# ardmere NEAR demo

## For judges

| | |
| --- | --- |
| Problem | A NEAR Intents solver hedges on a CEX. That custodial leg is the solver's own capital. Exchange PoR disclosures differ wildly; many are not third-party recomputable. |
| Product | A NEAR testnet index of **ardmere assessments**: sha256, transparency score, stage, and self-reported reserve fields. |
| Upstream | [`ardmere/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io) is a **unified verification layer for exchange Proof-of-Reserves**: one stage methodology, public assessments, and verification where artifacts allow (e.g. OKX Stage 1). `UNVERIFIABLE` marks snapshots that cannot be recomputed. This repo pins one commit and anchors each **assessment** sha256 on NEAR. |
| NEAR's role | Anyone can `view` the record with no account and no key. The chain freezes the assessment bytes (the verification outcome), not a raw exchange dump. It does not re-run proofs on-chain and does not prove reserve adequacy. |
| Contract | [`por-digest-v7-index.ardmere-demo-1fc2.testnet`](https://explorer.testnet.near.org/accounts/por-digest-v7-index.ardmere-demo-1fc2.testnet) (schema v7) |
| Do this | [Three steps](#try-it-in-three-steps) below. Single-file score is step 3. |
| Agent | [Agent path](#agent-path-por-risk-control): one exchange or a batch. Not part of the three steps. |
| See this | OKX latest: `custody_risk_score` **15**, file sha256 **equals** the chain, `por-check` prints `"riskScore": 15`, `"near.matches": true`. |

## Try it in three steps

No account and no key. Step 1 needs only `curl` and `python3`. Steps 2 and 3 need a clone with submodules; step 3 needs `python3` only (not the `near` CLI).

**Step 1 — read the on-chain record and print the JSON.**

```bash
curl -sS -X POST https://rpc.testnet.fastnear.com \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"query","params":{
        "request_type":"call_function","finality":"final",
        "account_id":"por-digest-v7-index.ardmere-demo-1fc2.testnet",
        "method_name":"get_latest",
        "args_base64":"eyJleGNoYW5nZSI6Im9reCJ9"}}' \
| python3 -c 'import json,sys; print(bytes(json.load(sys.stdin)["result"]["result"]).decode())'
```

`args_base64` is the base64 of `{"exchange":"okx"}`. See the account on [testnet explorer](https://explorer.testnet.near.org/accounts/por-digest-v7-index.ardmere-demo-1fc2.testnet).

Expected JSON includes `"exchange":"okx"`, `"snapshot_id":"508756245"`, `"assessment_sha256":"1867c97cbbf2a34841acbe0da20e381f7c46c042cce1dd65f2dc21a2f5d96bae"`, `"custody_risk_score":15`, `"por_stage":2`, `"schema_version":7`. `por_stage` 2 means Stage 1.

Other read-only methods on the same contract: `get` (exchange + plaintext audit id), `expected_snapshot_id`, `get_snapshot_count`, `get_snapshot_id_at`, and `get_snapshot`. Each row in `fixtures/digests.json` carries `expectedSnapshotId`. After `reconcile --apply`, `point_latest` chooses which snapshot `get_latest` returns.

**Step 2 — clone, then hash the file the digest names.**

```bash
git clone --recurse-submodules https://github.com/ardmere/ardmere-near-demo.git
cd ardmere-near-demo
sha256sum vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Expected: `1867c97cbbf2a34841acbe0da20e381f7c46c042cce1dd65f2dc21a2f5d96bae`, the same hex as Step 1. The bytes you hashed are the bytes the chain names.

**Step 3 — score that file against the live contract.** `python3` only.

```bash
POR_NEAR_CONTRACT=por-digest-v7-index.ardmere-demo-1fc2.testnet \
  skills/por-risk-control/scripts/por-check.sh \
  vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
```

Expected: `"riskScore": 15`, `"riskLevel": "low"`, `"near": {"live": true, "matches": true, ...}`. `live: true` means this run called the contract, not `fixtures/near-views.json`.

Any other row in `fixtures/digests.json` works the same way. All 59 listed snapshots are on this contract.

### What a judge cannot conclude

Step 2 proves the chain names the same bytes as the file. It does not prove the exchange holds reserves. A hash match is not evidence that anchoring made the disclosure recomputable. If the file sha256 disagrees with both `fixtures/digests.json` and the chain, the score floors at 100.

## Agent path: `por-risk-control`

Use this when the task is an exchange PoR assessment, not the hash check above. Step 3 already scores one file.

1. Clone with submodules, as in [step 2](#try-it-in-three-steps). Open that directory as the workspace root. `.cursor/skills/por-risk-control` points at `skills/por-risk-control`.
2. Set `POR_NEAR_CONTRACT=por-digest-v7-index.ardmere-demo-1fc2.testnet` for a live read. `python3` only. If the variable is unset, `por-check.sh` reads `fixtures/near-views.json` and `near.live` is false.
3. One exchange, latest snapshot plus optional history:

```bash
POR_NEAR_CONTRACT=por-digest-v7-index.ardmere-demo-1fc2.testnet \
  python3 skills/por-risk-control/scripts/por-exchange-report.py binance --months 3
```

4. User-facing layout is [`skills/por-risk-control/references/response-framework.md`](skills/por-risk-control/references/response-framework.md): **A** one snapshot, **B** one exchange, **C** many exchanges in one merged table. Missing self-reported fields are `Unavailable`. The score is transparency risk (higher = worse disclosure), not permission to trade.

## What this gives NEAR

Upstream **ardmere** is a **unified verification layer for exchange Proof-of-Reserves**: one public methodology evaluates CEX disclosures across venues, **verifies what is publicly verifiable** (wallet lists, ownership proofs, zk bundles where published — e.g. OKX at Stage 1), and labels what is not (`UNVERIFIABLE` / Stage 0). This demo anchors each **assessment** on NEAR so solvers and agents read a consistent, permissionless record of that outcome.

In short, NEAR holds a **checkable index of ardmere’s PoR verification results** — assessment digest, transparency score, stage, and self-reported reserve fields — for **on-chain protocol risk parameters** and for **agents** that touch CEX hedging or venue choice. That is **disclosure / verification-posture input**, not proof of reserve adequacy.

A NEAR Intents solver is a principal, not a matcher. Its own terms of use put it plainly: the solver "provides and maintains its own Liquidity, at its own cost and under its own control" and "bears all market, inventory, hedging, network, execution, and settlement risk as principal" ([Solver Terms of Use](https://docs.near-intents.org/integration/market-makers/solver-terms-of-use), §7.1 and §7.4).

Filling an intent leaves the solver holding the asset the user sold. It quotes slightly worse than the price it can get by selling that asset elsewhere, and keeps the difference as spread. The venue it sells into is usually a centralized exchange, because that is where depth and latency are. Industry write-ups of intent-based market making describe CEXs as "the primary hedging layer" that "introduces custodial risk and a single point of failure" ([ChainScore](https://chainscorelabs.com/blog/trading/intent-based-architectures/inventory-risk-for-market-makers), [Flip](https://flipdex.co/notes/solver-economics)).

So the solver carries two exposures, and only one of them is on chain:

| Stage | Exposure | Does a reserve assessment help? |
| --- | --- | --- |
| User ↔ solver | none: the swap settles atomically, or it refunds | no |
| Solver ↔ exchange, when hedging | **custodial**: the solver's own capital sits at the venue | **yes** |

The second one is why a reserve assessment has a reader here. A solver choosing where to hedge is choosing where to leave capital. The 59 assessments vendored here are **ardmere verification outcomes** for those venues: 52 of 59 are Stage 0 with `UNVERIFIABLE` (third party cannot recompute), while OKX’s 7 snapshots reach Stage 1 because published artifacts were verified under the same framework. That split is a fact a solver can cite — whether the reader is a solver, an agent, or a person.

This repo anchors the sha256 of each **assessment file** on NEAR (`por-digest-v7-index.ardmere-demo-1fc2.testnet`, schema v7: digest, `custody_risk_score`, and self-reported USD / major-coin reserve fields). Anyone can hash the local assessment and compare it to that on-chain digest — without calling the exchange's API.

What NEAR contributes to this, and what it does not:

- **Contributes:** the record is readable with a `view` call, with no account, no key and no payment ([step 1](#try-it-in-three-steps) is exactly that). A hosted API can rate-limit, go down, or change its answer; a `view` call at a block height cannot.
- **Contributes:** a named account such as `por-digest-v7-index.ardmere-demo-1fc2.testnet` is checkable by reading it, not by trusting a hex string.
- **Contributes:** a **permissionless on-chain index of that verification layer** on NEAR. Each anchored snapshot exposes `custody_risk_score`, `por_stage`, digest roots, and (schema v7) self-reported USD totals and major-coin ratio bps via `get` / `get_latest`. On-chain protocols can plug those **view** results into risk policy (for example minimum stage, maximum transparency score, or hash match) before routing treasury, hedging, or counterparty exposure — without trusting an exchange API or a hosted scorer.
- **Contributes:** the same records plus the [`por-risk-control`](skills/por-risk-control/SKILL.md) skill give NEAR **AI agents** a deterministic read path (`por-check.sh` → JSON with `officialSources` and `selfReportedReserves`) for CEX venue checks, PoR Q&A, and pre-flight hedging workflows. That is **transparency-risk input**, not solvency proof and not trade permission.
- **Does not contribute:** the NEAR contract does **not** re-verify exchange proofs and does **not** prove reserve adequacy. It freezes the assessment bytes. When upstream already verified (e.g. OKX Stage 1), the chain preserves that outcome; anchoring alone does not turn an `UNVERIFIABLE` disclosure into a recomputable one.

| Reader on NEAR | Typical use | On-chain hook |
| --- | --- | --- |
| Protocol / DAO policy | Gate hedge venue or custodial counterparty | `get_latest`, `custody_risk_score`, `por_stage` |
| AI agent | Venue pre-check; cite official PoR URLs to users | Skill + same contract `get`; `near.matches` |
| Intents solver | Hedge custodial leg (see above) | unchanged |

The chain is not what makes a solver safer. It is where the measurement about hedge venues can be read by anyone who needs it, without asking permission.

---

At submodule commit pinned in `fixtures/digests.json` (currently `be220a5`) there are 59 assessments across 19 exchanges under one verification framework: 52 are Stage 0 with `UNVERIFIABLE`; OKX is the only exchange at Stage 1 (7 snapshots, still carrying `NO_CANONICAL_ANCHOR`). The majority finding is intentional output of the verification layer, not a claim that ardmere only hashes filings.

NEAR stores the sha256 of each listed **assessment**. A view call returns the same 32 bytes, so the verification outcome can be re-hashed and re-queried. The contract does not re-run exchange proofs or attest reserves.

One contract indexes those assessment digests. One skill turns the public flags into a 0–100 score of transparency / verification posture. `./demo/run.sh` serves a local page with that score beside the file hash and the NEAR view. The judge path above does not need that page.

## Baseline

Assessment JSON comes from the **git submodule** [`vendor/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io) — the unified PoR verification layer — pinned to the commit named by `fixtures/digests.json` (`sourceCommit`). `fixtures/digests.json` lists every `*-assessment.json` in that submodule, so every published assessment can be scored and, once anchored, read back with `get` / `get_latest`. Methodology and verification stay upstream; this repo is the NEAR index plus the skill and dashboard.

Clone with submodules (same command as [step 2](#try-it-in-three-steps)):

```bash
git clone --recurse-submodules https://github.com/ardmere/ardmere-near-demo.git
# or, on an existing checkout:
git submodule update --init --recursive
```

To move the submodule to a newer upstream commit, update the checkout under `vendor/ardmere.github.io`, refresh `fixtures/digests.json` paths and sha256 entries, then commit both the submodule pointer and this repo.

### Assessments and this repo

The assessment files and the PoR stage methodology live in [`ardmere/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io). This repo pins one commit of it as a submodule and does not edit those files.

This repository's own history starts at 2026-11-05, inside the hackathon window. The first commit imported the NEAR demo from a branch of `ardmere.github.io`; the contract, the scoring script, the dashboard, and `demo/run.sh` arrived in that import and were then extended here.

Changes made in this repo after the import:

- `scripts/near_digest.py`, `scripts/upstream_check.py` — testnet publishing and drift checks.
- `skills/por-risk-control/scripts/inclusion_check.py` and `tests/` — local verification of a user's own inclusion proof.
- `contracts/por_digest_anchor` — `point_latest`, and the tests that pin `get_latest` behaviour.
- `.github/workflows/` — the two pipelines.
- The manifest now covers every assessment the submodule pins (59 across 19 exchanges), and all of them are anchored on testnet.

No third-party libraries are vendored into `src`. The contract depends on `near-sdk` from crates.io, and the Python tests use only the standard library.

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
| Anchor / refresh on testnet | `python3 scripts/near_digest.py --contract <c.testnet> reconcile --refresh --apply` | owner |
| Read a score | `POR_NEAR_CONTRACT=<c.testnet> skills/por-risk-control/scripts/por-check.sh <file>` | none |

`scripts/upstream_check.py` only reads the submodule and the manifest. `scripts/near_digest.py` skips a snapshot already on chain with the same bytes. When the assessment bytes for the same `snapshot_id` change, `reconcile --refresh --apply` updates that record. Without `--refresh`, a byte mismatch is reported and left in place. Neither command is a timer; the trigger is a manifest change, not a clock.

**Live contract (schema v7):** **`por-digest-v7-index.ardmere-demo-1fc2.testnet`** — 59 snapshots from the submodule commit in `fixtures/digests.json` (`sourceCommit`, currently `be220a5`). `SnapshotRecord` includes `custody_risk_score` (**0–100**, **255** = inconclusive), `total_liability_usd` / `total_reserve_usd` (`u128`, `0` = unavailable), and `btc` / `eth` / `usdt` / `usdc` `_reserve_ratio_bps` (`u16`, `10000` = 100%, `65535` = unavailable), aligned with Sepolia v7. Set `POR_NEAR_CONTRACT` and `vars.NEAR_CONTRACT_ID` (CI) to this account. `scripts/por_snapshot.py` packs reserve fields from assessment JSON.

**Legacy testnet accounts (read-only history):** **`por-digest-v5-index.ardmere-demo-1fc2.testnet`** (schema v5, old assessment sha256 — `near.matches` false vs current files). **`por-digest-v4-index.ardmere-demo-1fc2.testnet`** (schema v4, no on-chain custody score). Do **not** upgrade WASM in-place across schema versions; use a **new** subaccount, `new()`, then `reconcile --apply`.

Two workflows wire this up:

- `.github/workflows/upstream-check.yml` runs nightly, advances the submodule in the CI checkout, and opens `cursor/upstream-sync` when a listed assessment changed. No secrets.
- `.github/workflows/anchor-testnet.yml` runs on `main` when the manifest or the submodule pointer moves, and runs `reconcile --refresh --apply` (new rows and same-`snapshot_id` byte updates). It defaults `NEAR_CONTRACT_ID` to `por-digest-v7-index.ardmere-demo-1fc2.testnet` (override with `vars.NEAR_CONTRACT_ID`), needs `secrets.NEAR_TESTNET_OWNER_KEY` for the **v7-index contract account**, writes the key to a temporary keychain, and deletes it afterwards.

Merging the sync PR is a human decision about which snapshots this demo vouches for, and it is what triggers anchoring. The demo therefore becomes the publisher of the NEAR records it serves; the upstream repo stays the source of the assessments.

## Reading live versus sandbox

`fixtures/near-views.json` is a sandbox recording. With `POR_NEAR_CONTRACT` unset, the skill reads that file; the `near.live` field is `false`. Set `POR_NEAR_CONTRACT` to a testnet account and the `get` comes from the chain with `near.live` `true`. Quote which one produced a number before quoting the number.

## Tracks

Submission tracks: `agents`, `defi`, `open`. This repo does not settle swaps, prove reserves, or place orders.

- `agents` (primary). A NEAR agent that touches a CEX reads the same `view` and `por-risk-control` JSON (`riskScore`, `near.matches`, `officialSources`) before choosing a venue. The score is input. It is not permission to trade.
- `defi`. An Intents solver's hedge sits at a CEX. The on-chain index is the disclosure check for that custodial leg. It is not an exchange and it does not settle through Intents.
- `open`. The idea does not fit the investment-thesis or spending-control tracks. It is a disclosure index for agents and for hedge-venue choice. The [three steps](#try-it-in-three-steps) are the re-run.

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

The manifest covers every snapshot from the 19 exchanges in the submodule: Binance, BingX, Bitget, Bitunix, BTCC, Bybit, CoinEx, CoinW, Gate, HTX, Kraken, KuCoin, MEXC, OKX, Ourbit, Phemex, Poloniex, Toobit, and WOOX. Two examples: OKX `508756245` scores 15, `low` (`NO_CANONICAL_ANCHOR` +5, `HIGH_FREQUENCY_GAP` +5, `NO_PUBLIC_POR_API` +5). KuCoin `20261031` scores 100, `critical` (blocking + stage + derived disclosure gaps; same scorer as ardmere.github.io). `fixtures/near-views.json` in git is a sandbox recording of those two snapshots. A full `./demo/run.sh` rewrites it for every listed snapshot. Those scores describe how far a disclosure can be recomputed. They are not a reason to trade, and a matching digest is not proof of reserves.

Accounts the script prints exist only inside that sandbox process. They are not mainnet accounts.
