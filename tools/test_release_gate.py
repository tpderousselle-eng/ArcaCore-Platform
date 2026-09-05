"""Tests for the non-recursive Stabilization 25.9 release gate."""

from contextlib import redirect_stdout
from io import StringIO
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import release_gate


COMMIT = "5" * 40


def completed(returncode=0, output="Ran 7 tests in 1.000s\n\nOK\n"):
    return SimpleNamespace(returncode=returncode, stdout="", stderr=output)


class ReleaseCandidateGateTest(unittest.TestCase):
    def test_contract_inventory_covers_every_mandatory_executable_subsystem(self):
        self.assertEqual(
            [contract.name for contract in release_gate.CONTRACTS],
            [
                "Core discovery",
                "Golden application matrix",
                "Generated FastAPI runtime",
                "PostgreSQL integration",
                "Docker & Compose production runtime",
                "Kubernetes & health validation",
                "Failure injection / atomicity",
                "Security hardening",
                "Determinism / reproducibility",
            ],
        )

    def test_discovery_is_non_recursive_and_disables_docker_opt_in(self):
        discovery = release_gate.CONTRACTS[0]
        self.assertEqual(discovery.arguments[:3], ("-m", "unittest", "discover"))
        self.assertEqual(discovery.environment[release_gate.DOCKER_RUNTIME_ENV], None)
        self.assertNotIn("release_gate", " ".join(discovery.arguments))

    def test_real_docker_contract_is_required_and_enabled(self):
        docker = next(contract for contract in release_gate.CONTRACTS if contract.name.startswith("Docker"))
        self.assertEqual(docker.environment[release_gate.DOCKER_RUNTIME_ENV], "1")
        self.assertEqual(docker.approved_skips, frozenset())

    def test_contract_passes_with_reported_count(self):
        result = release_gate.run_contract(release_gate.CONTRACTS[1], runner=lambda *args, **kwargs: completed())
        self.assertTrue(result.passed)
        self.assertEqual(result.tests, 7)

    def test_contract_failure_is_not_hidden(self):
        result = release_gate.run_contract(
            release_gate.CONTRACTS[1],
            runner=lambda *args, **kwargs: completed(1, "Ran 7 tests in 1.0s\nFAILED (failures=1)\n"),
        )
        self.assertFalse(result.passed)
        self.assertIn("FAILED", result.detail)

    def test_success_without_test_count_fails_closed(self):
        result = release_gate.run_contract(
            release_gate.CONTRACTS[1], runner=lambda *args, **kwargs: completed(0, "OK\n")
        )
        self.assertFalse(result.passed)
        self.assertIn("count", result.detail)

    def test_unexpected_skip_fails_closed(self):
        result = release_gate.run_contract(
            release_gate.CONTRACTS[1],
            runner=lambda *args, **kwargs: completed(0, "x ... skipped 'dependency missing'\nRan 1 test in 0.1s\nOK (skipped=1)\n"),
        )
        self.assertFalse(result.passed)
        self.assertIn("unexpected skipped", result.detail)

    def test_discovery_accepts_only_documented_docker_skip(self):
        output = (
            f"x ... skipped '{release_gate.APPROVED_DISCOVERY_SKIP}'\n"
            "Ran 381 tests in 1.0s\nOK (skipped=1)\n"
        )
        result = release_gate.run_contract(
            release_gate.CONTRACTS[0], runner=lambda *args, **kwargs: completed(0, output)
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.skips, (release_gate.APPROVED_DISCOVERY_SKIP,))

    def _review(self, directory: str, *, findings=None, complete=True, commit=COMMIT) -> Path:
        root = Path(directory) / "codex-security"
        root.mkdir()
        findings_document = {"scanId": "scan-1", "findings": findings or []}
        coverage = {"scanId": "scan-1", "completeness": "complete" if complete else "partial", "deferred": []}
        findings_bytes = json.dumps(findings_document).encode()
        coverage_bytes = json.dumps(coverage).encode()
        (root / "findings.json").write_bytes(findings_bytes)
        (root / "coverage.json").write_bytes(coverage_bytes)
        manifest = {
            "documentType": "codex-security.scan-manifest",
            "scan": {
                "id": "scan-1",
                "producer": {"name": "codex-security-plugin", "version": "test"},
                "status": "completed",
                "sealedAt": "2026-09-05T00:00:00Z",
                "target": {
                    "kind": "git_diff",
                    "baseRevision": COMMIT,
                    "headRevision": commit,
                    "snapshotDigest": release_gate.working_tree_digest(runner=self._snapshot_runner),
                },
                "artifacts": [
                    {"path": "findings.json", "sha256": hashlib.sha256(findings_bytes).hexdigest()},
                    {"path": "coverage.json", "sha256": hashlib.sha256(coverage_bytes).hexdigest()},
                ],
            },
        }
        (root / "scan-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    @staticmethod
    def _snapshot_runner(command, **kwargs):
        if "diff" in command:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if "ls-files" in command:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(command)

    def test_security_review_must_be_complete_and_match_head(self):
        with TemporaryDirectory() as directory:
            incomplete = self._review(directory, complete=False)
            self.assertFalse(release_gate.validate_security_review(incomplete, COMMIT, runner=self._snapshot_runner).passed)
        with TemporaryDirectory() as directory:
            wrong = self._review(directory, commit="a" * 40)
            self.assertFalse(release_gate.validate_security_review(wrong, COMMIT, runner=self._snapshot_runner).passed)

    def test_blocking_security_finding_fails_gate(self):
        with TemporaryDirectory() as directory:
            review = self._review(directory, findings=[{"severity": {"level": "medium"}}])
            result = release_gate.validate_security_review(review, COMMIT, runner=self._snapshot_runner)
        self.assertFalse(result.passed)
        self.assertIn("medium", result.detail)

    def test_clean_local_security_review_is_blocked_without_trusted_issuer(self):
        with TemporaryDirectory() as directory:
            review = self._review(directory, findings=[{"severity": {"level": "low"}}])
            result = release_gate.validate_security_review(review, COMMIT, runner=self._snapshot_runner)
        self.assertFalse(result.passed)
        self.assertTrue(result.blocked)
        self.assertIn("not trusted promotion evidence", result.detail)

    def test_forged_clean_security_artifact_cannot_produce_a_pass(self):
        with TemporaryDirectory() as directory:
            forged = self._review(directory)
            result = release_gate.validate_security_review(forged, COMMIT, runner=self._snapshot_runner)
        self.assertFalse(result.passed)
        self.assertTrue(result.blocked)

    def test_security_review_rejects_unknown_severity_and_tampering(self):
        with TemporaryDirectory() as directory:
            review = self._review(directory, findings=[{"severity": {"level": "unknown"}}])
            self.assertFalse(release_gate.validate_security_review(review, COMMIT, runner=self._snapshot_runner).passed)
        with TemporaryDirectory() as directory:
            review = self._review(directory)
            (review / "findings.json").write_text('{"scanId":"scan-1","findings":[{"severity":{"level":"high"}}]}', encoding="utf-8")
            result = release_gate.validate_security_review(review, COMMIT, runner=self._snapshot_runner)
            self.assertFalse(result.passed)
            self.assertIn("sealed digest", result.detail)

    def test_execute_stops_at_first_failed_subsystem(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if command[0] == "git":
                return SimpleNamespace(returncode=0, stdout=f"{COMMIT}\n", stderr="")
            return completed(1, "Ran 1 test in 0.1s\nFAILED (errors=1)\n")

        with TemporaryDirectory() as directory:
            results, _metadata = release_gate.execute(Path(directory) / "missing.json", runner=runner)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)
        self.assertEqual(len(calls), 2)

    def test_cli_returns_nonzero_when_gate_fails(self):
        failed = [release_gate.GateResult("Core discovery", False, "boom")]
        metadata = {
            "commit": COMMIT,
            "python": "3.13",
            "platform": "test",
            "tests": 0,
            "docker_executed": False,
            "postgresql_executed": False,
            "fixture_sha256": {},
        }
        with patch.object(release_gate, "execute", return_value=(failed, metadata)), redirect_stdout(StringIO()) as output:
            code = release_gate.main(["--security-review", "review.json"])
        self.assertEqual(code, 1)
        self.assertIn("ARCCORE RELEASE GATE: FAIL", output.getvalue())

    def test_render_separates_functional_pass_from_blocked_security_promotion(self):
        results = [
            *(release_gate.GateResult(contract.name, True, "1 tests", tests=1) for contract in release_gate.CONTRACTS),
            release_gate.GateResult("Independent security review", False, "untrusted", blocked=True),
        ]
        metadata = {
            "commit": COMMIT,
            "python": "3.13",
            "platform": "test",
            "tests": len(release_gate.CONTRACTS),
            "docker_executed": True,
            "postgresql_executed": True,
            "fixture_sha256": {},
        }
        output = release_gate.render(results, metadata)
        self.assertIn("ARCCORE FUNCTIONAL RELEASE GATE: PASS", output)
        self.assertIn("ARCCORE SECURITY PROMOTION GATE: BLOCKED", output)
        self.assertIn("ARCCORE RELEASE GATE: FAIL", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
