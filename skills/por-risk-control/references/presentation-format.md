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

Optional when `schemaVersion` ≥ 7 and values are not `0` / `65535`: one row each for self-reported **total liability / reserve USD** and major-coin **reserve ratio bps** from `near.*` (label as exchange self-report, not verified).

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

Use script output (`--format markdown`, default) or the same table pattern for **Latest** + **History** sections.

## Forbidden in user-facing text

- Multi-sentence essays explaining methodology unless the user asked.
- Repeating the full `scoreSemantics.interpretation` block verbatim.
- Listing every flag when the table already has `riskFlags` truncated.

Always label the score **PoR transparency risk (higher = worse)**.
