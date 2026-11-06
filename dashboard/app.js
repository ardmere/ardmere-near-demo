// Point values match skills/por-risk-control/references/decision-table.md.
const BLOCKING = {
  UNVERIFIABLE: 40,
  LOGIN_WALL: 40,
  SAMPLE_ONLY: 40,
  BLACK_BOX_INCLUSION_PROOF: 40,
};
const NONBLOCKING = {
  STAGE_BLOCKED: 8,
  NO_WALLET_OWNERSHIP_PROOF: 8,
  OPAQUE_TRUSTED_SETUP: 8,
  BUSINESS_CONSTRAINT_GAP: 8,
  NEGATIVE_NET_WORTH_DUMMY_USER_RISK: 8,
  IMPLEMENTATION_SEMANTICS_RISK: 8,
  HIGH_FRICTION_INCLUSION_PROOF: 5,
  NO_INDEPENDENT_REVIEW: 5,
  NO_CANONICAL_ANCHOR: 5,
  CONFLICT_OF_INTEREST_UNDISCLOSED: 5,
  HIGH_FREQUENCY_GAP: 5,
};
const SEVERITY_FALLBACK = { critical: 10, high: 8, medium: 5, low: 2, info: 1 };
const NONBLOCKING_CAP = 20;
const RANK = { low: 0, medium: 1, high: 2, critical: 3 };

function band(score) {
  if (score >= 80) return "critical";
  if (score >= 50) return "high";
  if (score >= 25) return "medium";
  return "low";
}

function atLeast(level, floor) {
  return RANK[level] >= RANK[floor] ? level : floor;
}

function normalizeHex(value) {
  if (typeof value !== "string") return null;
  const text = value.trim().toLowerCase().replace(/^0x/, "");
  return /^[0-9a-f]{64}$/.test(text) ? text : null;
}

function stageBelow(stage) {
  if (typeof stage !== "string") return false;
  const text = stage.trim();
  const lowered = text.toLowerCase();
  if (
    lowered === "pre-stage" ||
    lowered.startsWith("pre-stage ") ||
    lowered.startsWith("pre-stage-") ||
    lowered.startsWith("pre-stage—")
  ) {
    return true;
  }
  return text === "Stage 0" || text.startsWith("Stage 0 ") || text.startsWith("Stage 0-") || text.startsWith("Stage 0—");
}

function capSum(factors, limit) {
  let total = factors.reduce((sum, item) => sum + item.delta, 0);
  if (total <= limit) return;
  let overflow = total - limit;
  for (let i = factors.length - 1; i >= 0 && overflow > 0; i -= 1) {
    const cut = Math.min(factors[i].delta, overflow);
    if (cut) {
      factors[i].delta -= cut;
      overflow -= cut;
      factors[i].note = `${factors[i].note} Score capped at 100.`.trim();
    }
  }
}

function scoreAssessment(assessment, fileSha, digestsSha, nearSha, nearPresent) {
  const flags = Array.isArray(assessment.riskFlags) ? assessment.riskFlags : [];
  const stage = assessment.porStage;
  if (fileSha !== digestsSha) {
    return finishIntegrity("DIGEST_MISMATCH", "File sha256 does not match fixtures/digests.json.", flags);
  }
  if (nearPresent && nearSha !== fileSha) {
    return finishIntegrity("NEAR_GET_MISMATCH", "NEAR get assessment_sha256 does not match the file sha256.", flags);
  }
  const factors = [];
  let sawBlocking = false;
  for (const flag of flags) {
    if (!flag || !(flag.id in BLOCKING)) continue;
    sawBlocking = true;
    factors.push({ id: flag.id, delta: BLOCKING[flag.id], note: flag.message || "Blocking high flag." });
  }
  if (stageBelow(stage)) {
    factors.push({
      id: "STAGE_BELOW_EFFECTIVE_POR",
      delta: 35,
      note: `porStage is ${stage}, below effective PoR.`,
    });
  }
  let nonblockingAdded = 0;
  for (const flag of flags) {
    if (!flag || typeof flag.id !== "string" || flag.id in BLOCKING) continue;
    const full = flag.id in NONBLOCKING
      ? NONBLOCKING[flag.id]
      : (SEVERITY_FALLBACK[String(flag.severity || "").toLowerCase()] ?? 5);
    const room = NONBLOCKING_CAP - nonblockingAdded;
    const applied = Math.min(full, Math.max(room, 0));
    let note = flag.message || "Non-blocking flag.";
    if (applied < full) note = `${note} Non-blocking contribution capped at 20.`;
    factors.push({ id: flag.id, delta: applied, note });
    nonblockingAdded += applied;
  }
  capSum(factors, 100);
  const riskScore = factors.reduce((sum, item) => sum + item.delta, 0);
  let riskLevel = band(riskScore);
  if (sawBlocking) riskLevel = atLeast(riskLevel, "high");
  if (stageBelow(stage)) riskLevel = atLeast(riskLevel, "medium");
  return { riskScore, riskLevel, factors, failed: false };

  function finishIntegrity(id, note, flagRows) {
    return {
      riskScore: 100,
      riskLevel: "critical",
      factors: [{ id, delta: 100, note }],
      failed: true,
      riskFlags: flagRows.filter((flag) => flag && flag.id).map((flag) => flag.id),
    };
  }
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function findView(near, method, exchange, snapshotId) {
  return (near.views || []).find((view) => {
    if (!view || view.method !== method) return false;
    const args = view.args || {};
    if (method === "get_latest") return args.exchange === exchange;
    return args.exchange === exchange && String(args.snapshot_id) === String(snapshotId);
  });
}

function cell(text, className) {
  const el = document.createElement("td");
  if (className) el.className = className;
  el.textContent = text;
  return el;
}

function render(rows) {
  const verdict = document.getElementById("verdict");
  const body = document.getElementById("rows");
  verdict.replaceChildren();
  body.replaceChildren();
  for (const row of rows) {
    const card = document.createElement("article");
    card.className = `card ${row.score.riskLevel}${row.score.failed ? " failure" : ""}`;
    card.innerHTML = `
      <p class="exchange"></p>
      <p class="score"></p>
      <p class="meta"></p>
    `;
    card.querySelector(".exchange").textContent = `${row.exchange} ${row.snapshotId}`;
    card.querySelector(".score").textContent = `${row.score.riskScore} ${row.score.riskLevel}`;
    card.querySelector(".meta").textContent = row.score.failed
      ? "Hash mismatch"
      : `${row.stage} · effective PoR ${row.effectivePoR ? "yes" : "no"}`;
    verdict.appendChild(card);

    const tr = document.createElement("tr");
    if (row.score.failed) tr.className = "is-failure";
    const exchange = document.createElement("td");
    const link = document.createElement("a");
    link.href = row.reportUrl;
    link.textContent = row.exchange;
    link.rel = "noopener";
    link.target = "_blank";
    exchange.appendChild(link);
    tr.append(exchange);
    tr.append(cell(row.snapshotId));
    tr.append(cell(row.stage || "—"));
    tr.append(cell(row.effectivePoR ? "yes" : "no"));
    tr.append(cell(String(row.score.riskScore)));
    const level = cell(row.score.riskLevel, `level ${row.score.riskLevel}`);
    tr.append(level);
    tr.append(cell(row.fileSha, "hash"));
    const nearText = row.nearPresent
      ? (row.hashesMatch ? `match ${row.nearSha}` : `mismatch ${row.nearSha || "missing hash"}`)
      : "no get view";
    const nearCell = cell(nearText, row.hashesMatch || !row.nearPresent ? "near-cell" : "near-cell mismatch");
    tr.append(nearCell);
    body.append(tr);

    const detail = document.createElement("tr");
    detail.className = "detail";
    detail.hidden = true;
    const detailCell = document.createElement("td");
    detailCell.colSpan = 8;
    const buttonRow = document.createElement("p");
    const button = document.createElement("button");
    button.className = "expand";
    button.type = "button";
    button.textContent = "Show view call";
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => {
      const open = detail.hidden;
      detail.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
      button.textContent = open ? "Hide view call" : "Show view call";
    });
    buttonRow.append(button);
    nearCell.append(document.createElement("br"), button);

    const factors = document.createElement("ul");
    factors.className = "factors";
    for (const factor of row.score.factors) {
      const item = document.createElement("li");
      item.textContent = `${factor.id} +${factor.delta} — ${factor.note}`;
      factors.append(item);
    }
    const getPre = document.createElement("pre");
    getPre.textContent = JSON.stringify({ method: "get", args: row.getView && row.getView.args, result: row.getView && row.getView.result }, null, 2);
    const latestPre = document.createElement("pre");
    latestPre.textContent = JSON.stringify({ method: "get_latest", args: row.latestView && row.latestView.args, result: row.latestView && row.latestView.result }, null, 2);
    const heading = document.createElement("h3");
    heading.textContent = "Factors";
    const getHeading = document.createElement("h3");
    getHeading.textContent = "get";
    const latestHeading = document.createElement("h3");
    latestHeading.textContent = "get_latest";
    detailCell.append(heading, factors, getHeading, getPre, latestHeading, latestPre);
    detail.append(detailCell);
    body.append(detail);
  }
}

function fail(message) {
  const verdict = document.getElementById("verdict");
  verdict.replaceChildren();
  const box = document.createElement("p");
  box.className = "error";
  box.textContent = message;
  verdict.append(box);
}

async function main() {
  const digestsRes = await fetch("../fixtures/digests.json");
  const nearRes = await fetch("../fixtures/near-views.json");
  if (!digestsRes.ok || !nearRes.ok) {
    fail("Could not read fixtures/digests.json and fixtures/near-views.json. Serve the repo root with demo/run.sh.");
    return;
  }
  const digests = await digestsRes.json();
  const near = await nearRes.json();
  document.getElementById("recording-note").textContent = near.note || "Sandbox recording, not a live chain.";
  const rows = [];
  for (const entry of digests.assessments || []) {
    const fileRes = await fetch(`../${entry.path}`);
    if (!fileRes.ok) {
      fail(`Missing ${entry.path}`);
      return;
    }
    const bytes = await fileRes.arrayBuffer();
    const fileSha = await sha256Hex(bytes);
    const assessment = JSON.parse(new TextDecoder().decode(bytes));
    const getView = findView(near, "get", entry.exchange, entry.snapshotId);
    const latestView = findView(near, "get_latest", entry.exchange, entry.snapshotId);
    const nearSha = normalizeHex(getView && getView.result && getView.result.assessment_sha256);
    const digestsSha = normalizeHex(entry.sha256);
    const nearPresent = Boolean(getView);
    const score = scoreAssessment(assessment, fileSha, digestsSha, nearSha, nearPresent);
    rows.push({
      exchange: entry.exchange,
      snapshotId: String(entry.snapshotId),
      stage: assessment.porStage,
      effectivePoR: assessment.effectivePoR === true,
      reportUrl: entry.reportUrl,
      fileSha,
      nearSha,
      nearPresent,
      hashesMatch: nearPresent && nearSha === fileSha && fileSha === digestsSha,
      score,
      getView,
      latestView,
    });
  }
  render(rows);
}

main().catch((error) => fail(error.message || "Failed to load the dashboard."));
