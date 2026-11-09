//! Stores a Sepolia-aligned PoR snapshot record plus the assessment sha256.
//! Schema mirrors ArdmerePoRAnchor SnapshotRecord v5 (upstream ardmere.github.io).
//! Does not verify reserves, fetch exchanges, or hold funds.

use near_sdk::{env, near, AccountId, PanicOnDefault};
use std::collections::HashMap;

const KEY_SEP: char = '\u{1}';
const PERIOD_KEY_SEP: char = '\u{2}';

/// Matches ArdmerePoRAnchor SCHEMA_VERSION on Sepolia (v5 = custody risk score on record).
pub const SCHEMA_VERSION: u8 = 5;

/// On-chain encoding when no conclusive custody score is stored (Sepolia v5 semantics).
pub const CUSTODY_RISK_INCONCLUSIVE: u8 = 255;

#[near(serializers = [borsh, json])]
#[derive(Clone, PartialEq, Debug)]
pub struct SnapshotRecord {
    /// Plaintext audit id (NEAR query key). Sepolia v6 stores composite hash as snapshotId.
    pub snapshot_id: String,
    /// expectedSnapshotId: keccak256(utf8(exchange) ++ 0x00 ++ utf8(snapshot_id)), 64 hex.
    /// Legacy anchors may still hold keccak256(utf8(snapshot_id)) until re-anchored.
    pub snapshot_id_hash: String,
    /// keccak256(utf8(exchange)) as 64 lowercase hex chars.
    pub exchange_tag: String,
    pub exchange: String,
    pub period_seq: u32,
    /// Exchange snapshot UTC unix seconds.
    pub snapshot_time: u64,
    pub btc_block_height: u32,
    /// 64 hex chars; all-zero when the exchange published no root.
    pub exchange_merkle_root: String,
    pub artifact_bundle_root: String,
    pub verification_bundle_root: String,
    pub verdict_summary: u8,
    /// Deprecated opaque max(verifier Coverage)×10000. Prefer wallet/reserve fields.
    pub coverage_bps: u16,
    pub schema_version: u8,
    /// NEAR block_timestamp at anchor time, in seconds.
    pub anchored_at: u64,
    /// 0=Pre-Stage, 1=Stage 0, 2=Stage 1, 3=Stage 2.
    pub por_stage: u8,
    pub effective_por: bool,
    pub wallet_coverage_bps: u16,
    pub reserve_coverage_bps: u16,
    /// NEAR-demo binding: sha256 of the assessment JSON file (64 hex).
    pub assessment_sha256: String,
    pub methodology_version: String,
    /// NEAR block height at anchor time.
    pub block_height: u64,
    /// Custody risk 0–100 at anchor time; 255 = inconclusive (no score committed).
    pub custody_risk_score: u8,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    owner: AccountId,
    records: HashMap<String, SnapshotRecord>,
    /// (exchange_tag, snapshot_id_hash) → record_key(exchange, snapshot_id)
    by_snapshot_id_hash: HashMap<String, String>,
    /// Manifest / demo pointer: plaintext exchange → snapshot_id
    latest: HashMap<String, String>,
    /// Last chronologically anchored snapshot per exchange_tag (Sepolia latestSnapshotId)
    latest_by_tag: HashMap<String, String>,
    /// exchange_tag → snapshot_id_hash values in anchor order (0 = earliest)
    snapshot_ids: HashMap<String, Vec<String>>,
    snapshot_count: HashMap<String, u64>,
    /// exchange_tag + period_seq → snapshot_id_hash
    snapshot_by_period: HashMap<String, String>,
}

#[near]
impl Contract {
    #[init]
    pub fn new() -> Self {
        Self {
            owner: env::predecessor_account_id(),
            records: HashMap::new(),
            by_snapshot_id_hash: HashMap::new(),
            latest: HashMap::new(),
            latest_by_tag: HashMap::new(),
            snapshot_ids: HashMap::new(),
            snapshot_count: HashMap::new(),
            snapshot_by_period: HashMap::new(),
        }
    }

    pub fn schema_version(&self) -> u8 {
        SCHEMA_VERSION
    }

    pub fn anchor(
        &mut self,
        exchange: String,
        snapshot_id: String,
        period_seq: u32,
        snapshot_time: u64,
        btc_block_height: u32,
        exchange_merkle_root: String,
        artifact_bundle_root: String,
        verification_bundle_root: String,
        verdict_summary: u8,
        coverage_bps: u16,
        por_stage: u8,
        effective_por: bool,
        wallet_coverage_bps: u16,
        reserve_coverage_bps: u16,
        assessment_sha256: String,
        methodology_version: String,
        custody_risk_score: u8,
    ) {
        if env::predecessor_account_id() != self.owner {
            env::panic_str("only the account that deployed this contract may anchor");
        }
        require_label("exchange", &exchange);
        require_label("snapshot_id", &snapshot_id);
        if methodology_version.is_empty() {
            env::panic_str("methodology_version is required");
        }
        if por_stage > 3 {
            env::panic_str("por_stage must be 0..=3");
        }
        require_custody_risk_score(custody_risk_score);
        let exchange = exchange.to_ascii_lowercase();
        let exchange_root = normalize_root(&exchange_merkle_root, true);
        let artifact_root = normalize_root(&artifact_bundle_root, false);
        let verification_root = normalize_root(&verification_bundle_root, false);
        let assessment_hex = encode_sha256(&decode_sha256(&assessment_sha256));
        let key = record_key(&exchange, &snapshot_id);
        if let Some(existing) = self.records.get(&key) {
            if existing.assessment_sha256 == assessment_hex
                && existing.artifact_bundle_root == artifact_root
                && existing.verification_bundle_root == verification_root
                && existing.exchange_merkle_root == exchange_root
                && existing.custody_risk_score == custody_risk_score
            {
                return;
            }
            env::panic_str("snapshot already anchored with different bytes");
        }
        let record = SnapshotRecord {
            snapshot_id_hash: expected_snapshot_id_hash(&exchange, &snapshot_id),
            exchange_tag: keccak_hex(exchange.as_bytes()),
            exchange,
            snapshot_id: snapshot_id.clone(),
            period_seq,
            snapshot_time,
            btc_block_height,
            exchange_merkle_root: exchange_root,
            artifact_bundle_root: artifact_root,
            verification_bundle_root: verification_root,
            verdict_summary,
            coverage_bps,
            schema_version: SCHEMA_VERSION,
            anchored_at: env::block_timestamp() / 1_000_000_000,
            por_stage,
            effective_por,
            wallet_coverage_bps,
            reserve_coverage_bps,
            assessment_sha256: assessment_hex,
            methodology_version,
            block_height: env::block_height(),
            custody_risk_score,
        };
        emit_anchored(&record);
        self.latest.insert(record.exchange.clone(), snapshot_id);
        self.records.insert(key.clone(), record.clone());
        self.register_indices(&record, &key);
    }

    /// Whether a snapshot exists, scoped by exchange tag and snapshot id hash.
    /// Accepts Sepolia v6 composite id or legacy keccak256(auditId) (dual-read).
    pub fn snapshot_exists(&self, exchange_tag: String, snapshot_id_hash: String) -> bool {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        let hash = require_hex32("snapshot_id_hash", &snapshot_id_hash);
        self.resolve_record_key_for_hash(&tag, &hash).is_some()
    }

    /// Fetch one snapshot by exchange tag and snapshot id hash (composite or legacy).
    pub fn get_snapshot(&self, exchange_tag: String, snapshot_id_hash: String) -> SnapshotRecord {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        let hash = require_hex32("snapshot_id_hash", &snapshot_id_hash);
        self.record_by_tagged_snapshot_id_hash(&tag, &hash)
    }

    /// Sepolia v6 expectedSnapshotId for an exchange slug and plaintext audit id.
    pub fn expected_snapshot_id(&self, exchange: String, snapshot_id: String) -> String {
        require_label("exchange", &exchange);
        require_label("snapshot_id", &snapshot_id);
        expected_snapshot_id_hash(&exchange.to_ascii_lowercase(), &snapshot_id)
    }

    /// Most recently anchored snapshot for an exchange tag (Sepolia getLatestSnapshot).
    pub fn get_latest_snapshot(&self, exchange_tag: String) -> SnapshotRecord {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        let snapshot_id_hash = match self.latest_by_tag.get(&tag) {
            Some(value) => value.clone(),
            None => env::panic_str("snapshot not found"),
        };
        self.record_by_tagged_snapshot_id_hash(&tag, &snapshot_id_hash)
    }

    /// Fetch a snapshot by exchange tag and period sequence (Sepolia getSnapshotByPeriod).
    pub fn get_snapshot_by_period(&self, exchange_tag: String, period_seq: u32) -> SnapshotRecord {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        let period_key = period_map_key(&tag, period_seq);
        let snapshot_id_hash = match self.snapshot_by_period.get(&period_key) {
            Some(value) => value.clone(),
            None => env::panic_str("snapshot not found"),
        };
        self.record_by_tagged_snapshot_id_hash(&tag, &snapshot_id_hash)
    }

    /// Number of anchored snapshots for an exchange tag (Sepolia getSnapshotCount).
    pub fn get_snapshot_count(&self, exchange_tag: String) -> u64 {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        *self.snapshot_count.get(&tag).unwrap_or(&0)
    }

    /// Snapshot id hash at chronological index, 0 = earliest (Sepolia getSnapshotIdAt).
    pub fn get_snapshot_id_at(&self, exchange_tag: String, index: u64) -> String {
        let tag = require_hex32("exchange_tag", &exchange_tag);
        let ids = match self.snapshot_ids.get(&tag) {
            Some(values) => values,
            None => env::panic_str("snapshot index out of bounds"),
        };
        let idx = usize::try_from(index).unwrap_or_else(|_| env::panic_str("snapshot index out of bounds"));
        if idx >= ids.len() {
            env::panic_str("snapshot index out of bounds");
        }
        ids[idx].clone()
    }

    /// Point get_latest at a snapshot that is already stored.
    /// anchor() moves the pointer on every new write, including an older snapshot
    /// that arrives after a newer one. The manifest order is the source of which
    /// snapshot is current, so the publisher calls this after reconciling.
    /// Set or refresh custody_risk_score on an existing snapshot (owner only).
    /// Other snapshot fields must stay unchanged; used to backfill v4 rows after upgrade.
    pub fn set_custody_risk_score(
        &mut self,
        exchange: String,
        snapshot_id: String,
        custody_risk_score: u8,
    ) {
        if env::predecessor_account_id() != self.owner {
            env::panic_str("only the account that deployed this contract may anchor");
        }
        require_label("exchange", &exchange);
        require_label("snapshot_id", &snapshot_id);
        require_custody_risk_score(custody_risk_score);
        let key = record_key(&exchange, &snapshot_id);
        let record = match self.records.get_mut(&key) {
            Some(value) => value,
            None => env::panic_str("snapshot not found"),
        };
        record.custody_risk_score = custody_risk_score;
        record.schema_version = SCHEMA_VERSION;
        emit_anchored(record);
    }

    pub fn point_latest(&mut self, exchange: String, snapshot_id: String) {
        if env::predecessor_account_id() != self.owner {
            env::panic_str("only the account that deployed this contract may anchor");
        }
        require_label("exchange", &exchange);
        require_label("snapshot_id", &snapshot_id);
        if self.records.get(&record_key(&exchange, &snapshot_id)).is_none() {
            env::panic_str("snapshot not found");
        }
        self.latest.insert(exchange, snapshot_id);
    }

    pub fn get(&self, exchange: String, snapshot_id: String) -> SnapshotRecord {
        match self.records.get(&record_key(&exchange, &snapshot_id)) {
            Some(record) => record.clone(),
            None => env::panic_str("snapshot not found"),
        }
    }

    pub fn get_latest(&self, exchange: String) -> SnapshotRecord {
        let snapshot_id = match self.latest.get(&exchange) {
            Some(snapshot_id) => snapshot_id.clone(),
            None => env::panic_str("no snapshot for exchange"),
        };
        self.get(exchange, snapshot_id)
    }

    fn register_indices(&mut self, record: &SnapshotRecord, record_key: &str) {
        let tag = record.exchange_tag.clone();
        let snapshot_id_hash = record.snapshot_id_hash.clone();
        let tagged_hash = tagged_snapshot_hash_key(&tag, &snapshot_id_hash);
        if self.by_snapshot_id_hash.contains_key(&tagged_hash) {
            env::panic_str("snapshot id hash already anchored for this exchange");
        }
        self.by_snapshot_id_hash
            .insert(tagged_hash, record_key.to_string());
        self.snapshot_ids
            .entry(tag.clone())
            .or_default()
            .push(snapshot_id_hash.clone());
        *self.snapshot_count.entry(tag.clone()).or_insert(0) += 1;
        self.latest_by_tag.insert(tag.clone(), snapshot_id_hash.clone());
        // Assessments often carry periodSeq 0 as a placeholder; only index real periods.
        if record.period_seq > 0 {
            let period_key = period_map_key(&tag, record.period_seq);
            if let Some(existing) = self.snapshot_by_period.get(&period_key) {
                if existing != &snapshot_id_hash {
                    env::panic_str("period already anchored with a different snapshot");
                }
            } else {
                self.snapshot_by_period.insert(period_key, snapshot_id_hash);
            }
        }
    }

    fn record_by_tagged_snapshot_id_hash(
        &self,
        exchange_tag: &str,
        snapshot_id_hash: &str,
    ) -> SnapshotRecord {
        let record_key = match self.resolve_record_key_for_hash(exchange_tag, snapshot_id_hash) {
            Some(value) => value,
            None => env::panic_str("snapshot not found"),
        };
        match self.records.get(&record_key) {
            Some(record) => record.clone(),
            None => env::panic_str("snapshot not found"),
        }
    }

    /// Primary index lookup, then scan for dual-read (composite vs legacy audit-only hash).
    fn resolve_record_key_for_hash(
        &self,
        exchange_tag: &str,
        snapshot_id_hash: &str,
    ) -> Option<String> {
        let tagged = tagged_snapshot_hash_key(exchange_tag, snapshot_id_hash);
        if let Some(key) = self.by_snapshot_id_hash.get(&tagged) {
            return Some(key.clone());
        }
        for (record_key, record) in &self.records {
            if record.exchange_tag != exchange_tag {
                continue;
            }
            let composite = expected_snapshot_id_hash(&record.exchange, &record.snapshot_id);
            let legacy = legacy_snapshot_id_hash(&record.snapshot_id);
            if snapshot_id_hash == composite || snapshot_id_hash == legacy {
                return Some(record_key.clone());
            }
        }
        None
    }
}

fn require_custody_risk_score(value: u8) {
    if value > 100 && value != CUSTODY_RISK_INCONCLUSIVE {
        env::panic_str("custody_risk_score must be 0..=100 or 255");
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

fn period_map_key(exchange_tag: &str, period_seq: u32) -> String {
    format!("{exchange_tag}{PERIOD_KEY_SEP}{period_seq}")
}

fn tagged_snapshot_hash_key(exchange_tag: &str, snapshot_id_hash: &str) -> String {
    format!("{exchange_tag}{KEY_SEP}{snapshot_id_hash}")
}

fn require_hex32(name: &str, value: &str) -> String {
    let hex = value.strip_prefix("0x").unwrap_or(value).to_ascii_lowercase();
    if hex.len() != 64 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
        env::panic_str(&format!("{name} must be 32 bytes (64 hex chars)"));
    }
    hex
}

fn keccak_hex(bytes: &[u8]) -> String {
    encode_sha256(
        &env::keccak256(bytes)
            .try_into()
            .unwrap_or_else(|_| env::panic_str("keccak256 did not return 32 bytes")),
    )
}

fn expected_snapshot_id_hash(exchange: &str, snapshot_id: &str) -> String {
    let exchange_lower = exchange.to_ascii_lowercase();
    let mut payload = exchange_lower.into_bytes();
    payload.push(0);
    payload.extend_from_slice(snapshot_id.as_bytes());
    keccak_hex(&payload)
}

fn legacy_snapshot_id_hash(snapshot_id: &str) -> String {
    keccak_hex(snapshot_id.as_bytes())
}

fn normalize_root(value: &str, allow_zero: bool) -> String {
    let bytes = decode_root(value);
    if !allow_zero && bytes == [0u8; 32] {
        env::panic_str("bundle root must be non-zero");
    }
    encode_sha256(&bytes)
}

fn decode_root(value: &str) -> [u8; 32] {
    let hex_str = value.strip_prefix("0x").unwrap_or(value);
    if hex_str.is_empty() {
        return [0u8; 32];
    }
    decode_sha256(hex_str)
}

fn decode_sha256(value: &str) -> [u8; 32] {
    let hex_str = value.strip_prefix("0x").unwrap_or(value);
    if hex_str.len() != 64 {
        env::panic_str("hex root/digest must be 32 bytes (64 hex chars)");
    }
    let mut out = [0u8; 32];
    for (i, chunk) in hex_str.as_bytes().chunks(2).enumerate() {
        let text = std::str::from_utf8(chunk).unwrap_or("");
        match u8::from_str_radix(text, 16) {
            Ok(byte) => out[i] = byte,
            Err(_) => env::panic_str("hex root/digest is not hex"),
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

fn emit_anchored(record: &SnapshotRecord) {
    let payload = format!(
        concat!(
            "EVENT_JSON:{{\"standard\":\"por_digest_anchor\",\"version\":\"5.0.0\",",
            "\"event\":\"por_snapshot_anchored\",\"data\":[{{",
            "\"exchange\":{exchange},\"snapshot_id\":{snapshot_id},",
            "\"snapshot_id_hash\":{snapshot_id_hash},\"exchange_tag\":{exchange_tag},",
            "\"period_seq\":{period_seq},\"snapshot_time\":{snapshot_time},",
            "\"btc_block_height\":{btc_block_height},",
            "\"exchange_merkle_root\":{exchange_merkle_root},",
            "\"artifact_bundle_root\":{artifact_bundle_root},",
            "\"verification_bundle_root\":{verification_bundle_root},",
            "\"verdict_summary\":{verdict_summary},\"coverage_bps\":{coverage_bps},",
            "\"schema_version\":{schema_version},\"anchored_at\":{anchored_at},",
            "\"por_stage\":{por_stage},\"effective_por\":{effective_por},",
            "\"wallet_coverage_bps\":{wallet_coverage_bps},",
            "\"reserve_coverage_bps\":{reserve_coverage_bps},",
            "\"assessment_sha256\":{assessment_sha256},",
            "\"methodology_version\":{methodology_version},",
            "\"block_height\":{block_height},",
            "\"custody_risk_score\":{custody_risk_score}}}]}}"
        ),
        exchange = json_string(&record.exchange),
        snapshot_id = json_string(&record.snapshot_id),
        snapshot_id_hash = json_string(&record.snapshot_id_hash),
        exchange_tag = json_string(&record.exchange_tag),
        period_seq = record.period_seq,
        snapshot_time = record.snapshot_time,
        btc_block_height = record.btc_block_height,
        exchange_merkle_root = json_string(&record.exchange_merkle_root),
        artifact_bundle_root = json_string(&record.artifact_bundle_root),
        verification_bundle_root = json_string(&record.verification_bundle_root),
        verdict_summary = record.verdict_summary,
        coverage_bps = record.coverage_bps,
        schema_version = record.schema_version,
        anchored_at = record.anchored_at,
        por_stage = record.por_stage,
        effective_por = if record.effective_por { "true" } else { "false" },
        wallet_coverage_bps = record.wallet_coverage_bps,
        reserve_coverage_bps = record.reserve_coverage_bps,
        assessment_sha256 = json_string(&record.assessment_sha256),
        methodology_version = json_string(&record.methodology_version),
        block_height = record.block_height,
        custody_risk_score = record.custody_risk_score,
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
            .block_height(block_height)
            .block_timestamp(1_700_000_000_000_000_000);
        testing_env!(builder.build());
    }

    fn setup(block_height: u64) -> Contract {
        set_context("owner.sandbox", block_height);
        Contract::new()
    }

    fn sample_roots(seed: u8) -> (String, String, String) {
        (
            "00".repeat(32),
            format!("{:02x}", seed).repeat(32),
            format!("{:02x}", seed.wrapping_add(1)).repeat(32),
        )
    }

    fn anchor_with_period(
        contract: &mut Contract,
        exchange: &str,
        snapshot_id: &str,
        assessment_hash: &str,
        period_seq: u32,
        stage: u8,
        effective: bool,
        seed: u8,
        custody_risk_score: u8,
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
            assessment_hash.to_string(),
            "por-transparency-framework@2026-07-01".to_string(),
            custody_risk_score,
        );
    }

    fn anchor(
        contract: &mut Contract,
        exchange: &str,
        snapshot_id: &str,
        assessment_hash: &str,
        stage: u8,
        effective: bool,
        seed: u8,
    ) {
        anchor_with_period(
            contract,
            exchange,
            snapshot_id,
            assessment_hash,
            1,
            stage,
            effective,
            seed,
            10,
        );
    }

    #[test]
    fn schema_version_is_v5() {
        let contract = setup(1);
        assert_eq!(contract.schema_version(), 5);
    }

    #[test]
    fn anchor_then_get_returns_the_same_bytes() {
        let mut contract = setup(7);
        let hash = "ab".repeat(32);
        anchor(&mut contract, "okx", "508756245", &hash, 2, true, 0xab);
        let rec = contract.get("okx".to_string(), "508756245".to_string());
        assert_eq!(rec.assessment_sha256, hash);
        assert_eq!(decode_sha256(&rec.assessment_sha256), [0xab; 32]);
        assert_eq!(rec.exchange, "okx");
        assert_eq!(rec.snapshot_id, "508756245");
        assert_eq!(rec.por_stage, 2);
        assert!(rec.effective_por);
        assert_eq!(rec.schema_version, 5);
        assert_eq!(rec.custody_risk_score, 10);
        assert_eq!(rec.block_height, 7);
        assert_eq!(rec.anchored_at, 1_700_000_000);
        assert_eq!(rec.exchange_tag, keccak_hex(b"okx"));
        assert_eq!(
            rec.snapshot_id_hash,
            expected_snapshot_id_hash("okx", "508756245")
        );
        assert_eq!(rec.artifact_bundle_root, "ab".repeat(32));
        assert_eq!(rec.verification_bundle_root, "ac".repeat(32));
        let logs = get_logs();
        assert!(
            logs
                .iter()
                .any(|line| line.contains("por_snapshot_anchored") && line.contains(&hash)),
            "expected por_snapshot_anchored, got {logs:?}"
        );

        set_context("owner.sandbox", 8);
        anchor(
            &mut contract,
            "okx",
            "508756245",
            &format!("0x{}", hash.to_uppercase()),
            2,
            true,
            0xab,
        );
        let again = contract.get("okx".to_string(), "508756245".to_string());
        assert_eq!(again.assessment_sha256, hash);
        assert_eq!(again.block_height, 7);
    }

    #[test]
    #[should_panic(expected = "different bytes")]
    fn second_different_digest_reverts() {
        let mut contract = setup(4);
        anchor(&mut contract, "okx", "508756245", &"11".repeat(32), 2, true, 0x11);
        anchor(&mut contract, "okx", "508756245", &"22".repeat(32), 2, true, 0x22);
    }

    #[test]
    fn get_latest_follows_the_newest_snapshot() {
        let mut contract = setup(3);
        anchor_with_period(&mut contract, "okx", "older", &"11".repeat(32), 1, 2, true, 0x11, 10);
        set_context("owner.sandbox", 4);
        anchor_with_period(&mut contract, "okx", "newer", &"22".repeat(32), 2, 2, true, 0x22, 10);
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
        assert_eq!(
            decode_sha256(&contract.get_latest("okx".to_string()).assessment_sha256),
            [0x22; 32]
        );

        set_context("owner.sandbox", 5);
        anchor_with_period(&mut contract, "kucoin", "20261031", &"33".repeat(32), 1, 1, false, 0x33, 75);
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "newer");
        assert_eq!(contract.get_latest("kucoin".to_string()).snapshot_id, "20261031");

        set_context("owner.sandbox", 9);
        anchor_with_period(&mut contract, "okx", "older", &"11".repeat(32), 1, 2, true, 0x11, 10);
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
        anchor(&mut contract, "okx", "508756245", &"11".repeat(32), 2, true, 0x11);
    }

    #[test]
    fn sepolia_query_surface() {
        let mut contract = setup(1);
        anchor_with_period(
            &mut contract,
            "okx",
            "older",
            &"11".repeat(32),
            5,
            2,
            true,
            0x11,
            10,
        );
        set_context("owner.sandbox", 2);
        anchor_with_period(
            &mut contract,
            "okx",
            "newer",
            &"22".repeat(32),
            6,
            2,
            true,
            0x22,
            10,
        );
        let tag = keccak_hex(b"okx");
        assert_eq!(contract.get_snapshot_count(tag.clone()), 2);
        let first = contract.get_snapshot_id_at(tag.clone(), 0);
        let second = contract.get_snapshot_id_at(tag.clone(), 1);
        assert_eq!(first, expected_snapshot_id_hash("okx", "older"));
        assert_eq!(second, expected_snapshot_id_hash("okx", "newer"));
        assert!(contract.snapshot_exists(tag.clone(), second.clone()));
        assert_eq!(
            contract
                .get_snapshot(tag.clone(), second.clone())
                .snapshot_id,
            "newer"
        );
        let legacy_second = legacy_snapshot_id_hash("newer");
        assert!(contract.snapshot_exists(tag.clone(), legacy_second.clone()));
        assert_eq!(
            contract.get_snapshot(tag.clone(), legacy_second).snapshot_id,
            "newer"
        );
        assert_eq!(contract.get_latest_snapshot(tag.clone()).snapshot_id, "newer");
        assert_eq!(contract.get_snapshot_by_period(tag, 5).snapshot_id, "older");
    }

    #[test]
    fn expected_snapshot_id_view_matches_record() {
        let mut contract = setup(1);
        anchor(&mut contract, "okx", "508756245", &"11".repeat(32), 2, true, 0x11);
        let expected = contract.expected_snapshot_id("okx".to_string(), "508756245".to_string());
        assert_eq!(
            expected,
            contract
                .get("okx".to_string(), "508756245".to_string())
                .snapshot_id_hash
        );
    }

    #[test]
    fn get_latest_snapshot_differs_from_manifest_pointer() {
        let mut contract = setup(1);
        anchor_with_period(&mut contract, "okx", "older", &"11".repeat(32), 3, 2, true, 0x11, 10);
        set_context("owner.sandbox", 2);
        anchor_with_period(&mut contract, "okx", "newer", &"22".repeat(32), 4, 2, true, 0x22, 10);
        contract.point_latest("okx".to_string(), "older".to_string());
        assert_eq!(contract.get_latest("okx".to_string()).snapshot_id, "older");
        let tag = keccak_hex(b"okx");
        assert_eq!(contract.get_latest_snapshot(tag).snapshot_id, "newer");
    }
}
