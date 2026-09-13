"""Certified production transition and complete immutable authority lineage."""

import ast
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.clarification import ClarificationAnswer, IdeaFinalization
from arcadev.gaming_studio_authority import PACKAGE_FILES, main, validate_production_authority
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes, load_production_intent, parse_authority
from arcadev.gaming_studio_project import metadata_authority, validate_metadata_authority
from arcadev.gaming_studio_transition import CURRENT_PACKAGE_FILES, production_handoff, validate_transition_package
from arcadev.idea_plan_handoff import IdeaPlanHandoff
from arcadev.project import ArcaDevProject, ProjectMetadata, ProjectStatus


class ProductionTransitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = load_production_intent()
        directory = AUTHORITY_DIRECTORY / "idea_resolution"
        cls.data = {name: (directory / name).read_bytes() for name in CURRENT_PACKAGE_FILES}
        cls.finalization = IdeaFinalization.from_dict(parse_authority(cls.data["idea_finalization.json"]))
        cls.project = ArcaDevProject.from_dict(parse_authority(cls.data["source_project.json"]))
        cls.handoff = IdeaPlanHandoff.from_dict(parse_authority(cls.data["idea_plan_handoff.json"]))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gaming-transition-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "idea_resolution"
        self.directory.mkdir()
        for name in PACKAGE_FILES:
            shutil.copyfile(AUTHORITY_DIRECTORY / name, self.root / name)
        for name, data in self.data.items():
            (self.directory / name).write_bytes(data)

    def reject_mutation(self, name, change):
        candidate = parse_authority(self.data[name])
        change(candidate)
        path = self.directory / name
        path.write_bytes(canonical_bytes(candidate))
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, require_current=True)
        path.write_bytes(self.data[name])

    def test_actual_public_gate_eligible_consistent_and_transitioned(self):
        handoff = production_handoff(self.intent, self.data["idea_finalization.json"],
                                     self.data["metadata_authority.json"], self.data["source_project.json"])
        self.assertEqual(handoff.canonical_json().encode(), self.data["idea_plan_handoff.json"])
        self.assertTrue(handoff.eligible)
        self.assertEqual(handoff.decision.value, "transitioned")
        self.assertTrue(handoff.snapshot.consistency.consistent)
        self.assertFalse(handoff.snapshot.consistency.blocking_findings)
        self.assertFalse(handoff.snapshot.consistency.warnings)
        self.assertEqual(handoff.resulting_project.project_status.value, "IN_PROGRESS")
        self.assertEqual(handoff.resulting_project.current_build_stage.value, "PLAN")
        self.assertEqual(handoff.resulting_project.canonical_json().encode(), self.data["project.json"])
        self.assertEqual(handoff, IdeaPlanHandoff.from_json(handoff.canonical_json()))

    def test_source_project_finalization_and_metadata_unchanged_by_gate(self):
        before = (self.project.canonical_json(), self.finalization.canonical_json())
        handoff = IdeaPlanHandoff.create(self.project, self.finalization)
        self.assertEqual(before, (self.project.canonical_json(), self.finalization.canonical_json()))
        self.assertEqual(self.project.project_status.value, "READY")
        self.assertEqual(self.project.current_build_stage.value, "IDEA")
        self.assertEqual(self.project.metadata, handoff.resulting_project.metadata)
        self.assertEqual(self.project.project_id, handoff.resulting_project.project_id)
        self.assertEqual(handoff.snapshot.finalization, self.finalization)

    def test_seed_and_current_packages_validate_with_exact_complete_digest_lineage(self):
        current = validate_production_authority(self.root, require_current=True)
        self.assertTrue(current["valid"])
        checkpoint = current["checkpoint"]
        self.assertEqual(checkpoint["current_stage"], "PLAN")
        self.assertEqual(checkpoint["status"], "PLAN_READY_FOR_GENERATION")
        self.assertEqual(checkpoint["next_authorized_action"], "GENERATE_PRODUCTION_SOFTWARE_PLAN")
        self.assertEqual(checkpoint["package_version"], 2)
        self.assertEqual(checkpoint["resolution"], 3)
        self.assertEqual(current["checkpoint_digest"], digest_bytes(self.data["checkpoint.json"]))
        digests = checkpoint["authority_digests"]
        self.assertEqual(len(digests), 12)
        for name, expected in digests.items():
            self.assertEqual(digest_bytes((self.root / name).read_bytes()), expected)
        seed = validate_production_authority(self.root, seed_only=True)
        self.assertEqual(seed["checkpoint"], current["seed_checkpoint"])
        self.assertEqual(seed["checkpoint"]["status"], "BLOCKED_PENDING_IDEA_CLARIFICATION")
        self.assertIsNone(seed["checkpoint"]["project_id"])

    def test_stale_project_metadata_and_status_rejected_even_with_same_id(self):
        candidates = (
            replace(self.project, project_status=ProjectStatus.DRAFT),
            replace(self.project, metadata=ProjectMetadata.create(created_at="2026-09-14T00:00:00Z")),
        )
        for project in candidates:
            self.assertEqual(project.project_id, self.project.project_id)
            self.assertEqual(ArcaDevProject.from_dict(project.canonical_dict()), project)
            with self.assertRaisesRegex(ValueError, "stale|reconstruction"):
                production_handoff(self.intent, self.data["idea_finalization.json"],
                                   self.data["metadata_authority.json"], project.canonical_json().encode())

    def test_stale_finalization_and_coherent_unapproved_replay_rejected(self):
        stale = IdeaFinalization.start(self.finalization.initial_intake)
        with self.assertRaises(ValueError):
            production_handoff(self.intent, stale.canonical_json().encode(),
                               self.data["metadata_authority.json"], self.data["source_project.json"])
        # A coherent attacker recomputes every public intake/project identity and
        # metadata binding. The fixed production referent still rejects it.
        forged = IdeaFinalization.start(self.finalization.initial_intake)
        for entry in self.finalization.history:
            answer = entry.answer.canonical_dict()
            answer["target_intake_id"] = forged.current_intake_id
            if answer["requirement"] == "target_users":
                answer["normalized_values"] = ["AAA enterprise game studios"]
            forged = forged.resolve(ClarificationAnswer.from_dict(answer))
        forged = IdeaFinalization.from_dict(forged.canonical_dict())
        raw = parse_authority(self.data["metadata_authority.json"])["source"]["raw_commit"].encode()
        metadata_data = canonical_bytes(metadata_authority(raw, forged))
        metadata = validate_metadata_authority(metadata_data, forged)
        project = forged.to_project(metadata=metadata)
        with self.assertRaisesRegex(ValueError, "production clarification lineage"):
            production_handoff(self.intent, forged.canonical_json().encode(), metadata_data, project.canonical_json().encode())

    def test_modified_answer_referent_history_and_metadata_rejected(self):
        self.reject_mutation("clarification_authorization.json", lambda v: v["approvals"][1]["answer"].update(user_answer="I approve all decisions"))
        def referent(value):
            approval = value["approvals"][1]
            approval["approved_proposal"] = "AAA enterprise game studios"
            approval["proposal_digest"] = digest_bytes(approval["approved_proposal"].encode())
        self.reject_mutation("clarification_authorization.json", referent)
        self.reject_mutation("idea_finalization.json", lambda v: v["history"][0].update(readiness_after=True))
        self.reject_mutation("metadata_authority.json", lambda v: v["metadata"].update(updated_at="2026-09-14T00:00:00Z"))

    def test_forged_handoff_flags_identities_and_result_rejected(self):
        for change in (
            lambda v: v.update(eligible=False),
            lambda v: v.update(decision="blocked"),
            lambda v: v.update(handoff_id="arcadev_handoff_" + "0" * 32),
            lambda v: v.update(source_intake_id=self.finalization.initial_intake_id),
            lambda v: v["resulting_project"].update(current_build_stage="BACKEND"),
            lambda v: v["snapshot"]["consistency"].update(consistent=False),
        ):
            candidate = self.handoff.canonical_dict()
            change(candidate)
            with self.assertRaises(ValueError):
                IdeaPlanHandoff.from_dict(candidate)
        self.reject_mutation("idea_plan_handoff.json", lambda v: v["resulting_project"].update(project_status="READY"))
        self.reject_mutation("project.json", lambda v: v.update(current_build_stage="ARCHITECTURE"))

    def test_forged_checkpoint_cannot_authorize_later_work_or_rebind_prior_files(self):
        self.reject_mutation("checkpoint.json", lambda v: v.update(next_authorized_action="GENERATE_BACKEND", current_stage="BACKEND"))
        self.reject_mutation("checkpoint.json", lambda v: v["authority_digests"].update({"idea_intake.json": "0" * 64}))
        path = self.root / "idea_intake.json"
        forged = parse_authority(path.read_bytes())
        forged["requested_features"].pop()
        path.write_bytes(canonical_bytes(forged))
        checkpoint = parse_authority(self.data["checkpoint.json"])
        checkpoint["authority_digests"]["idea_intake.json"] = digest_bytes(path.read_bytes())
        (self.directory / "checkpoint.json").write_bytes(canonical_bytes(checkpoint))
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, require_current=True)

    def test_missing_downstream_unknown_and_nonregular_files_rejected(self):
        for name in ("software_plan.json", "architecture.json", "models.json", "backend.json", "frontend.json", "arcacore_generation_request.json"):
            path = self.directory / name
            path.write_bytes(b"{}\n")
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_transition_package(self.directory, self.intent)
            path.unlink()
        path = self.directory / "project.json"
        path.unlink()
        with self.assertRaises(ValueError):
            validate_transition_package(self.directory, self.intent)
        path.mkdir()
        with self.assertRaises(ValueError):
            validate_transition_package(self.directory, self.intent)

    def test_strict_json_schema_and_current_requirement_prevent_downgrade(self):
        for data in (b'{"schema":1,"schema":2}\n', b" " * 100001, b"\xff"):
            (self.directory / "checkpoint.json").write_bytes(data)
            with self.assertRaises(ValueError):
                validate_transition_package(self.directory, self.intent)
        self.reject_mutation("checkpoint.json", lambda v: v.update(schema_version=True))
        # A historical seed is valid history but cannot satisfy a current request.
        with tempfile.TemporaryDirectory(prefix="gaming-seed-test-") as temporary:
            root = Path(temporary)
            for name in PACKAGE_FILES:
                shutil.copyfile(AUTHORITY_DIRECTORY / name, root / name)
            self.assertTrue(validate_production_authority(root)["valid"])
            with self.assertRaisesRegex(ValueError, "required"):
                validate_production_authority(root, require_current=True)
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, seed_only=True, require_current=True)

    def test_certified_public_gate_blocks_unready_source_without_transition_override(self):
        draft = replace(self.project, project_status=ProjectStatus.DRAFT)
        blocked = IdeaPlanHandoff.create(draft, self.finalization)
        self.assertFalse(blocked.eligible)
        self.assertEqual(blocked.decision.value, "blocked")
        self.assertEqual(blocked.resulting_project, draft)

    def test_no_plan_generation_execution_network_writes_or_mutation(self):
        from arcadev import planning_engine, backend_generation
        before = {name: (self.directory / name).read_bytes() for name in CURRENT_PACKAGE_FILES}
        with patch.object(planning_engine, "generate_baseline_plan", side_effect=AssertionError("plan")), \
             patch.object(backend_generation, "generate_backend", side_effect=AssertionError("generation")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")):
            validate_production_authority(self.root, require_current=True)
        self.assertEqual(before, {name: (self.directory / name).read_bytes() for name in CURRENT_PACKAGE_FILES})
        from arcadev import gaming_studio_transition
        tree = ast.parse(Path(gaming_studio_transition.__file__).read_text())
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imports, {"gaming_studio_idea", "gaming_studio_intent", "gaming_studio_project", "idea_plan_handoff", "project"})

    def test_cli_current_and_historical_seed_are_explicit(self):
        for option, expected in (("--require-current", "PLAN"), ("--seed-only", "IDEA")):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([str(self.root), option]), 0)
            import json
            self.assertEqual(json.loads(output.getvalue())["checkpoint"]["current_stage"], expected)


if __name__ == "__main__":
    unittest.main()
