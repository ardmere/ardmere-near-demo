//! Same three checks as the in-crate tests, called through the public API.
//! No network and no key files.

use near_sdk::test_utils::VMContextBuilder;
use near_sdk::testing_env;
use por_digest_anchor::Contract;

fn set_context(predecessor: &str, block_height: u64) {
    let mut builder = VMContextBuilder::new();
    builder
        .predecessor_account_id(predecessor.parse().unwrap())
        .current_account_id("por-digest-anchor.sandbox".parse().unwrap())
        .block_height(block_height);
    testing_env!(builder.build());
}

fn anchor(contract: &mut Contract, exchange: &str, snapshot_id: &str, hash: &str, stage: &str, effective: bool) {
    contract.anchor(
        exchange.to_string(),
        snapshot_id.to_string(),
        hash.to_string(),
        stage.to_string(),
        effective,
        "por-transparency-framework@2026-07-01".to_string(),
    );
}

#[test]
fn anchor_then_get_returns_the_same_bytes() {
    set_context("owner.sandbox", 7);
    let mut contract = Contract::new();
    let hash = "ab".repeat(32);
    anchor(&mut contract, "okx", "508756245", &hash, "Stage 1", true);
    let rec = contract.get("okx".to_string(), "508756245".to_string());
    assert_eq!(rec.assessment_sha256, hash);
    assert_eq!(rec.assessment_sha256.len(), 64);
}

#[test]
#[should_panic(expected = "different bytes")]
fn second_different_digest_reverts() {
    set_context("owner.sandbox", 4);
    let mut contract = Contract::new();
    anchor(&mut contract, "okx", "508756245", &"11".repeat(32), "Stage 1", true);
    anchor(&mut contract, "okx", "508756245", &"22".repeat(32), "Stage 1", true);
}

#[test]
fn get_latest_follows_the_newest_snapshot() {
    set_context("owner.sandbox", 3);
    let mut contract = Contract::new();
    anchor(&mut contract, "okx", "older", &"11".repeat(32), "Stage 1", true);
    set_context("owner.sandbox", 4);
    anchor(&mut contract, "okx", "newer", &"22".repeat(32), "Stage 1", true);
    assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
}
