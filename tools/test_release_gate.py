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
from tools import promotion_evidence


COMMIT = "5" * 40


def completed(returncode=0, output="Ran 7 tests in 1.000s\n\nOK\n"):
    return SimpleNamespace(returncode=returncode, stdout="", stderr=output)


class ReleaseCandidateGateTest(unittest.TestCase):
    def _promotion(self, directory: str, **overrides) -> Path:
        document = {
            "schema_version": promotion_evidence.SCHEMA_VERSION,
            "repository": promotion_evidence.REPOSITORY,
            "commit_sha": COMMIT,
            "source_ref": promotion_evidence.SOURCE_REF,
            "workflow_name": promotion_evidence.WORKFLOW_NAME,
            "workflow_path": promotion_evidence.WORKFLOW_PATH,
            "workflow_run_id": "12345",
            "result": "PASS",
            "checks": {name: "PASS" for name in promotion_evidence.REQUIRED_CHECKS},
            "docker": {"executed": True, "result": "PASS"},
        }
        document.update(overrides)
        path = Path(directory) / "arcacore-security-promotion.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    @staticmethod
    def _verified_gh(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"verificationResult": {"verified": True}}]),
            stderr="",
        )

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
                "Hostile specification audit",
                "Determinism / reproducibility",
                "Autonomous generation lifecycle",
                "Autonomous runtime recovery",
                "Background and scheduled jobs",
                "Events and webhooks",
                "File and object storage",
                "Production intelligence",
            ],
        )

    def test_autonomous_lifecycle_contract_is_complete_and_non_recursive(self):
        contract = next(
            item for item in release_gate.CONTRACTS
            if item.name == "Autonomous generation lifecycle"
        )
        modules = set(contract.arguments)
        self.assertTrue({
            "tools.test_schema_lifecycle",
            "tools.test_schema_evolution",
            "tools.test_alembic_migration",
            "tools.test_minimal_regeneration",
            "tools.test_runtime_harness",
            "tools.test_failure_localization",
        } <= modules)
        self.assertNotIn("tools.test_release_gate", modules)

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

    def test_forged_local_promotion_json_is_rejected_without_gh(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory)
            result = release_gate._validate_trusted_promotion(
                artifact, COMMIT, gh_finder=lambda _name: None
            )
        self.assertFalse(result.passed)
        self.assertTrue(result.blocked)

    def test_unsigned_promotion_artifact_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory)
            result = release_gate._validate_trusted_promotion(
                artifact,
                COMMIT,
                gh_finder=lambda _name: "gh",
                runner=lambda *args, **kwargs: completed(1, "no attestations found"),
            )
        self.assertFalse(result.passed)

    def test_tampered_promotion_artifact_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory)
            artifact.write_text("{}", encoding="utf-8")
            result = release_gate._validate_trusted_promotion(
                artifact,
                COMMIT,
                gh_finder=lambda _name: "gh",
                runner=lambda *args, **kwargs: completed(1, "subject digest mismatch"),
            )
        self.assertFalse(result.passed)

    def test_wrong_github_repository_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory, repository="attacker/project")
            result = release_gate._validate_trusted_promotion(
                artifact, COMMIT, gh_finder=lambda _name: "gh", runner=self._verified_gh
            )
        self.assertFalse(result.passed)

    def test_wrong_signer_workflow_is_rejected_by_gh_policy(self):
        def wrong_signer(command, **kwargs):
            self.assertEqual(
                command[command.index("--signer-workflow") + 1],
                release_gate.PROMOTION_SIGNER_WORKFLOW,
            )
            return completed(1, "signer workflow mismatch")

        with TemporaryDirectory() as directory:
            result = release_gate._validate_trusted_promotion(
                self._promotion(directory), COMMIT, gh_finder=lambda _name: "gh", runner=wrong_signer
            )
        self.assertFalse(result.passed)

    def test_wrong_source_ref_is_rejected_by_gh_policy(self):
        def wrong_ref(command, **kwargs):
            self.assertEqual(command[command.index("--source-ref") + 1], promotion_evidence.SOURCE_REF)
            return completed(1, "source ref mismatch")

        with TemporaryDirectory() as directory:
            result = release_gate._validate_trusted_promotion(
                self._promotion(directory), COMMIT, gh_finder=lambda _name: "gh", runner=wrong_ref
            )
        self.assertFalse(result.passed)

    def test_wrong_source_digest_is_rejected_by_gh_policy(self):
        def wrong_digest(command, **kwargs):
            self.assertEqual(command[command.index("--source-digest") + 1], COMMIT)
            return completed(1, "source digest mismatch")

        with TemporaryDirectory() as directory:
            result = release_gate._validate_trusted_promotion(
                self._promotion(directory), COMMIT, gh_finder=lambda _name: "gh", runner=wrong_digest
            )
        self.assertFalse(result.passed)

    def test_stale_commit_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory, commit_sha="a" * 40)
            result = release_gate._validate_trusted_promotion(
                artifact, COMMIT, gh_finder=lambda _name: "gh", runner=self._verified_gh
            )
        self.assertFalse(result.passed)

    def test_signed_fail_result_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory, result="FAIL")
            result = release_gate._validate_trusted_promotion(
                artifact, COMMIT, gh_finder=lambda _name: "gh", runner=self._verified_gh
            )
        self.assertFalse(result.passed)

    def test_missing_required_promotion_field_is_rejected(self):
        with TemporaryDirectory() as directory:
            artifact = self._promotion(directory)
            document = json.loads(artifact.read_text(encoding="utf-8"))
            del document["checks"]
            artifact.write_text(json.dumps(document), encoding="utf-8")
            result = release_gate._validate_trusted_promotion(
                artifact, COMMIT, gh_finder=lambda _name: "gh", runner=self._verified_gh
            )
        self.assertFalse(result.passed)

    def test_valid_github_attestation_and_policy_return_pass(self):
        commands = []
        invocations = []

        def verified(command, **kwargs):
            commands.append(command)
            invocations.append(kwargs)
            return self._verified_gh(command, **kwargs)

        with TemporaryDirectory() as directory:
            result = release_gate._validate_trusted_promotion(
                self._promotion(directory), COMMIT, gh_finder=lambda _name: "gh", runner=verified
            )
        self.assertTrue(result.passed)
        self.assertIn("--deny-self-hosted-runners", commands[0])
        self.assertNotIn("shell", invocations[0])

    def test_promotion_workflow_has_least_privilege_and_attests_after_checks(self):
        workflow = (release_gate.REPOSITORY_ROOT / ".github" / "workflows" / "arcacore-security-promotion.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertLess(workflow.index("Release-gate unit tests"), workflow.index("actions/attest@v4"))
        self.assertLess(workflow.index("Real Docker and Compose"), workflow.index("actions/attest@v4"))

    def test_promotion_workflow_has_no_result_or_commit_inputs(self):
        workflow = (release_gate.REPOSITORY_ROOT / ".github" / "workflows" / "arcacore-security-promotion.yml").read_text(encoding="utf-8")
        self.assertNotIn("inputs:", workflow)
        self.assertIn("python -m tools.promotion_evidence", workflow)

    def test_local_codex_security_artifact_remains_blocked(self):
        with TemporaryDirectory() as directory:
            review = self._review(directory)
            result = release_gate.validate_security_review(review, COMMIT, runner=self._snapshot_runner)
        self.assertFalse(result.passed)
        self.assertTrue(result.blocked)

    def test_promotion_evidence_is_deterministic_and_uses_github_identity(self):
        environment = {
            "GITHUB_REPOSITORY": promotion_evidence.REPOSITORY,
            "GITHUB_SHA": COMMIT,
            "GITHUB_REF": promotion_evidence.SOURCE_REF,
            "GITHUB_WORKFLOW": promotion_evidence.WORKFLOW_NAME,
            "GITHUB_RUN_ID": "12345",
        }
        self.assertEqual(
            promotion_evidence.evidence_from_github_environment(environment),
            promotion_evidence.evidence_from_github_environment(dict(reversed(list(environment.items())))),
        )

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
        self.assertNotIn("ARCCORE V1: COMPLETE", output)

    def test_v1_completion_is_emitted_only_after_both_gates_pass(self):
        results = [
            *(release_gate.GateResult(contract.name, True, "1 tests", tests=1) for contract in release_gate.CONTRACTS),
            release_gate.GateResult("Independent security review", True, "trusted"),
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
        self.assertIn("ARCCORE SECURITY PROMOTION GATE: PASS", output)
        self.assertIn("ARCCORE RELEASE GATE: PASS", output)
        self.assertTrue(output.endswith("ARCCORE V1: COMPLETE"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
