//! Stores a sha256 digest of an off-chain Proof-of-Reserves assessment.
//! Does not verify reserves, fetch exchanges, or hold funds.

use near_sdk::{env, near, AccountId, PanicOnDefault};
use std::collections::HashMap;

const KEY_SEP: char = '\u{1}';

#[near(serializers = [borsh, json])]
#[derive(Clone, PartialEq, Debug)]
pub struct DigestRecord {
    pub exchange: String,
    pub snapshot_id: String,
    pub assessment_sha256: String,
    pub por_stage: String,
    pub effective_por: bool,
    pub methodology_version: String,
    pub block_height: u64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    owner: AccountId,
    records: HashMap<String, DigestRecord>,
    latest: HashMap<String, String>,
}

#[near]
impl Contract {
    #[init]
    pub fn new() -> Self {
        Self {
            owner: env::predecessor_account_id(),
            records: HashMap::new(),
            latest: HashMap::new(),
        }
    }

    pub fn anchor(
        &mut self,
        exchange: String,
        snapshot_id: String,
        assessment_sha256: String,
        por_stage: String,
        effective_por: bool,
        methodology_version: String,
    ) {
        if env::predecessor_account_id() != self.owner {
            env::panic_str("only the account that deployed this contract may anchor");
        }
        require_label("exchange", &exchange);
        require_label("snapshot_id", &snapshot_id);
        if por_stage.is_empty() || methodology_version.is_empty() {
            env::panic_str("por_stage and methodology_version are required");
        }
        let bytes = decode_sha256(&assessment_sha256);
        let stored_hex = encode_sha256(&bytes);
        let key = record_key(&exchange, &snapshot_id);
        if let Some(existing) = self.records.get(&key) {
            if existing.assessment_sha256 == stored_hex {
                return;
            }
            env::panic_str("digest already anchored with different bytes");
        }
        let record = DigestRecord {
            exchange,
            snapshot_id: snapshot_id.clone(),
            assessment_sha256: stored_hex,
            por_stage,
            effective_por,
            methodology_version,
            block_height: env::block_height(),
        };
        emit_anchored(&record);
        self.latest.insert(record.exchange.clone(), snapshot_id);
        self.records.insert(key, record);
    }

    pub fn get(&self, exchange: String, snapshot_id: String) -> DigestRecord {
        match self.records.get(&record_key(&exchange, &snapshot_id)) {
            Some(record) => record.clone(),
            None => env::panic_str("digest not found"),
        }
    }

    pub fn get_latest(&self, exchange: String) -> DigestRecord {
        let snapshot_id = match self.latest.get(&exchange) {
            Some(snapshot_id) => snapshot_id.clone(),
            None => env::panic_str("no digest for exchange"),
        };
        self.get(exchange, snapshot_id)
    }
}

fn require_label(name: &str, value: &str) {
    if value.is_empty() || value.contains(KEY_SEP) {
        env::panic_str(&format!("{name} is empty or contains a reserved separator"));
    }
}

fn record_key(exchange: &str, snapshot_id: &str) -> String {
    format!("{exchange}{KEY_SEP}{snapshot_id}")
}

fn decode_sha256(value: &str) -> [u8; 32] {
    let hex_str = value.strip_prefix("0x").unwrap_or(value);
    if hex_str.len() != 64 {
        env::panic_str("assessment_sha256 must be 32 bytes (64 hex chars)");
    }
    let mut out = [0u8; 32];
    for (i, chunk) in hex_str.as_bytes().chunks(2).enumerate() {
        let text = std::str::from_utf8(chunk).unwrap_or("");
        match u8::from_str_radix(text, 16) {
            Ok(byte) => out[i] = byte,
            Err(_) => env::panic_str("assessment_sha256 is not hex"),
        }
    }
    out
}

fn encode_sha256(bytes: &[u8; 32]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(64);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn emit_anchored(record: &DigestRecord) {
    let payload = format!(
        concat!(
            "EVENT_JSON:{{\"standard\":\"por_digest_anchor\",\"version\":\"1.0.0\",",
            "\"event\":\"por_digest_anchored\",\"data\":[{{",
            "\"exchange\":{exchange},\"snapshot_id\":{snapshot_id},",
            "\"assessment_sha256\":{assessment_sha256},\"por_stage\":{por_stage},",
            "\"effective_por\":{effective_por},\"methodology_version\":{methodology_version},",
            "\"block_height\":{block_height}}}]}}"
        ),
        exchange = json_string(&record.exchange),
        snapshot_id = json_string(&record.snapshot_id),
        assessment_sha256 = json_string(&record.assessment_sha256),
        por_stage = json_string(&record.por_stage),
        effective_por = if record.effective_por { "true" } else { "false" },
        methodology_version = json_string(&record.methodology_version),
        block_height = record.block_height,
    );
    env::log_str(&payload);
}

fn json_string(value: &str) -> String {
    let mut out = String::from("\"");
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::{get_logs, VMContextBuilder};
    use near_sdk::testing_env;

    fn set_context(predecessor: &str, block_height: u64) {
        let mut builder = VMContextBuilder::new();
        builder
            .predecessor_account_id(predecessor.parse().unwrap())
            .current_account_id("por-digest-anchor.sandbox".parse().unwrap())
            .block_height(block_height);
        testing_env!(builder.build());
    }

    fn setup(block_height: u64) -> Contract {
        set_context("owner.sandbox", block_height);
        Contract::new()
    }

    fn anchor(
        contract: &mut Contract,
        exchange: &str,
        snapshot_id: &str,
        hash: &str,
        stage: &str,
        effective: bool,
    ) {
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
        let mut contract = setup(7);
        let hash = "ab".repeat(32);
        anchor(&mut contract, "okx", "508756245", &hash, "Stage 1", true);
        let rec = contract.get("okx".to_string(), "508756245".to_string());
        assert_eq!(rec.assessment_sha256, hash);
        assert_eq!(decode_sha256(&rec.assessment_sha256), [0xab; 32]);
        assert_eq!(rec.exchange, "okx");
        assert_eq!(rec.snapshot_id, "508756245");
        assert_eq!(rec.por_stage, "Stage 1");
        assert!(rec.effective_por);
        assert_eq!(rec.block_height, 7);
        let logs = get_logs();
        assert!(
            logs.iter().any(|line| line.contains("por_digest_anchored") && line.contains(&hash)),
            "expected por_digest_anchored, got {logs:?}"
        );

        set_context("owner.sandbox", 8);
        anchor(
            &mut contract,
            "okx",
            "508756245",
            &format!("0x{}", hash.to_uppercase()),
            "Stage 1",
            true,
        );
        let again = contract.get("okx".to_string(), "508756245".to_string());
        assert_eq!(again.assessment_sha256, hash);
        assert_eq!(again.block_height, 7);
    }

    #[test]
    #[should_panic(expected = "different bytes")]
    fn second_different_digest_reverts() {
        let mut contract = setup(4);
        anchor(&mut contract, "okx", "508756245", &"11".repeat(32), "Stage 1", true);
        anchor(&mut contract, "okx", "508756245", &"22".repeat(32), "Stage 1", true);
    }

    #[test]
    fn get_latest_follows_the_newest_snapshot() {
        let mut contract = setup(3);
        anchor(&mut contract, "okx", "older", &"11".repeat(32), "Stage 1", true);
        set_context("owner.sandbox", 4);
        anchor(&mut contract, "okx", "newer", &"22".repeat(32), "Stage 1", true);
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
        assert_eq!(
            decode_sha256(&contract.get_latest("okx".to_string()).assessment_sha256),
            [0x22; 32]
        );

        set_context("owner.sandbox", 5);
        anchor(&mut contract, "kucoin", "20261031", &"33".repeat(32), "Stage 0", false);
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
        assert_eq!(contract.get_latest("kucoin".to_string()).snapshot_id, "20261031");

        set_context("owner.sandbox", 9);
        anchor(&mut contract, "okx", "older", &"11".repeat(32), "Stage 1", true);
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
        assert_eq!(
            contract.get("okx".to_string(), "older".to_string()).block_height,
            3
        );
    }

    #[test]
    #[should_panic(expected = "only the account that deployed")]
    fn other_predecessor_cannot_anchor() {
        let mut contract = setup(1);
        set_context("other.sandbox", 2);
        anchor(&mut contract, "okx", "508756245", &"11".repeat(32), "Stage 1", true);
    }
}
