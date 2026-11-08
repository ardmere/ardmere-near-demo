# ardmere NEAR demo

Public Proof-of-Reserves from mainstream exchanges, in the assessments vendored here, is mostly not something a third party can recompute. At submodule commit `e4400bd` there are 57 snapshots across 19 exchanges: 50 are Stage 0 and carry `UNVERIFIABLE`. OKX is the only exchange at Stage 1 (7 snapshots), and every one of those still carries `NO_CANONICAL_ANCHOR`.

NEAR stores the sha256 of each listed assessment. A view call returns the same 32 bytes, so the measurement can be re-hashed and re-queried. The contract does not verify reserves. Anchoring a digest does not make a disclosure verifiable, and it is not a record that exchange disclosure advanced.

One contract stores the digest. One skill turns the public flags into a 0–100 score of how far a snapshot is from being recomputable. One page shows that score beside the file hash and the NEAR view.

## Baseline

Assessment JSON comes from the **git submodule** [`vendor/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io), pinned to the same baseline commit as `fixtures/digests.json` (`sourceCommit`). `fixtures/digests.json` lists every `*-assessment.json` in that submodule, so every exchange the upstream repo has published can be scored and, once anchored, read back with `get` / `get_latest`. The registry and the Ethereum Sepolia anchor stay in that repo. This repo is the NEAR slice plus the skill and dashboard.

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/ardmere/ardmere-near-demo.git
# or, on an existing checkout:
git submodule update --init --recursive
```

To move the submodule to a newer upstream commit, update the checkout under `vendor/ardmere.github.io`, refresh `fixtures/digests.json` paths and sha256 entries, then commit both the submodule pointer and this repo.

## Cursor: `por-risk-control` skill

This repo ships a symlink so Cursor can discover the skill in place:

- `.cursor/skills/por-risk-control` → `skills/por-risk-control` (same `SKILL.md` and `scripts/` as the CLI)

Open this folder as the workspace root in Cursor; the agent can use it when you ask for a custody risk score from a public assessment file. The runnable check remains:

```bash
skills/por-risk-control/scripts/por-check.sh vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json
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

Two workflows wire this up:

- `.github/workflows/upstream-check.yml` runs nightly, advances the submodule in the CI checkout, and opens `cursor/upstream-sync` when a listed assessment changed. No secrets.
- `.github/workflows/anchor-testnet.yml` runs on `main` when the manifest or the submodule pointer moves, and anchors only what testnet is missing. It needs `vars.NEAR_CONTRACT_ID` and `secrets.NEAR_TESTNET_OWNER_KEY`, writes the key to a temporary keychain, and deletes it afterwards.

Merging the sync PR is a human decision about which snapshots this demo vouches for, and it is what triggers anchoring. The demo therefore becomes the publisher of the NEAR records it serves; the upstream repo stays the source of the assessments and the Sepolia anchor.

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

The manifest covers every snapshot from the 19 exchanges in the submodule: Binance, BingX, Bitget, Bitunix, BTCC, Bybit, CoinEx, CoinW, Gate, HTX, Kraken, KuCoin, MEXC, OKX, Ourbit, Phemex, Poloniex, Toobit, and WOOX. Two examples: OKX `508756245` scores 10, `low` (`NO_CANONICAL_ANCHOR` +5 and `HIGH_FREQUENCY_GAP` +5). KuCoin `20261031` scores 75, `high` (`UNVERIFIABLE` +40 and stage +35). `fixtures/near-views.json` in git is a sandbox recording of those two snapshots. A full `./demo/run.sh` rewrites it for every listed snapshot. `THESIS.md` states the claim, the evidence for it, the evidence against it, and what result would drop the claim.

Accounts the script prints exist only inside that sandbox process. They are not mainnet accounts.
