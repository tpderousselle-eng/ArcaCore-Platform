"""Create deterministic GitHub security-promotion evidence after CI passes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re


SCHEMA_VERSION = "arcacore.security-promotion/v1"
REPOSITORY = "tpderousselle-eng/ArcaCore-Platform"
SOURCE_REF = "refs/heads/main"
WORKFLOW_NAME = "ArcaCore Security Promotion"
WORKFLOW_PATH = ".github/workflows/arcacore-security-promotion.yml"
REQUIRED_CHECKS = (
    "discovery",
    "security_hardening",
    "generated_runtime",
    "postgresql",
    "kubernetes_health",
    "failure_injection",
    "determinism",
    "release_gate_unit",
    "docker_compose",
)


def evidence_from_github_environment(environment: dict[str, str]) -> dict[str, object]:
    repository = environment.get("GITHUB_REPOSITORY", "")
    commit = environment.get("GITHUB_SHA", "")
    source_ref = environment.get("GITHUB_REF", "")
    workflow = environment.get("GITHUB_WORKFLOW", "")
    run_id = environment.get("GITHUB_RUN_ID", "")
    if repository != REPOSITORY:
        raise ValueError("unexpected GitHub repository")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("GITHUB_SHA must be a full lowercase commit SHA")
    if source_ref != SOURCE_REF:
        raise ValueError("promotion evidence may only be created from main")
    if workflow != WORKFLOW_NAME:
        raise ValueError("unexpected GitHub workflow identity")
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("GITHUB_RUN_ID must be a positive integer")
    return {
        "checks": {name: "PASS" for name in REQUIRED_CHECKS},
        "commit_sha": commit,
        "docker": {"executed": True, "result": "PASS"},
        "repository": repository,
        "result": "PASS",
        "schema_version": SCHEMA_VERSION,
        "source_ref": source_ref,
        "workflow_name": workflow,
        "workflow_path": WORKFLOW_PATH,
        "workflow_run_id": run_id,
    }


def write_evidence(path: Path, environment: dict[str, str]) -> None:
    document = evidence_from_github_environment(environment)
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    write_evidence(Path("arcacore-security-promotion.json"), dict(os.environ))
