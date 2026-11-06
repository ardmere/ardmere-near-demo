# ardmere NEAR demo

A trading agent that uses CEX liquidity needs a custody-risk record anyone can re-hash and re-query, and NEAR fits because one contract stores the digest and a view call returns it.

One contract stores an assessment digest. One skill scores custody risk from that digest. One page shows the score beside the hash and the NEAR view.

## Baseline

Assessment JSON comes from the **git submodule** [`vendor/ardmere.github.io`](https://github.com/ardmere/ardmere.github.io), pinned to the same baseline commit as `fixtures/digests.json` (`sourceCommit`). The registry and the Ethereum Sepolia anchor stay in that repo. This repo is the NEAR slice plus the skill and dashboard.

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

The script prints one low score for OKX snapshot `508756245` (Stage 1, `effectivePoR` true, `NO_CANONICAL_ANCHOR` +5 and `HIGH_FREQUENCY_GAP` +5, riskScore 10, `low`) and one elevated score for KuCoin snapshot `20261031` (Stage 0, `UNVERIFIABLE` +40 and stage +35, riskScore 75, `high`). The sha256 fields in `fixtures/near-views.json` match `fixtures/digests.json`. Open the printed localhost URL and see the same hashes. `THESIS.md` states the claim, the evidence for it, the evidence against it, and what result would drop the claim.

Accounts the script prints exist only inside that sandbox process. They are not mainnet accounts.
