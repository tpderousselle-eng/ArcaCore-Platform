"""Certified production IDEA-to-PLAN gate; no planning or generation implementation."""

from .gaming_studio_idea import checkpoint_manifest, clarification_review, materialize_idea
from .gaming_studio_intent import canonical_bytes, digest_bytes, local_authority_path, parse_authority, read_authority
from .gaming_studio_project import (
    PROJECT_PACKAGE_FILES, materialize_project, project_package,
    validate_finalization, validate_metadata_authority,
)
from .idea_plan_handoff import IdeaPlanHandoff, TransitionDecision
from .project import ArcaDevProject


CURRENT_PACKAGE_FILES = PROJECT_PACKAGE_FILES | frozenset({
    "idea_plan_handoff.json", "project.json", "checkpoint.json",
})


def production_handoff(intent, finalization_data, metadata_data, project_data):
    """Check complete production inputs, then delegate only to the public gate."""
    finalization = validate_finalization(finalization_data, intent)
    expected_project = materialize_project(finalization, metadata_data, intent)
    project = ArcaDevProject.from_dict(parse_authority(project_data))
    if project_data != expected_project.canonical_json().encode("utf-8"):
        raise ValueError("IDEA handoff source project is stale or differs from production reconstruction.")
    handoff = IdeaPlanHandoff.create(project, finalization)
    return IdeaPlanHandoff.from_dict(handoff.canonical_dict())


def transition_package(intent, raw_commit):
    package = project_package(intent, raw_commit)
    handoff = production_handoff(
        intent, package["idea_finalization.json"], package["metadata_authority.json"],
        package["source_project.json"],
    )
    package["idea_plan_handoff.json"] = handoff.canonical_json().encode("utf-8")
    package["project.json"] = handoff.resulting_project.canonical_json().encode("utf-8")
    # Retain the Resolution 2 checkpoint as history. The new checkpoint is a
    # projection of the certified result, never a second transition algorithm.
    checkpoint = parse_authority(package["idea_checkpoint.json"])
    transitioned = handoff.decision is TransitionDecision.TRANSITIONED
    seed = materialize_idea(intent)
    seed_files = {
        "production_intent.json": intent.canonical_bytes(),
        "idea_intake.json": seed.canonical_json().encode("utf-8"),
        "clarification_review.json": canonical_bytes(clarification_review(intent, seed)),
        "checkpoint.json": canonical_bytes(checkpoint_manifest(intent, seed)),
    }
    checkpoint.update(
        resolution=3, current_stage=handoff.resulting_project.current_build_stage.value,
        project_status=handoff.resulting_project.project_status.value,
        status="PLAN_READY_FOR_GENERATION" if transitioned else "BLOCKED_IDEA_PLAN_HANDOFF",
        next_authorized_action="GENERATE_PRODUCTION_SOFTWARE_PLAN" if transitioned else "RESOLVE_IDEA_PLAN_HANDOFF_BLOCKERS",
        handoff_id=handoff.handoff_id, decision=handoff.decision.value, eligible=handoff.eligible,
        consistency=handoff.snapshot.consistency.canonical_dict(),
        authority_digests={
            **{name: digest_bytes(data) for name, data in seed_files.items()},
            **{f"idea_resolution/{name}": digest_bytes(data) for name, data in package.items()},
        },
    )
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_transition_package(directory, intent):
    directory = local_authority_path(directory)
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != CURRENT_PACKAGE_FILES:
        raise ValueError("Current resolution package has unknown or missing authority files.")
    actual = {name: read_authority(directory / name) for name in sorted(CURRENT_PACKAGE_FILES)}
    for data in actual.values():
        parse_authority(data)
    finalization = validate_finalization(actual["idea_finalization.json"], intent)
    metadata = parse_authority(actual["metadata_authority.json"])
    validate_metadata_authority(actual["metadata_authority.json"], finalization)
    expected = transition_package(intent, metadata["source"]["raw_commit"].encode("utf-8"))
    if actual != expected:
        raise ValueError("Current resolution package differs from the exact production lineage.")
    IdeaPlanHandoff.from_dict(parse_authority(actual["idea_plan_handoff.json"]))
    return parse_authority(expected["checkpoint.json"])
