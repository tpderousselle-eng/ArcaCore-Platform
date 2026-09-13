"""Replay production IDEA and materialize a project with verified administrative metadata."""

from datetime import datetime, timezone
import hashlib

from .clarification import IdeaFinalization
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, canonical_bytes, digest_bytes, local_authority_path,
    parse_authority, read_authority,
)
from .gaming_studio_resolution import authorization_package, replay_authorization
from .idea_intake import IdeaIntake
from .project import ArcaDevProject, ProjectMetadata


CERTIFIED_CHECKPOINT_COMMIT = "e47123a13f380dd73dd0aa7a36b5036713ef0fd8"
METADATA_SCHEMA = "arcadev.gaming_studio.project_metadata_authority"
CHECKPOINT_SCHEMA = "arcadev.gaming_studio.resolution_checkpoint"
PROJECT_PACKAGE_FILES = frozenset({
    "clarification_authorization.json", "idea_finalization.json", "current_intake.json",
    "metadata_authority.json", "source_project.json", "idea_checkpoint.json",
})


def production_finalization(intent):
    return replay_authorization(canonical_bytes(authorization_package(intent)), intent)


def validate_finalization(data, intent):
    parsed = IdeaFinalization.from_dict(parse_authority(data))
    expected = production_finalization(intent)
    if data != expected.canonical_json().encode("utf-8"):
        raise ValueError("Finalization differs from the exact production clarification lineage.")
    return parsed


def metadata_authority(raw_commit, finalization):
    """Prove the administrative timestamp from the pinned Git commit object.

    No Git process, host clock, network or asserted timestamp is trusted here.
    The hash verifies the entire commit object, including its committer epoch.
    This records the administrative inception of production authority, not the
    wall-clock time this replay or a future build was executed.
    """
    if not isinstance(raw_commit, bytes) or len(raw_commit) > 10_000:
        raise ValueError("Metadata commit proof must be bounded bytes.")
    object_bytes = b"commit " + str(len(raw_commit)).encode("ascii") + b"\0" + raw_commit
    if hashlib.sha1(object_bytes).hexdigest() != CERTIFIED_CHECKPOINT_COMMIT:
        raise ValueError("Metadata proof is not the certified checkpoint commit object.")
    text = raw_commit.decode("utf-8")
    headers = text.split("\n\n", 1)[0].splitlines()
    committer = next(line for line in headers if line.startswith("committer "))
    epoch = int(committer.rsplit(" ", 2)[1])
    timestamp = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = ProjectMetadata.create(created_at=timestamp, updated_at=timestamp)
    return {
        "schema": METADATA_SCHEMA, "schema_version": 1,
        "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "finalization_digest": digest_bytes(finalization.canonical_json().encode("utf-8")),
        "current_intake_id": finalization.current_intake_id,
        "source": {"kind": "certified_git_commit_committer_epoch",
                   "commit_oid": CERTIFIED_CHECKPOINT_COMMIT, "raw_commit": text},
        "timestamp_semantics": "Administrative inception of certified production authority; not artifact generation or build execution time.",
        "metadata": metadata.canonical_dict(),
    }


def validate_metadata_authority(data, finalization):
    value = parse_authority(data)
    source = value.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("raw_commit"), str):
        raise ValueError("Metadata requires the certified commit proof.")
    expected = metadata_authority(source["raw_commit"].encode("utf-8"), finalization)
    if data != canonical_bytes(expected):
        raise ValueError("Metadata authority or finalization binding is forged.")
    return ProjectMetadata.from_dict(expected["metadata"])


def materialize_project(finalization, metadata_data, intent):
    finalization = validate_finalization(finalization.canonical_json().encode("utf-8"), intent)
    if metadata_data is None:
        raise ValueError("Production project creation requires verified metadata authority.")
    metadata = validate_metadata_authority(metadata_data, finalization)
    intake = finalization.current_intake
    if finalization.conflicts or intake.assumptions or intake.unresolved_requirements or not intake.readiness.ready_for_plan:
        raise ValueError("Production IDEA is not eligible for project materialization.")
    project = finalization.to_project(metadata=metadata)
    return ArcaDevProject.from_dict(project.canonical_dict())


def idea_checkpoint(finalization, metadata_data=None, project=None):
    """Report a project only when a verified materialization is supplied internally."""
    intake = finalization.current_intake
    return {
        "schema": CHECKPOINT_SCHEMA, "schema_version": 1, "package_version": 2,
        "resolution": 2, "production_intent_digest": APPROVED_INTENT_DIGEST,
        "finalization_digest": digest_bytes(finalization.canonical_json().encode("utf-8")),
        "current_intake_id": finalization.current_intake_id,
        "current_intake_digest": digest_bytes(intake.canonical_json().encode("utf-8")),
        "metadata_authority_digest": digest_bytes(metadata_data) if metadata_data is not None else None,
        "project_id": project.project_id if project else None,
        "source_project_digest": digest_bytes(project.canonical_json().encode("utf-8")) if project else None,
        "current_stage": "IDEA", "project_status": project.project_status.value if project else None,
        "ready_for_plan": intake.readiness.ready_for_plan,
        "blocking_requirement_keys": list(intake.readiness.blocking_requirements),
        "conflict_count": len(finalization.conflicts), "assumption_count": len(intake.assumptions),
        "status": "IDEA_READY_FOR_TRANSITION" if project else "IDEA_READY_PENDING_PROJECT_METADATA",
        "next_authorized_action": "RUN_CERTIFIED_IDEA_PLAN_HANDOFF" if project else "COLLECT_AUTHORIZED_PROJECT_METADATA",
    }


def project_package(intent, raw_commit):
    finalization = production_finalization(intent)
    authority = canonical_bytes(metadata_authority(raw_commit, finalization))
    project = materialize_project(finalization, authority, intent)
    return {
        "clarification_authorization.json": canonical_bytes(authorization_package(intent)),
        "idea_finalization.json": finalization.canonical_json().encode("utf-8"),
        "current_intake.json": finalization.current_intake.canonical_json().encode("utf-8"),
        "metadata_authority.json": authority,
        "source_project.json": project.canonical_json().encode("utf-8"),
        "idea_checkpoint.json": canonical_bytes(idea_checkpoint(finalization, authority, project)),
    }


def validate_project_package(directory, intent):
    directory = local_authority_path(directory)
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != PROJECT_PACKAGE_FILES:
        raise ValueError("Resolution project package has unknown or missing files.")
    actual = {name: read_authority(directory / name) for name in sorted(PROJECT_PACKAGE_FILES)}
    for data in actual.values():
        parse_authority(data)
    finalization = validate_finalization(actual["idea_finalization.json"], intent)
    metadata = parse_authority(actual["metadata_authority.json"])
    validate_metadata_authority(actual["metadata_authority.json"], finalization)
    expected = project_package(intent, metadata["source"]["raw_commit"].encode("utf-8"))
    if actual != expected:
        raise ValueError("Resolution project package differs from canonical production reconstruction.")
    IdeaIntake.from_dict(parse_authority(actual["current_intake.json"]))
    ArcaDevProject.from_dict(parse_authority(actual["source_project.json"]))
    return parse_authority(expected["idea_checkpoint.json"])
