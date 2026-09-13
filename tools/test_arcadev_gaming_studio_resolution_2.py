"""Production finalization and Git-proven administrative project metadata."""

from copy import deepcopy
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.clarification import IdeaFinalization
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, load_production_intent, parse_authority
from arcadev.gaming_studio_project import (
    CERTIFIED_CHECKPOINT_COMMIT, PROJECT_PACKAGE_FILES, idea_checkpoint,
    materialize_project, metadata_authority, production_finalization,
    validate_finalization, validate_metadata_authority, validate_project_package,
)
from arcadev.idea_intake import IdeaIntake
from arcadev.project import ArcaDevProject, ProjectMetadata


class ProductionProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = load_production_intent()
        cls.finalization = production_finalization(cls.intent)
        cls.directory = AUTHORITY_DIRECTORY / "idea_resolution"
        cls.metadata_data = (cls.directory / "metadata_authority.json").read_bytes()
        cls.metadata = parse_authority(cls.metadata_data)

    def test_five_accepted_replay_readiness_and_intake_roundtrip(self):
        result = validate_finalization((self.directory / "idea_finalization.json").read_bytes(), self.intent)
        self.assertEqual(result, self.finalization)
        self.assertEqual([e.outcome.value for e in result.history], ["accepted"] * 5)
        self.assertFalse(result.conflicts)
        self.assertFalse(result.current_intake.unresolved_requirements)
        self.assertFalse(result.current_intake.assumptions)
        self.assertTrue(result.current_intake.readiness.ready_for_plan)
        intake = (self.directory / "current_intake.json").read_bytes()
        self.assertEqual(IdeaIntake.from_dict(parse_authority(intake)).canonical_json().encode(), intake)

    def test_seed_and_previous_intake_lineage_preserved(self):
        seed = (AUTHORITY_DIRECTORY / "idea_intake.json").read_bytes()
        self.assertEqual(seed, self.finalization.initial_intake.canonical_json().encode())
        self.assertEqual(self.finalization.current_intake_id, self.finalization.history[-1].resulting_intake_id)
        for before, after in zip(self.finalization.history, self.finalization.history[1:]):
            self.assertEqual(before.resulting_intake_id, after.answer.target_intake_id)

    def test_metadata_commit_proof_and_canonical_utc_timestamp(self):
        import hashlib
        raw = self.metadata["source"]["raw_commit"].encode()
        actual = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(actual, CERTIFIED_CHECKPOINT_COMMIT)
        metadata = validate_metadata_authority(self.metadata_data, self.finalization)
        self.assertEqual(metadata.created_at, "2026-09-13T16:19:57Z")
        self.assertEqual(metadata.updated_at, metadata.created_at)
        self.assertEqual(metadata, ProjectMetadata.from_dict(metadata.canonical_dict()))

    def test_project_creation_requires_verified_metadata(self):
        for data in (None, b"{}\n", canonical_bytes({"created_at": "2026-09-13T16:19:57Z"})):
            with self.subTest(data=data), self.assertRaises(ValueError):
                materialize_project(self.finalization, data, self.intent)
        with self.assertRaises(ValueError):
            self.finalization.to_project(metadata=None)
        checkpoint = idea_checkpoint(self.finalization)
        self.assertEqual(checkpoint["status"], "IDEA_READY_PENDING_PROJECT_METADATA")
        self.assertIsNone(checkpoint["project_id"])
        self.assertEqual(checkpoint["current_stage"], "IDEA")

    def test_project_is_canonical_ready_idea_from_public_finalization(self):
        project = materialize_project(self.finalization, self.metadata_data, self.intent)
        data = (self.directory / "source_project.json").read_bytes()
        self.assertEqual(project.canonical_json().encode(), data)
        self.assertEqual(project, ArcaDevProject.from_dict(parse_authority(data)))
        self.assertEqual(project.project_status.value, "READY")
        self.assertEqual(project.current_build_stage.value, "IDEA")
        metadata = validate_metadata_authority(self.metadata_data, self.finalization)
        self.assertEqual(project, self.finalization.to_project(metadata=metadata))

    def test_forged_metadata_timestamp_proof_bindings_and_fields_rejected(self):
        mutations = (
            lambda v: v["metadata"].update(created_at="2026-09-14T00:00:00Z", updated_at="2026-09-14T00:00:00Z"),
            lambda v: v["source"].update(raw_commit=v["source"]["raw_commit"].replace("1789316397", "1789402797")),
            lambda v: v["source"].update(commit_oid="0" * 40),
            lambda v: v["source"].update(kind="user_asserted_timestamp"),
            lambda v: v.update(finalization_digest="0" * 64),
            lambda v: v.update(current_intake_id=self.finalization.initial_intake_id),
            lambda v: v.update(schema_version=True),
            lambda v: v.update(secret="password=unapproved"),
            lambda v: v["source"].pop("raw_commit"),
        )
        for index, change in enumerate(mutations):
            candidate = deepcopy(self.metadata)
            change(candidate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                materialize_project(self.finalization, canonical_bytes(candidate), self.intent)
        with self.assertRaises(ValueError):
            metadata_authority(b" " * 10001, self.finalization)

    def test_stale_or_modified_finalization_rejected_even_with_rebound_metadata(self):
        stale = IdeaFinalization.start(self.finalization.initial_intake)
        raw = self.metadata["source"]["raw_commit"].encode()
        rebound = canonical_bytes(metadata_authority(raw, stale))
        with self.assertRaises(ValueError):
            materialize_project(stale, rebound, self.intent)
        for change in (
            lambda v: v["history"][1].update(outcome="conflict"),
            lambda v: v["history"][1]["answer"].update(user_answer="I approve all products"),
            lambda v: v["current_intake"]["readiness"].update(ready_for_plan=False),
            lambda v: v["history"].pop(),
        ):
            candidate = self.finalization.canonical_dict()
            change(candidate)
            with self.assertRaises(ValueError):
                validate_finalization(canonical_bytes(candidate), self.intent)

    def test_persisted_project_package_reconstruction_and_forged_files(self):
        with tempfile.TemporaryDirectory(prefix="gaming-project-test-") as temporary:
            directory = Path(temporary)
            for name in PROJECT_PACKAGE_FILES:
                shutil.copyfile(self.directory / name, directory / name)
            checkpoint = validate_project_package(directory, self.intent)
            self.assertEqual(checkpoint["status"], "IDEA_READY_FOR_TRANSITION")
            for name in ("source_project.json", "idea_checkpoint.json", "current_intake.json"):
                path = directory / name
                original = path.read_bytes()
                raw = parse_authority(original)
                raw["unknown"] = "unapproved"
                path.write_bytes(canonical_bytes(raw))
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_project_package(directory, self.intent)
                path.write_bytes(original)
            (directory / "software_plan.json").write_bytes(b"{}\n")
            with self.assertRaises(ValueError):
                validate_project_package(directory, self.intent)

    def test_metadata_duplicate_keys_and_oversized_input_rejected(self):
        for data in (b'{"source":{},"source":{}}\n', b" " * 100001, b"\xff"):
            with self.assertRaises(ValueError):
                validate_metadata_authority(data, self.finalization)

    def test_no_plan_handoff_generation_network_process_or_writes(self):
        from arcadev.idea_plan_handoff import IdeaPlanHandoff
        from arcadev import planning_engine, backend_generation
        with patch.object(IdeaPlanHandoff, "create", side_effect=AssertionError("handoff")), \
             patch.object(planning_engine, "generate_baseline_plan", side_effect=AssertionError("plan")), \
             patch.object(backend_generation, "generate_backend", side_effect=AssertionError("generation")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")):
            materialize_project(self.finalization, self.metadata_data, self.intent)


if __name__ == "__main__":
    unittest.main()
