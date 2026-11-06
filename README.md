# ardmere NEAR demo

A trading agent that uses CEX liquidity needs a custody-risk record anyone can re-hash and re-query, and NEAR fits because one contract stores the digest and a view call returns it.

One contract stores an assessment digest. One skill scores custody risk from that digest. One page shows the score beside the hash and the NEAR view.

## Baseline

Assessments are copied from `ardmere/ardmere.github.io` at commit `57a5bcd`. The registry and the Ethereum Sepolia anchor stay in that repo. This repo is the NEAR slice.

## Tracks

- `thesis` (primary). `THESIS.md` states the claim, the evidence for it, the evidence against it, and the result that would drop it. The page is the re-runnable evidence.
- `defi`. The same check a trading agent would read before treating a CEX as a venue: a 0–100 custody risk score and the factors for one snapshot. The agent or the person decides whether to trade.
- `security`. The same check. A hash mismatch or a blocking flag raises the score. The score is the signal. It does not place orders or move funds.

## Reproduce

Toolchain: Rust with the `wasm32-unknown-unknown` target, `near-sandbox`, and `near` (near-cli-rs).

```bash
./demo/run.sh
```

`fixtures/near-views.json` in git is a sandbox recording, not a live chain. The script is the check.

The script prints one low score for OKX snapshot `508756245` (Stage 1, `effectivePoR` true, `NO_CANONICAL_ANCHOR` +5 and `HIGH_FREQUENCY_GAP` +5, riskScore 10, `low`) and one elevated score for KuCoin snapshot `20261031` (Stage 0, `UNVERIFIABLE` +40 and stage +35, riskScore 75, `high`). The sha256 fields in `fixtures/near-views.json` match `fixtures/digests.json`. Open the printed localhost URL and see the same hashes. `THESIS.md` states the claim, the evidence for it, the evidence against it, and what result would drop the claim.

Accounts the script prints exist only inside that sandbox process. They are not mainnet accounts.
