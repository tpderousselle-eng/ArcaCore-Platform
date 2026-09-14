"""Complete architecture checkpoint lineage, hostile data, and inert validation."""

from contextlib import ExitStack
import copy
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.architecture_clarification import ArchitectureFinalization
from arcadev.gaming_studio_architecture import ARCHITECTURE_AREA, read_architecture_authority
from arcadev import gaming_studio_architecture_checkpoint as production
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes
from arcadev.gaming_studio_plan_approval import APPROVAL_AREA
from arcadev.plan_architecture_handoff import PlanArchitectureHandoff


class ProductionArchitectureCheckpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = PlanArchitectureHandoff.from_json(
            (AUTHORITY_DIRECTORY / APPROVAL_AREA / "plan_architecture_handoff.json").read_text(encoding="utf-8"))
        cls.finalization = ArchitectureFinalization.from_json(
            (AUTHORITY_DIRECTORY / ARCHITECTURE_AREA / "architecture_finalization.json").read_text(encoding="utf-8"),
            handoff=cls.handoff)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)
        self.area = self.root / ARCHITECTURE_AREA
        self.package = {n: (self.area / n).read_bytes() for n in production.ARCHITECTURE_PACKAGE_FILES}

    def reject_mutation(self, relative, change, rehash=False):
        path = self.root / relative
        original = path.read_bytes()
        cp_path = self.area / "checkpoint.json"
        cp_original = cp_path.read_bytes()
        value = json.loads(original)
        change(value)
        path.write_bytes(canonical_bytes(value))
        if rehash:
            cp = json.loads(cp_path.read_bytes())
            cp["authority_digests"][relative] = digest_bytes(path.read_bytes())
            cp_path.write_bytes(canonical_bytes(cp))
        try:
            with self.assertRaises(ValueError):
                production.validate_production_architecture_checkpoint(self.root)
        finally:
            path.write_bytes(original)
            cp_path.write_bytes(cp_original)

    def test_full_public_replay_and_canonical_package(self):
        actual = production.validate_production_architecture_checkpoint(self.root)
        self.assertEqual(actual, json.loads(self.package["checkpoint.json"]))
        self.assertEqual(self.package, production.production_architecture_checkpoint_package(self.root))

    def test_checkpoint_complete_digest_inventory_counts_and_stage(self):
        cp = json.loads(self.package["checkpoint.json"])
        architecture = self.finalization.original_architecture
        names = production.architecture_historical_authority_names() | {
            f"{ARCHITECTURE_AREA}/{n}" for n in production.ARCHITECTURE_PACKAGE_FILES - {"checkpoint.json"}}
        self.assertEqual(set(cp["authority_digests"]), names)
        self.assertEqual(len(production.architecture_historical_authority_names()), 25)
        for name, digest in cp["authority_digests"].items():
            self.assertEqual(digest, digest_bytes((self.root / name).read_bytes()))
        for key, expected in {
            "schema": production.ARCHITECTURE_CHECKPOINT_SCHEMA, "schema_version": 1, "package_version": 4,
            "project_id": architecture.project_id, "software_plan_id": architecture.software_plan_id,
            "plan_finalization_id": architecture.plan_finalization_id, "approved_plan_id": architecture.approved_plan_id,
            "plan_architecture_handoff_id": self.handoff.handoff_id,
            "architecture_specification_id": architecture.architecture_id,
            "architecture_finalization_id": self.finalization.finalization_id,
            "component_count": len(architecture.components), "interface_count": len(architecture.interfaces),
            "data_flow_count": len(architecture.data_flows), "aspect_count": len(architecture.aspects),
            "unresolved_question_count": len(self.finalization.unresolved_questions), "conflict_count": 0,
            "effective_ready_for_approval": False, "architecture_approved": False, "models_authorized": False,
            "current_stage": "ARCHITECTURE", "project_status": "IN_PROGRESS",
            "status": "BLOCKED_PENDING_ARCHITECTURE_CLARIFICATION",
            "next_authorized_action": "COLLECT_EXPLICIT_ARCHITECTURE_CLARIFICATIONS",
        }.items():
            self.assertEqual(cp[key], expected, key)

    def test_every_upstream_record_bound_and_rehashed_parent_changes_rejected(self):
        for name in sorted(production.architecture_historical_authority_names()):
            with self.subTest(name=name):
                self.reject_mutation(name, lambda v: v.update(unapproved=True))
        for name, key in (("production_plan/software_plan.json", "plan_id"),
                          (APPROVAL_AREA + "/approved_plan.json", "approval_id"),
                          (APPROVAL_AREA + "/plan_architecture_handoff.json", "handoff_id")):
            with self.subTest(name=name):
                self.reject_mutation(name, lambda v: v.update({key: "forged"}), rehash=True)

    def test_rehashed_architecture_sources_boundaries_and_questions_rejected(self):
        # Isolate the checkpoint comparison against a public reconstructed state.
        # Full unmocked reconstruction is exercised in test_full_public_replay.
        with patch.object(production, "production_architecture_initial_state", return_value=(self.handoff, self.finalization)):
            for change in (
                lambda v: v["objective"].update(source_requirements=["invented_plan_source"]),
                lambda v: v["aspects"].pop(), lambda v: v["components"].pop(),
                lambda v: v["interfaces"].pop(), lambda v: v["data_flows"].pop(),
                lambda v: v["open_architecture_questions"].pop(),
                lambda v: v["open_architecture_questions"][0].update(question="Rewritten question"),
                lambda v: v["readiness"].update(ready_for_finalization=True),
            ):
                self.reject_mutation(ARCHITECTURE_AREA + "/architecture_specification.json", change, rehash=True)

    def test_rehashed_finalization_review_request_and_checkpoint_forgery_rejected(self):
        with patch.object(production, "production_architecture_initial_state", return_value=(self.handoff, self.finalization)):
            for name, change in (
                ("architecture_finalization.json", lambda v: v.update(finalization_id="forged")),
                ("architecture_finalization.json", lambda v: v["decisions"].append({"accepted_values": ["fake"]})),
                ("architecture_finalization.json", lambda v: v["history"].append({"answer": "fake"})),
                ("clarification_review.json", lambda v: v.update(architecture_approved=True)),
                ("clarification_request.json", lambda v: v["questions"][0].update(architecture_question_id="forged")),
                ("clarification_request.json", lambda v: v.update(answers_present=True)),
                ("checkpoint.json", lambda v: v.update(current_stage="MODELS", models_authorized=True)),
                ("checkpoint.json", lambda v: v.update(approved_architecture={})),
            ):
                self.reject_mutation(ARCHITECTURE_AREA + "/" + name, change, rehash=name != "checkpoint.json")

    def test_later_authority_fixtures_and_unknown_entries_rejected(self):
        for name in ("architecture_clarification_answer.json", "architecture_decision.json", "approved_architecture.json",
                     "architecture_models_handoff.json", "domain_model.json", "backend.json", "frontend.json", "fixture.json"):
            path = self.area / name
            path.write_bytes(b"{}\n")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown or missing"):
                production.validate_production_architecture_checkpoint(self.root)
            path.unlink()
        (self.area / "unapproved").mkdir()
        with self.assertRaises(ValueError):
            production.validate_production_architecture_checkpoint(self.root)

    def test_malformed_duplicate_secret_oversized_missing_and_nonregular_records(self):
        path = self.area / "architecture_specification.json"
        for raw in (b"\xff", b'{"schema":1,"schema":2}\n', b'{"password":"secret-value"}\n', b" " * 5_000_001):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                production.validate_production_architecture_checkpoint(self.root)
        path.unlink()
        with self.assertRaises(ValueError):
            production.validate_production_architecture_checkpoint(self.root)
        path.mkdir()
        with self.assertRaises(ValueError):
            production.validate_production_architecture_checkpoint(self.root)

    def test_links_junctions_network_paths_and_untrusted_digest_paths_rejected(self):
        original = Path.is_symlink
        for kind in ("is_symlink", "is_junction"):
            with patch.object(Path, kind, autospec=True, side_effect=lambda p: p == self.area or original(p)):
                with self.assertRaisesRegex(ValueError, "links"):
                    production.validate_production_architecture_checkpoint(self.root)
        for path in ("//server/share/authority", "//?/C:/authority"):
            with patch.object(Path, "stat", side_effect=AssertionError("filesystem")), self.assertRaisesRegex(ValueError, "local"):
                production.validate_production_architecture_checkpoint(Path(path))
        cp_path = self.area / "checkpoint.json"
        cp = json.loads(cp_path.read_bytes())
        cp["authority_digests"]["../../outside-secret.json"] = "0" * 64
        cp_path.write_bytes(canonical_bytes(cp))
        with patch.object(production, "read_authority", wraps=production.read_authority) as reader:
            with self.assertRaises(ValueError):
                production.validate_production_architecture_checkpoint(self.root)
        self.assertTrue(all(".." not in call.args[0].parts for call in reader.call_args_list))

    def test_public_validation_has_no_answers_approval_models_generation_execution_network_or_writes(self):
        from arcadev.architecture_clarification import ArchitectureClarificationAnswer, ArchitectureDecision
        from arcadev.architecture_approval import ApprovedArchitecture
        from arcadev.architecture_models_handoff import ArchitectureModelsHandoff
        from arcadev import domain_model_engine, backend_generation
        from tools import generate
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for owner, name in ((ArchitectureClarificationAnswer, "create"), (ArchitectureDecision, "create"),
                (ApprovedArchitecture, "create"), (ArchitectureModelsHandoff, "create"), (ArchitectureFinalization, "resolve"),
                (domain_model_engine, "generate_baseline_domain_model"), (backend_generation, "generate_backend"),
                (generate, "generate_module"), (socket, "socket"), (subprocess, "Popen"),
                (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            production.validate_production_architecture_checkpoint(self.root)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
