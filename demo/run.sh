#!/usr/bin/env bash
# Local NEAR sandbox: deploy por_digest_anchor, anchor the fixture digests, print risk scores, serve the dashboard.
# No mainnet, no testnet account, no key file in the repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

refuse() {
  echo "demo/run.sh: $*" >&2
  exit 1
}

check_pointed_at() {
  local label="$1"
  local value="$2"
  [[ -z "$value" ]] && return 0
  local lower
  lower="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    *mainnet*|*testnet*)
      refuse "refusing ${label} (${value}). This script does not use mainnet or testnet."
      ;;
  esac
  if [[ "$value" == *.near ]]; then
    refuse "refusing named .near account in ${label}. Sandbox accounts are created inside the script."
  fi
}

for arg in "$@"; do
  check_pointed_at "argument" "$arg"
done
for var in NEAR_ENV NEAR_NETWORK NEAR_RPC_URL NEAR_ACCOUNT_ID NEAR_ACCOUNT NEAR_SIGNER; do
  check_pointed_at "$var" "${!var-}"
done

if [[ ! -e "$ROOT/vendor/ardmere.github.io/docs/reports/okx/508756245-assessment.json" ]]; then
  refuse "submodule vendor/ardmere.github.io is missing. Run: git submodule update --init --recursive"
fi

command -v cargo >/dev/null 2>&1 || refuse "cargo is not installed"
command -v rustup >/dev/null 2>&1 || refuse "rustup is not installed"
rustup target list --installed | grep -q '^wasm32-unknown-unknown$' || refuse "rust target wasm32-unknown-unknown is not installed"
command -v python3 >/dev/null 2>&1 || refuse "python3 is not installed"
command -v curl >/dev/null 2>&1 || refuse "curl is not installed"

if command -v near >/dev/null 2>&1; then
  NEAR=(near)
else
  refuse "near (near-cli-rs) is not installed"
fi

if command -v near-sandbox >/dev/null 2>&1; then
  SANDBOX=(near-sandbox)
elif command -v npx >/dev/null 2>&1; then
  SANDBOX=(npx --yes near-sandbox@0.3.5)
else
  refuse "near-sandbox is not installed"
fi

WORKDIR="$(mktemp -d /tmp/por-digest-sandbox-XXXX)"
CLI_HOME="$WORKDIR/cli-home"
SANDBOX_HOME="$WORKDIR/sandbox"
mkdir -p "$CLI_HOME/.config/near-cli" "$CLI_HOME/.near-credentials"
export HOME="$CLI_HOME"
export XDG_CONFIG_HOME="$CLI_HOME/.config"
export XDG_DATA_HOME="$CLI_HOME/.local/share"
unset NEAR_ENV NEAR_NETWORK NEAR_RPC_URL NEAR_ACCOUNT_ID NEAR_ACCOUNT NEAR_SIGNER || true

SANDBOX_PID=""
cleanup() {
  if [[ -n "$SANDBOX_PID" ]] && kill -0 "$SANDBOX_PID" 2>/dev/null; then
    kill -- "-$SANDBOX_PID" 2>/dev/null || kill "$SANDBOX_PID" 2>/dev/null || true
    wait "$SANDBOX_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "sandbox home: $SANDBOX_HOME (local process only)"
"${SANDBOX[@]}" --home "$SANDBOX_HOME" init

python3 - "$SANDBOX_HOME" <<'PY'
import json, sys
from pathlib import Path
home = Path(sys.argv[1])
config_path = home / "config.json"
config = json.loads(config_path.read_text())
# nearcore config nests the RPC address. Force loopback only.
def rewrite(node):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key in {"addr", "rpc_addr"} and isinstance(value, str) and value.startswith("0.0.0.0:"):
                node[key] = "127.0.0.1:" + value.split(":", 1)[1]
            else:
                rewrite(value)
    elif isinstance(node, list):
        for item in node:
            rewrite(item)
rewrite(config)
config_path.write_text(json.dumps(config, indent=2) + "\n")
PY

RPC_PORT="$(python3 - "$SANDBOX_HOME/config.json" <<'PY'
import json, sys
config = json.loads(open(sys.argv[1]).read())
found = []
def walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"addr", "rpc_addr"} and isinstance(value, str) and "3030" in value:
                found.append(value.rsplit(":", 1)[-1])
            else:
                walk(value)
    elif isinstance(node, list):
        for item in node:
            walk(item)
walk(config)
print(found[0] if found else "3030")
PY
)"
RPC="http://127.0.0.1:${RPC_PORT}"
case "$RPC" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) refuse "sandbox RPC is not loopback: $RPC" ;;
esac

cat > "$CLI_HOME/.config/near-cli/config.toml" <<EOF
version = "5"
credentials_home_dir = "${CLI_HOME}/.near-credentials"

[network_connection.sandbox]
network_name = "sandbox"
rpc_url = "${RPC}/"
wallet_url = "http://127.0.0.1/"
explorer_transaction_url = "http://127.0.0.1/"
EOF

connections="$("${NEAR[@]}" config show-connections 2>&1 || true)"
printf '%s\n' "$connections" | grep -q "$RPC" || refuse "sandbox connection was not loaded"
if printf '%s\n' "$connections" | grep -Eiq 'mainnet|testnet'; then
  refuse "near CLI config includes mainnet or testnet; refusing to continue"
fi

echo "starting NEAR sandbox at $RPC"
setsid "${SANDBOX[@]}" --home "$SANDBOX_HOME" run >"$WORKDIR/sandbox.log" 2>&1 &
SANDBOX_PID=$!

ready=0
for _ in $(seq 1 90); do
  if curl -sf "$RPC/status" >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$SANDBOX_PID" 2>/dev/null; then
    echo "sandbox exited early. log:" >&2
    cat "$WORKDIR/sandbox.log" >&2 || true
    refuse "sandbox did not stay up"
  fi
  sleep 0.5
done
[[ "$ready" -eq 1 ]] || refuse "sandbox RPC did not answer at $RPC. See $WORKDIR/sandbox.log"

KEY_FILE="$(find "$SANDBOX_HOME" -name 'validator_key.json' -print -quit)"
[[ -n "$KEY_FILE" ]] || refuse "sandbox did not write validator_key.json"
SIGNER_KEY="$WORKDIR/signer-key.json"
python3 - "$KEY_FILE" "$SIGNER_KEY" <<'PY'
import json, sys
src = json.load(open(sys.argv[1]))
secret = src.get("private_key") or src.get("secret_key")
if not secret or "public_key" not in src:
    raise SystemExit("sandbox key file is missing a key pair")
json.dump({"public_key": src["public_key"], "private_key": secret}, open(sys.argv[2], "w"))
PY
PARENT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["account_id"])' "$KEY_FILE")"
echo "sandbox-only genesis signer: $PARENT"
CONTRACT="por-digest-anchor.${PARENT}"
echo "sandbox-only contract account: $CONTRACT"

timeout 180 "${NEAR[@]}" account create-account fund-myself "$CONTRACT" '20 NEAR' \
  autogenerate-new-keypair save-to-legacy-keychain \
  sign-as "$PARENT" \
  network-config sandbox \
  sign-with-access-key-file "$SIGNER_KEY" \
  send

echo "building por_digest_anchor wasm"
cargo build --manifest-path contracts/por_digest_anchor/Cargo.toml --target wasm32-unknown-unknown --release
WASM="contracts/por_digest_anchor/target/wasm32-unknown-unknown/release/por_digest_anchor.wasm"
[[ -f "$WASM" ]] || refuse "wasm build did not produce $WASM"

echo "deploying to sandbox-only account $CONTRACT"
timeout 180 "${NEAR[@]}" contract deploy "$CONTRACT" \
  use-file "$WASM" \
  with-init-call new json-args '{}' \
  prepaid-gas '80 Tgas' \
  attached-deposit '0 NEAR' \
  network-config sandbox \
  sign-with-legacy-keychain \
  send

mkdir -p "$WORKDIR/args" "$WORKDIR/views"
python3 - "$ROOT" "$WORKDIR" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
work = Path(sys.argv[2])
sys.path.insert(0, str(root / "scripts"))
from por_snapshot import build_anchor_args
digests = json.loads((root / "fixtures/digests.json").read_text())
files = [(root / row["path"]) for row in digests["assessments"]]
listed = {row["path"] for row in digests["assessments"]}
found = set()
for path in files:
    rel = path.relative_to(root).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    row = next((item for item in digests["assessments"] if item["path"] == rel), None)
    if row is None or row["sha256"] != digest:
        raise SystemExit(f"sha256 mismatch for {rel}")
    found.add(rel)
    assessment = json.loads(path.read_text())
    args = build_anchor_args(assessment, digest)
    name = f"{args['exchange']}-{args['snapshot_id']}.json"
    (work / "args" / name).write_text(json.dumps(args))
if found != listed:
    raise SystemExit(f"assessment set {found} != digests.json {listed}")
print("fixture sha256 matches digests.json")
PY

for args in "$WORKDIR"/args/*.json; do
  echo "anchoring $(basename "$args")"
  timeout 180 "${NEAR[@]}" contract call-function as-transaction "$CONTRACT" anchor file-args "$args" \
    prepaid-gas '80 Tgas' \
    attached-deposit '0 NEAR' \
    sign-as "$CONTRACT" \
    network-config sandbox \
    sign-with-legacy-keychain \
    send
done

python3 - "$ROOT" "$WORKDIR/latest.jsonl" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
out = Path(sys.argv[2])
digests = json.loads((root / "fixtures/digests.json").read_text())
newest = {}
for row in digests["assessments"]:
    newest[row["exchange"]] = str(row["snapshotId"])
out.write_text("".join(json.dumps({"exchange": e, "snapshot_id": s}) + "\n" for e, s in sorted(newest.items())))
PY
while IFS= read -r latest; do
  [ -z "$latest" ] && continue
  echo "point_latest $latest"
  timeout 120 "${NEAR[@]}" contract call-function as-transaction "$CONTRACT" point_latest json-args "$latest" \
    prepaid-gas '30 Tgas' \
    attached-deposit '0 NEAR' \
    sign-as "$CONTRACT" \
    network-config sandbox \
    sign-with-legacy-keychain \
    send
done < "$WORKDIR/latest.jsonl"

python3 - "$ROOT" "$WORKDIR/calls.txt" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
out = Path(sys.argv[2])
digests = json.loads((root / "fixtures/digests.json").read_text())
lines = []
for row in digests["assessments"]:
    lines.append(json.dumps({"method": "get", "args": {"exchange": row["exchange"], "snapshot_id": row["snapshotId"]}}))
    lines.append(json.dumps({"method": "get_latest", "args": {"exchange": row["exchange"]}}))
out.write_text("\n".join(lines) + "\n")
PY

: > "$WORKDIR/view-results.jsonl"
while IFS= read -r call; do
  method="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["method"])' "$call")"
  args="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["args"]))' "$call")"
  echo "view $method $args"
  raw="$(timeout 120 "${NEAR[@]}" --quiet contract call-function as-read-only "$CONTRACT" "$method" json-args "$args" network-config sandbox now)"
  printf '%s\n' "$raw" > "$WORKDIR/last-view.txt"
  python3 - "$call" "$WORKDIR/last-view.txt" "$WORKDIR/view-results.jsonl" <<'PY'
import json, sys
from pathlib import Path
call = json.loads(sys.argv[1])
text = Path(sys.argv[2]).read_text()
decoder = json.JSONDecoder()
found = []
for index, char in enumerate(text):
    if char not in "{[":
        continue
    try:
        obj, _end = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    found.append(obj)

def has_hash(node):
    if isinstance(node, dict) and "assessment_sha256" in node:
        return node
    if isinstance(node, dict):
        for value in node.values():
            hit = has_hash(value)
            if hit is not None:
                return hit
    if isinstance(node, list):
        for value in node:
            hit = has_hash(value)
            if hit is not None:
                return hit
    return None

result = None
for obj in reversed(found):
    result = has_hash(obj)
    if result is not None:
        break
if result is None:
    raise SystemExit("view call did not return a SnapshotRecord:\n" + text)
record = {"method": call["method"], "args": call["args"], "result": result}
with open(sys.argv[3], "a") as handle:
    handle.write(json.dumps(record) + "\n")
PY
done < "$WORKDIR/calls.txt"

python3 - "$ROOT/fixtures/near-views.json" "$WORKDIR/view-results.jsonl" <<'PY'
import json, sys
from pathlib import Path
views = [json.loads(line) for line in Path(sys.argv[2]).read_text().splitlines() if line.strip()]
doc = {
    "network": "sandbox",
    "live": False,
    "source": "sandbox-run",
    "note": "Saved output of a local NEAR sandbox run. Not a live chain. demo/run.sh is the check.",
    "views": views,
}
Path(sys.argv[1]).write_text(json.dumps(doc, indent=2) + "\n")
print(f"wrote {sys.argv[1]} ({len(views)} views)")
PY

if kill -0 "$SANDBOX_PID" 2>/dev/null; then
  kill -- "-$SANDBOX_PID" 2>/dev/null || kill "$SANDBOX_PID" 2>/dev/null || true
  wait "$SANDBOX_PID" 2>/dev/null || true
fi
SANDBOX_PID=""

echo "risk scores"
while IFS= read -r rel; do
  skills/por-risk-control/scripts/por-check.sh "$ROOT/$rel"
done < <(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("\n".join(r["path"] for r in d["assessments"]))' "$ROOT/fixtures/digests.json")

PORT=8765
while [[ "$PORT" -lt 8780 ]] && curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; do
  PORT=$((PORT + 1))
done
echo "dashboard http://127.0.0.1:${PORT}/dashboard/"
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT"
