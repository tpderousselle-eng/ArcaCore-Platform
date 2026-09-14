"""Complete resolved checkpoint, historical bindings, hostile files, and inert validation."""

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

from arcadev import gaming_studio_architecture_resolution_checkpoint as production
from arcadev.gaming_studio_architecture_resolution import RESOLUTION_AREA, INITIAL_FINALIZATION_ID, ARCHITECTURE_ID
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes


class ArchitectureResolutionCheckpointTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)
        self.area = self.root / RESOLUTION_AREA
        self.package = {name: (self.area / name).read_bytes() for name in production.RESOLUTION_PACKAGE_FILES}
        self.cp = json.loads(self.package["checkpoint.json"])

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
                production.validate_architecture_resolution_checkpoint(self.root)
        finally:
            path.write_bytes(original)
            cp_path.write_bytes(cp_original)

    def test_full_public_checkpoint_validation_without_later_authority_execution_or_writes(self):
        from arcadev import architecture_approval, domain_model_engine, backend_generation
        from arcadev.architecture_models_handoff import ArchitectureModelsHandoff
        from tools import generate
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for owner, name in ((architecture_approval, "approve_architecture"),
                (architecture_approval.ApprovedArchitecture, "create"), (ArchitectureModelsHandoff, "create"),
                (domain_model_engine, "generate_baseline_domain_model"), (backend_generation, "generate_backend"),
                (generate, "generate_module"), (socket, "socket"), (subprocess, "Popen"),
                (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            actual = production.validate_architecture_resolution_checkpoint(self.root)
        self.assertEqual(actual, self.cp)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_checkpoint_exact_ids_counts_scope_and_complete_digests(self):
        review = json.loads(self.package["resolution_review.json"])
        historical = json.loads((self.root / "production_architecture/checkpoint.json").read_bytes())
        for key, expected in {
            "schema": production.RESOLUTION_CHECKPOINT_SCHEMA, "schema_version": 1, "package_version": 3,
            "architecture_specification_id": ARCHITECTURE_ID,
            "initial_architecture_finalization_id": INITIAL_FINALIZATION_ID,
            "architecture_finalization_id": review["architecture_finalization_id"],
            "accepted_decision_ids": review["accepted_decision_ids"], "accepted_decision_count": 8,
            "history_count": 8, "unresolved_question_count": 0, "conflict_count": 0,
            "effective_ready_for_approval": True, "current_stage": "ARCHITECTURE", "project_status": "IN_PROGRESS",
            "architecture_approved": False, "models_authorized": False,
            "status": "ARCHITECTURE_READY_FOR_APPROVAL", "next_authorized_action": "REQUEST_EXPLICIT_ARCHITECTURE_APPROVAL",
        }.items():
            self.assertEqual(self.cp[key], expected, key)
        for key in ("project_id", "software_plan_id", "plan_finalization_id", "approved_plan_id", "plan_architecture_handoff_id"):
            self.assertEqual(self.cp[key], historical[key])
        names = production.resolution_historical_authority_names() | {
            f"{RESOLUTION_AREA}/{name}" for name in production.RESOLUTION_PACKAGE_FILES - {"checkpoint.json"}}
        self.assertEqual(set(self.cp["authority_digests"]), names)
        self.assertEqual(len(names), 33)
        for name, digest in self.cp["authority_digests"].items():
            self.assertEqual(digest_bytes((self.root / name).read_bytes()), digest, name)

    def test_all_historical_authority_and_rehashed_plan_architecture_question_changes_rejected(self):
        for name in sorted(production.resolution_historical_authority_names()):
            with self.subTest(name=name):
                self.reject_mutation(name, lambda v: v.update(forged=True))
        for name, change in (
            ("production_plan/software_plan.json", lambda v: v.update(plan_id="forged")),
            ("production_architecture/architecture_specification.json", lambda v: v["open_architecture_questions"][0].update(question="Rewritten")),
            ("production_architecture/clarification_request.json", lambda v: v["questions"][0].update(area="integration")),
        ):
            self.reject_mutation(name, change, rehash=True)

    def test_changed_answer_normalized_value_evidence_and_mapping_rejected_even_rehashed(self):
        for key, value in (("user_answer", "Use another implementation"),
                           ("normalized_values", ["AWS S3"]), ("evidence", ["AWS S3"]),
                           ("target_question_id", "forged")):
            self.reject_mutation(RESOLUTION_AREA + "/clarification_authorization.json",
                lambda v: v["approvals"][0]["answer"].update({key: value}), rehash=True)

    def test_changed_missing_ninth_decision_and_stale_lineage_rejected_even_rehashed(self):
        for change in (
            lambda v: v["decisions"][0].update(decision_id="forged"),
            lambda v: v["decisions"].pop(),
            lambda v: v["decisions"].append(copy.deepcopy(v["decisions"][0])),
            lambda v: v["history"].reverse(),
            lambda v: v["history"][1]["answer"].update(target_finalization_id=INITIAL_FINALIZATION_ID),
        ):
            self.reject_mutation(RESOLUTION_AREA + "/architecture_finalization.json", change, rehash=True)

    def test_forged_readiness_approval_models_domain_model_and_digest_paths_rejected(self):
        for key, value in (("effective_ready_for_approval", False), ("accepted_decision_count", 9),
            ("architecture_approved", True), ("models_authorized", True), ("current_stage", "MODELS"),
            ("approved_architecture", {}), ("architecture_models_handoff", {}), ("domain_model", {})):
            self.reject_mutation(RESOLUTION_AREA + "/checkpoint.json", lambda v: v.update({key: value}))
        cp = copy.deepcopy(self.cp)
        cp["authority_digests"]["../../outside-secret.json"] = "0" * 64
        (self.area / "checkpoint.json").write_bytes(canonical_bytes(cp))
        with patch.object(production, "read_architecture_authority", wraps=production.read_architecture_authority) as reader:
            with self.assertRaises(ValueError):
                production.validate_architecture_resolution_checkpoint(self.root)
        self.assertTrue(all(".." not in call.args[0].parts for call in reader.call_args_list))

    def test_unknown_later_authority_and_missing_or_nonregular_file_rejected(self):
        for name in ("approved_architecture.json", "architecture_models_handoff.json", "domain_model.json",
                     "backend.json", "frontend.json", "project.json", "unknown.json"):
            path = self.area / name
            path.write_bytes(b"{}\n")
            with self.subTest(name=name), self.assertRaises(ValueError):
                production.validate_architecture_resolution_checkpoint(self.root)
            path.unlink()
        path = self.area / "resolution_review.json"
        path.unlink()
        with self.assertRaises(ValueError):
            production.validate_architecture_resolution_checkpoint(self.root)
        path.mkdir()
        with self.assertRaises(ValueError):
            production.validate_architecture_resolution_checkpoint(self.root)

    def test_malformed_duplicate_noncanonical_and_oversized_json_rejected(self):
        for name in production.RESOLUTION_PACKAGE_FILES:
            for raw in (b"{", b"\xff", b'{"schema":1,"schema":2}\n', b" ", b" " * 5_000_001):
                path = self.area / name
                path.write_bytes(raw)
                with self.subTest(name=name, raw=raw[:20]), self.assertRaises(ValueError):
                    production.validate_architecture_resolution_checkpoint(self.root)
                path.write_bytes(self.package[name])

    def test_links_junctions_and_network_paths_rejected_before_traversal(self):
        for kind in ("is_symlink", "is_junction"):
            original = getattr(Path, kind)
            for linked in (self.area, self.area / "checkpoint.json"):
                with patch.object(Path, kind, autospec=True, side_effect=lambda p: p == linked or original(p)):
                    with self.assertRaisesRegex(ValueError, "links"):
                        production.validate_architecture_resolution_checkpoint(self.root)
        for path in ("//server/share/authority", "//?/C:/authority"):
            with patch.object(Path, "stat", side_effect=AssertionError("filesystem")), self.assertRaisesRegex(ValueError, "local"):
                production.validate_architecture_resolution_checkpoint(Path(path))


if __name__ == "__main__":
    unittest.main()
