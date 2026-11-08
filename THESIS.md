# Thesis

In the public assessments pinned in this repo, mainstream exchange Proof-of-Reserves is mostly not something a third party can recompute. NEAR stores the sha256 of that measurement so a view call returns the same 32 bytes. The chain does not verify reserves. A second copy of the hash is not progress in what exchanges publish.

## Evidence for

At `ardmere/ardmere.github.io` commit `e4400bd` the submodule holds 57 assessments across 19 exchanges. 50 are Stage 0 and carry `UNVERIFIABLE`: Binance, BingX, Bitget, Bitunix, BTCC, Bybit, CoinEx, CoinW, Gate, HTX, Kraken, KuCoin, MEXC, Ourbit, Phemex, Poloniex, Toobit, and WOOX. The other 7 are OKX, all Stage 1, and each carries `NO_CANONICAL_ANCHOR` and `HIGH_FREQUENCY_GAP`. Stage here is a label for how much of the disclosure a third party can recompute. It is not a credit rating.

`fixtures/digests.json` lists all 57 of those assessments, every exchange the upstream repo publishes at that commit. Anyone can sha256 a listed file and compare it to the manifest. `get_latest` is pointed at the newest snapshot by `snapshotTime` for each exchange.

`por_digest_anchor` stores that digest under `(exchange, snapshot_id)`. `get` and `get_latest` return it. The same call works in a local NEAR sandbox, with no exchange RPC and no custody of funds.

`skills/por-risk-control/scripts/por-check.sh` reads one file, checks the hash, and prints `riskScore`, `riskLevel`, and `factors`. The dashboard shows that score next to the file hash and the view result.

## Evidence against

The contract stores a digest of an off-chain assessment. It does not prove reserves.

The existing registry anchors on Ethereum Sepolia. A second chain holding the same kind of hash does not make the underlying custody claim true.

The score is a reading of flags already on the public assessment. It is not a new reserve proof, and it does not decide a trade. OKX lands at 10 (`low`) because the hash matches, effective PoR is true, and the only flags are `NO_CANONICAL_ANCHOR` and `HIGH_FREQUENCY_GAP`. KuCoin lands at 75 (`high`) because the file carries `UNVERIFIABLE` and the stage is Stage 0. Those numbers describe the pinned assessments. They are not a reason to trade.

## What would drop the claim

A recount of the pinned assessments that does not show 50 of 57 snapshots as Stage 0 with `UNVERIFIABLE`, or that shows an exchange other than OKX at Stage 1. The measurement would be wrong for this commit.

A view that does not return the same 32 bytes the assessment file hashes to. The record would no longer be something anyone can re-check.

Reading the on-chain digest as proof of reserves, or as evidence that anchoring made a disclosure verifiable. That is a different claim, and this repo does not support it. An assessment file whose sha256 does not match both `fixtures/digests.json` and the anchored value fails the same way: the score floors at 100, `critical`, which is the script saying the trail broke.
