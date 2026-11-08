//! Same checks as the in-crate tests, called through the public API.
//! No network and no key files.

use near_sdk::test_utils::VMContextBuilder;
use near_sdk::testing_env;
use por_digest_anchor::Contract;

fn set_context(predecessor: &str, block_height: u64) {
    let mut builder = VMContextBuilder::new();
    builder
        .predecessor_account_id(predecessor.parse().unwrap())
        .current_account_id("por-digest-anchor.sandbox".parse().unwrap())
        .block_height(block_height)
        .block_timestamp(1_700_000_000_000_000_000);
    testing_env!(builder.build());
}

fn sample_roots(seed: u8) -> (String, String, String) {
    (
        "00".repeat(32),
        format!("{:02x}", seed).repeat(32),
        format!("{:02x}", seed.wrapping_add(1)).repeat(32),
    )
}

fn anchor(
    contract: &mut Contract,
    exchange: &str,
    snapshot_id: &str,
    hash: &str,
    period_seq: u32,
    stage: u8,
    effective: bool,
    seed: u8,
) {
    let (ex_root, art_root, ver_root) = sample_roots(seed);
    contract.anchor(
        exchange.to_string(),
        snapshot_id.to_string(),
        period_seq,
        1_700_000_000,
        0,
        ex_root,
        art_root,
        ver_root,
        0x09,
        0,
        stage,
        effective,
        0,
        0,
        hash.to_string(),
        "por-transparency-framework@2026-07-01".to_string(),
    );
}

#[test]
fn anchor_then_get_returns_the_same_bytes() {
    set_context("owner.sandbox", 7);
    let mut contract = Contract::new();
    let hash = "ab".repeat(32);
    anchor(&mut contract, "okx", "508756245", &hash, 1, 2, true, 0xab);
    let rec = contract.get("okx".to_string(), "508756245".to_string());
    assert_eq!(rec.assessment_sha256, hash);
    assert_eq!(rec.assessment_sha256.len(), 64);
    assert_eq!(rec.schema_version, 4);
    assert_eq!(rec.por_stage, 2);
    assert_eq!(rec.artifact_bundle_root, "ab".repeat(32));
}

#[test]
#[should_panic(expected = "different bytes")]
fn second_different_digest_reverts() {
    set_context("owner.sandbox", 4);
    let mut contract = Contract::new();
    anchor(&mut contract, "okx", "508756245", &"11".repeat(32), 1, 2, true, 0x11);
    anchor(&mut contract, "okx", "508756245", &"22".repeat(32), 1, 2, true, 0x22);
}

#[test]
fn get_latest_follows_the_newest_snapshot() {
    set_context("owner.sandbox", 3);
    let mut contract = Contract::new();
    anchor(&mut contract, "okx", "older", &"11".repeat(32), 1, 2, true, 0x11);
    set_context("owner.sandbox", 4);
    anchor(&mut contract, "okx", "newer", &"22".repeat(32), 2, 2, true, 0x22);
    assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
    set_context("owner.sandbox", 5);
    anchor(&mut contract, "okx", "older", &"11".repeat(32), 1, 2, true, 0x11);
    assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
    contract.point_latest("okx".to_string(), "older".to_string());
    assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "older");
    contract.point_latest("okx".to_string(), "newer".to_string());
    assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
}
