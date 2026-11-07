# Thesis

A trading agent that uses CEX liquidity needs a custody-risk record anyone can re-hash and re-query, and NEAR fits because one contract stores the digest and a view call returns it.

## Evidence for

The assessment files are the public OKX `508756245` and KuCoin `20261031` JSON from the git submodule `vendor/ardmere.github.io` at `ardmere/ardmere.github.io` commit `57a5bcd` (see `fixtures/digests.json` for exact paths under `docs/reports/...`). Anyone can sha256 those bytes and compare them to `fixtures/digests.json`.

`por_digest_anchor` stores that digest under `(exchange, snapshot_id)`. `get` and `get_latest` return it. The same call works in a local NEAR sandbox, with no exchange RPC and no custody of funds.

`skills/por-risk-control/scripts/por-check.sh` reads one file, checks the hash, and prints `riskScore`, `riskLevel`, and `factors`. The dashboard shows that score next to the file hash and the view result.

## Evidence against

The contract stores a digest of an off-chain assessment. It does not prove reserves.

The existing registry anchors on Ethereum Sepolia. A second chain holding the same kind of hash does not make the underlying custody claim true.

The score is a reading of flags already on the public assessment. It is not a new reserve proof, and it does not decide a trade. OKX lands at 10 (`low`) because the hash matches, effective PoR is true, and the only flags are `NO_CANONICAL_ANCHOR` and `HIGH_FREQUENCY_GAP`. KuCoin lands at 75 (`high`) because the file carries `UNVERIFIABLE` and the stage is Stage 0. Those numbers describe the copied files. They are not a reason to trade.

## What would drop the claim

A view that does not return the same 32 bytes the assessment file hashes to.

A contract that has to verify reserves, fetch the exchange, or hold funds before a reader can re-query the digest. The claim is that storage plus a view call is the fit.

An assessment file whose sha256 does not match both `fixtures/digests.json` and the anchored value. The record would no longer be something anyone can re-check. The score then floors at 100, `critical`, which is the script saying the trail broke.
