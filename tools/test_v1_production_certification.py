"""Fail-closed inventory checks for ArcaCore v1 production certification."""

import unittest

from tools import promotion_evidence, release_gate


class V1ProductionCertificationTest(unittest.TestCase):
    def contract(self, prefix):
        return next(item for item in release_gate.CONTRACTS if item.name.startswith(prefix))

    def test_real_postgresql_is_a_mandatory_release_contract(self):
        contract = self.contract("PostgreSQL")
        self.assertIn("tools.test_postgresql_runtime", contract.arguments)
        self.assertEqual(contract.approved_skips, frozenset())

    def test_real_docker_compose_is_enabled_and_cannot_skip(self):
        contract = self.contract("Docker & Compose")
        self.assertEqual(contract.environment[release_gate.DOCKER_RUNTIME_ENV], "1")
        self.assertEqual(contract.approved_skips, frozenset())

    def test_kubernetes_health_and_probe_suites_are_mandatory(self):
        arguments = set(self.contract("Kubernetes & health").arguments)
        self.assertTrue({
            "tools.test_kubernetes",
            "tools.test_kubernetes_validation",
            "tools.test_health_checks",
        } <= arguments)

    def test_restart_recovery_persistence_and_determinism_are_mandatory(self):
        names = {item.name for item in release_gate.CONTRACTS}
        self.assertTrue({
            "Autonomous generation lifecycle",
            "Autonomous runtime recovery",
            "Failure injection / atomicity",
            "Determinism / reproducibility",
        } <= names)

    def test_promotion_evidence_requires_every_production_result(self):
        required = set(promotion_evidence.REQUIRED_CHECKS)
        self.assertTrue({
            "discovery",
            "postgresql",
            "kubernetes_health",
            "docker_compose",
            "release_gate_unit",
        } <= required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
