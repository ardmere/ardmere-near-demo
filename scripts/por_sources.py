"""Official PoR data sources for an assessment (exchange pages, artifact URLs)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REGISTRY = Path("vendor/ardmere.github.io/config/exchanges/registry.yaml")
GITHUB_IO = "https://github.com/ardmere/ardmere.github.io"


def _registry_por_page(exchange_id: str, repo_root: Path) -> str | None:
    path = repo_root / REGISTRY
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    block = re.search(
        rf"- id: {re.escape(exchange_id)}\n(?:.*?\n)*?    porPage: (\S+)",
        text,
    )
    return block.group(1) if block else None


def _registry_repos(exchange_id: str, repo_root: Path) -> list[dict[str, str]]:
    path = repo_root / REGISTRY
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    block = re.search(
        rf"- id: {re.escape(exchange_id)}\n(?:.*?\n)*?(?=\n  - id: |\Z)",
        text,
        re.DOTALL,
    )
    if not block:
        return []
    repos = []
    for match in re.finditer(
        r"- url: (\S+)\n        role: (\S+)",
        block.group(0),
    ):
        repos.append({"url": match.group(1), "role": match.group(2)})
    return repos


def official_sources(
    assessment: dict[str, Any],
    assessment_path: Path | None,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    exchange = str(assessment.get("exchange") or "").strip().lower()
    snapshot = assessment.get("snapshot") or {}
    snapshot_id = snapshot.get("id") if isinstance(snapshot, dict) else None

    artifacts = assessment.get("artifacts") or {}
    present = artifacts.get("present") if isinstance(artifacts, dict) else []
    artifact_urls: list[dict[str, str]] = []
    if isinstance(present, list):
        for row in present:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            artifact_urls.append(
                {
                    "kind": str(row.get("kind") or "artifact"),
                    "availability": str(row.get("availability") or "unknown"),
                    "url": url.strip(),
                }
            )

    out: dict[str, Any] = {
        "exchange": exchange,
        "snapshotId": str(snapshot_id) if snapshot_id is not None else None,
        "exchangePorPage": _registry_por_page(exchange, repo_root),
        "upstreamVerifierRepos": _registry_repos(exchange, repo_root),
        "publicArtifacts": artifact_urls,
    }

    if assessment_path is not None:
        try:
            rel = assessment_path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = assessment_path.as_posix()
        if rel.startswith("vendor/ardmere.github.io/"):
            upstream_rel = rel.split("vendor/ardmere.github.io/", 1)[-1]
            out["ardmereAssessment"] = f"{GITHUB_IO}/blob/main/{upstream_rel}"
            if rel.endswith("-assessment.json"):
                report_rel = rel.replace("-assessment.json", "-transparency-report.md")
                out["ardmereTransparencyReport"] = (
                    f"{GITHUB_IO}/blob/main/{report_rel.split('vendor/ardmere.github.io/', 1)[-1]}"
                )
            out["localAssessmentPath"] = rel
    return out
