# How to present PoR results (agents)

**Do not** answer in long paragraphs. Use the structure below. One line = one fact.

## Single snapshot (`por-check.sh`)

```markdown
## {exchange} · {snapshotId}

| Item | Value |
| --- | --- |
| Transparency risk | **{riskScore}/100** ({riskLevel}) — higher = worse disclosure |
| Scoring source | {scoringSource} |
| PoR stage | {porStage} |
| Effective PoR | {effectivePoR} |
| NEAR digest match | {near.matches} |
| Schema (chain) | {near.schemaVersion} |

### Self-reported reserves (`selfReportedReserves`)

Always include when answering PoR **assessment** questions (label: exchange self-report, **not** verified solvency).

| Metric | Value (example) |
| --- | --- |
| Total liability (USD) | `$9.32B` or **Unavailable** |
| Total reserve (USD) | `$32.62B` or **Unavailable** |
| Total reserve ratio | `105.33%` or **Unavailable** |
| BTC / ETH / USDT / USDC ratios | `108.39%` or **Unavailable** each |

**Missing values:** when a field is `null`, `available: false`, or absent, show **`Unavailable`** in user-facing tables (not `—`, not blank). JSON from `por-check` keeps machine `null` / booleans unchanged.

Use a small **two-table** block (totals + coin ratios). Do not bury these numbers in prose.

### Top factors

| Factor | Δ |
| --- | ---: |
| {id} | {delta} |
| … | … |

### Verify yourself

| Source | Link |
| --- | --- |
| Exchange PoR page | {exchangePorPage} |
| {artifact kind} | {url} |
| ardmere assessment | {ardmereAssessment} |
| ardmere report | {ardmereTransparencyReport} |
```

Cap factors at **5 rows** in chat; say “(+N more)” if needed.

## Exchange window (`por-exchange-report.py`)

Use script output (`--format markdown`, default) or the same table pattern for **Latest** + **History** sections. Section order and batch layout: [`response-framework.md`](response-framework.md).

## Batch (many exchanges)

Use **one merged overview table** (risk + stage + `near.matches` + all self-reported reserve columns per row). Do **not** split a separate headline table and reserves table. Full template: [`response-framework.md`](response-framework.md) § Framework C.

## Forbidden in user-facing text

- Multi-sentence essays explaining methodology unless the user asked.
- Repeating the full `scoreSemantics.interpretation` block verbatim.
- Listing every flag when the table already has `riskFlags` truncated.

Always label the score **PoR transparency risk (higher = worse)**.
