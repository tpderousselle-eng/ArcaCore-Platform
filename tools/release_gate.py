"""Authoritative Stabilization 25 release-candidate gate.

The gate intentionally executes test contracts in child processes.  This keeps
the normal unittest discovery suite non-recursive while preserving each
contract's real setup, teardown, environment, and exit status.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCKER_RUNTIME_ENV = "ARCACORE_RUN_DOCKER_TESTS"
TEST_COUNT_PATTERN = re.compile(r"Ran (\d+) tests? in ")
SKIP_PATTERN = re.compile(r"skipped ['\"]([^'\"]+)['\"]")
APPROVED_DISCOVERY_SKIP = (
    f"Set {DOCKER_RUNTIME_ENV}=1 to run the real Docker Compose contract."
)
BLOCKING_SECURITY_SEVERITIES = frozenset({"critical", "high", "medium"})
ALLOWED_SECURITY_SEVERITIES = BLOCKING_SECURITY_SEVERITIES | {"low"}


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str
    tests: int = 0
    skips: tuple[str, ...] = ()
    blocked: bool = False


@dataclass(frozen=True)
class Contract:
    name: str
    arguments: tuple[str, ...]
    environment: Mapping[str, str | None]
    approved_skips: frozenset[str] = frozenset()


CONTRACTS = (
    Contract(
        "Core discovery",
        ("-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py", "-v"),
        {DOCKER_RUNTIME_ENV: None},
        frozenset({APPROVED_DISCOVERY_SKIP}),
    ),
    Contract("Golden application matrix", ("-m", "unittest", "tools.test_golden_matrix", "-v"), {}),
    Contract("Generated FastAPI runtime", ("-m", "unittest", "tools.test_generated_runtime", "-v"), {}),
    Contract("PostgreSQL integration", ("-m", "unittest", "tools.test_postgresql_runtime", "-v"), {}),
    Contract(
        "Docker & Compose production runtime",
        ("-m", "unittest", "tools.test_docker_compose_runtime", "-v"),
        {DOCKER_RUNTIME_ENV: "1"},
    ),
    Contract(
        "Kubernetes & health validation",
        (
            "-m", "unittest",
            "tools.test_kubernetes", "tools.test_kubernetes_validation", "tools.test_health_checks",
            "-v",
        ),
        {},
    ),
    Contract("Failure injection / atomicity", ("-m", "unittest", "tools.test_failure_injection", "-v"), {}),
    Contract("Security hardening", ("-m", "unittest", "tools.test_security_hardening", "-v"), {}),
    Contract("Determinism / reproducibility", ("-m", "unittest", "tools.test_determinism", "-v"), {}),
)


def _environment(overrides: Mapping[str, str | None]) -> dict[str, str]:
    environment = os.environ.copy()
    for key, value in overrides.items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    return environment


def _failure_detail(output: str, returncode: int) -> str:
    meaningful = [line.strip() for line in output.splitlines() if line.strip()]
    for marker in ("FAILED (", "FAILED", "Traceback (most recent call last):"):
        if marker in meaningful:
            return marker
    return meaningful[-1][:240] if meaningful else f"test process exited {returncode}"


def run_contract(
    contract: Contract,
    *,
    python: str = sys.executable,
    runner=subprocess.run,
) -> GateResult:
    completed = runner(
        (python, *contract.arguments),
        cwd=REPOSITORY_ROOT,
        env=_environment(contract.environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    match = TEST_COUNT_PATTERN.search(output)
    tests = int(match.group(1)) if match else 0
    skips = tuple(SKIP_PATTERN.findall(output))
    unexpected = sorted(set(skips) - contract.approved_skips)
    missing_count = completed.returncode == 0 and not match
    if completed.returncode != 0:
        return GateResult(contract.name, False, _failure_detail(output, completed.returncode), tests, skips)
    if missing_count:
        return GateResult(contract.name, False, "test count was not reported", tests, skips)
    if unexpected:
        return GateResult(contract.name, False, f"unexpected skipped check: {unexpected[0]}", tests, skips)
    detail = f"{tests} tests"
    if skips:
        detail += f", {len(skips)} approved environment-dependent skip"
    return GateResult(contract.name, True, detail, tests, skips)


def current_commit(*, runner=subprocess.run) -> str:
    completed = runner(
        ("git", "-c", "safe.directory=C:/Projects/ArcaCore", "rev-parse", "HEAD"),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError("current Git commit could not be determined")
    commit = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Git returned an invalid commit SHA")
    return commit


def _digest_field(digest, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def working_tree_digest(*, runner=subprocess.run) -> str:
    """Match the Codex Security git-worktree snapshot contract."""

    digest = hashlib.sha256()
    _digest_field(digest, b"format", b"codex-security-snapshot/v1")
    diff = runner(
        (
            "git", "-c", "safe.directory=C:/Projects/ArcaCore", "diff", "--binary",
            "--full-index", "--no-ext-diff", "--no-textconv", "--ignore-submodules=none",
            "HEAD", "--", ".",
        ),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise RuntimeError("working-tree diff could not be read")
    _digest_field(digest, b"tracked-diff", diff.stdout)
    untracked = runner(
        (
            "git", "-c", "safe.directory=C:/Projects/ArcaCore", "ls-files", "--others",
            "--exclude-standard", "-z", "--", ".",
        ),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )
    if untracked.returncode != 0:
        raise RuntimeError("untracked files could not be read")
    for raw_path in sorted(path for path in untracked.stdout.split(b"\0") if path):
        relative = os.fsdecode(raw_path)
        path = REPOSITORY_ROOT / relative
        metadata = path.lstat()
        _digest_field(digest, b"untracked-path", raw_path)
        _digest_field(digest, b"untracked-mode", str(stat.S_IMODE(metadata.st_mode)).encode())
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"unsupported untracked path in release snapshot: {relative}")
        content = path.read_bytes()
        _digest_field(digest, b"untracked-kind", b"file")
        _digest_field(digest, b"untracked-size", str(len(content)).encode())
        _digest_field(digest, b"untracked-content-sha256", hashlib.sha256(content).digest())
    return f"codex-security-snapshot/v1:sha256:{digest.hexdigest()}"


def _json_file(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return document


def validate_security_review(path: Path, commit: str, *, runner=subprocess.run) -> GateResult:
    """Inspect local Codex Security artifacts without treating them as trusted.

    The artifact seal is a consistency checksum, not an issuer signature.  This
    process has no pinned public key, workload identity, or transparency-log
    receipt with which to authenticate a Codex Security result.  Consequently a
    locally supplied artifact can inform a failure but can never authorize
    promotion.
    """

    try:
        root = path.resolve(strict=True)
        if root == REPOSITORY_ROOT or REPOSITORY_ROOT in root.parents:
            raise ValueError("security artifacts must remain outside the repository")
        manifest = _json_file(root / "scan-manifest.json")
        findings_document = _json_file(root / "findings.json")
        coverage = _json_file(root / "coverage.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return GateResult("Independent security review", False, f"review unavailable: {error}")
    scan = manifest.get("scan")
    if manifest.get("documentType") != "codex-security.scan-manifest" or not isinstance(scan, dict):
        return GateResult("Independent security review", False, "unrecognized Codex Security manifest")
    producer = scan.get("producer")
    target = scan.get("target")
    if not isinstance(producer, dict) or producer.get("name") != "codex-security-plugin":
        return GateResult("Independent security review", False, "review producer is not Codex Security")
    if scan.get("status") != "completed" or not scan.get("sealedAt"):
        return GateResult("Independent security review", False, "review is not completed and sealed")
    if not isinstance(target, dict):
        return GateResult("Independent security review", False, "security review target is malformed")
    target_kind = target.get("kind")
    reviewed_commit = (
        target.get("headRevision") if target_kind == "git_diff" else target.get("revision")
    )
    if reviewed_commit != commit:
        return GateResult("Independent security review", False, "review commit does not match Git HEAD")
    try:
        digest = working_tree_digest(runner=runner)
    except (OSError, RuntimeError) as error:
        return GateResult("Independent security review", False, f"working-tree snapshot failed: {error}")
    if target_kind not in {"git_diff", "git_worktree"} or target.get("snapshotDigest") != digest:
        return GateResult("Independent security review", False, "review snapshot does not match the working tree")
    scan_id = scan.get("id")
    if coverage.get("scanId") != scan_id or findings_document.get("scanId") != scan_id:
        return GateResult("Independent security review", False, "security artifact scan IDs disagree")
    if coverage.get("completeness") != "complete" or coverage.get("deferred") != []:
        return GateResult("Independent security review", False, "security review coverage is incomplete")
    artifacts = scan.get("artifacts")
    if not isinstance(artifacts, list):
        return GateResult("Independent security review", False, "security artifact seal is malformed")
    expected_hashes = {
        item.get("path"): item.get("sha256")
        for item in artifacts
        if isinstance(item, dict) and item.get("path") in {"findings.json", "coverage.json"}
    }
    for name in ("findings.json", "coverage.json"):
        if expected_hashes.get(name) != hashlib.sha256((root / name).read_bytes()).hexdigest():
            return GateResult("Independent security review", False, f"{name} does not match the sealed digest")
    findings = findings_document.get("findings")
    if not isinstance(findings, list):
        return GateResult("Independent security review", False, "review findings are malformed")
    if any(not isinstance(item, dict) for item in findings):
        return GateResult("Independent security review", False, "every security finding must be an object")
    severities = []
    for item in findings:
        severity = item.get("severity")
        if not isinstance(severity, dict):
            return GateResult("Independent security review", False, "security finding severity is malformed")
        severities.append(str(severity.get("level", "")).lower())
    if any(severity not in ALLOWED_SECURITY_SEVERITIES for severity in severities):
        return GateResult("Independent security review", False, "security finding has an unknown severity")
    blocking = [severity for severity in severities if severity in BLOCKING_SECURITY_SEVERITIES]
    if blocking:
        counts = {severity: blocking.count(severity) for severity in sorted(set(blocking))}
        return GateResult("Independent security review", False, f"blocking findings: {counts}")
    return GateResult(
        "Independent security review",
        False,
        (
            "local artifacts are not trusted promotion evidence; require an "
            "externally verified signed attestation or protected CI/security-service status"
        ),
        blocked=True,
    )


def fixture_hashes() -> dict[str, str]:
    targets = (REPOSITORY_ROOT / "tools" / "golden_matrix.py", REPOSITORY_ROOT / "tools" / "registry" / "models.json")
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in targets
    }


def execute(security_review: Path, *, runner=subprocess.run) -> tuple[list[GateResult], dict[str, object]]:
    commit = current_commit(runner=runner)
    results: list[GateResult] = []
    for contract in CONTRACTS:
        result = run_contract(contract, runner=runner)
        results.append(result)
        if not result.passed:
            break
    if all(result.passed for result in results):
        results.append(validate_security_review(security_review, commit, runner=runner))
    metadata = {
        "commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tests": sum(result.tests for result in results),
        "docker_executed": any(result.name.startswith("Docker") and result.passed for result in results),
        "postgresql_executed": any(result.name == "PostgreSQL integration" and result.passed for result in results),
        "fixture_sha256": fixture_hashes(),
    }
    return results, metadata


def render(results: Sequence[GateResult], metadata: Mapping[str, object]) -> str:
    lines = ["ArcaCore Release Candidate Gate", ""]
    for result in results:
        status = "PASS" if result.passed else "BLOCKED" if result.blocked else "FAIL"
        lines.append(f"[{status}] {result.name}: {result.detail}")
    functional_passed = (
        len(results) >= len(CONTRACTS)
        and all(result.passed for result in results[:len(CONTRACTS)])
    )
    security_result = results[len(CONTRACTS)] if len(results) > len(CONTRACTS) else None
    security_status = (
        "PASS" if security_result is not None and security_result.passed
        else "BLOCKED" if security_result is None or security_result.blocked
        else "FAIL"
    )
    passed = functional_passed and security_status == "PASS"
    lines.extend(("", "Release metadata"))
    lines.append(f"Git commit: {metadata['commit']}")
    lines.append(f"Python: {metadata['python']}")
    lines.append(f"Platform: {metadata['platform']}")
    lines.append(f"Executed test count (including dedicated reruns): {metadata['tests']}")
    lines.append(f"Docker executed: {'yes' if metadata['docker_executed'] else 'no'}")
    lines.append(f"PostgreSQL executed: {'yes' if metadata['postgresql_executed'] else 'no'}")
    for name, digest in metadata["fixture_sha256"].items():
        lines.append(f"SHA-256 {name}: {digest}")
    lines.extend(
        (
            "",
            f"ARCCORE FUNCTIONAL RELEASE GATE: {'PASS' if functional_passed else 'FAIL'}",
            f"ARCCORE SECURITY PROMOTION GATE: {security_status}",
            f"ARCCORE RELEASE GATE: {'PASS' if passed else 'FAIL'}",
        )
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--security-review",
        type=Path,
        required=True,
        help="Completed Codex Security artifact directory for the current working tree",
    )
    arguments = parser.parse_args(argv)
    try:
        results, metadata = execute(arguments.security_review)
    except Exception as error:
        print("ArcaCore Release Candidate Gate\n")
        print(f"[FAIL] Gate infrastructure: {error}")
        print("\nARCCORE RELEASE GATE: FAIL")
        return 1
    print(render(results, metadata))
    return 0 if len(results) == len(CONTRACTS) + 1 and all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
