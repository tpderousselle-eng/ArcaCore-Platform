"""Read-only state compatibility evidence reconstructed from approved authority."""
from .arcacore_generation_request import (
    ArcaCoreCapability as C, ArcaCoreCapabilityStatus as S,
    validate_arcacore_generation_request,
)


def state_certification_report(request, *, previous_counts):
    """Compare an explicitly supplied historical count with current validated scope.

    Historical counts are context, never generation authority. Current counts,
    entity dispositions and dependency evidence are always reconstructed.
    """
    request = validate_arcacore_generation_request(request)
    keys = {"blockers", "unsupported", "requires_certification"}
    if type(previous_counts) is not dict or set(previous_counts) != keys or any(
        type(v) is not int or v < 0 for v in previous_counts.values()
    ) or previous_counts["blockers"] != previous_counts["unsupported"] + previous_counts["requires_certification"]:
        raise ValueError("Historical counts must be explicit nonnegative totals.")
    mappings = {m.responsibility_id: m for m in request.capability_mappings if m.capability is C.LOGICAL_STATE}
    model = request.approved_backend.package.original_backend.resolved_model
    entities = []
    for entity in sorted(model.entities, key=lambda e: e.entity_id):
        mapping = mappings[entity.entity_id]
        entities.append({"entity_id": entity.entity_id, "name": entity.name,
            "disposition": "GENERATABLE" if mapping.status is S.SUPPORTED else "BLOCKED",
            "reason": mapping.reason, "module_request_ids": list(mapping.module_request_ids)})
    after = {"blockers": len(request.blocking_findings),
        "unsupported": len(request.unsupported_mappings),
        "requires_certification": len(request.required_certification_mappings)}
    groups = {}
    for capability in C:
        findings = [f for f in request.blocking_findings if f.capability is capability]
        groups[capability.name] = {"count": len(findings),
            "unsupported": sum(f.status is S.UNSUPPORTED for f in findings),
            "requires_certification": sum(f.status is S.REQUIRES_CERTIFICATION for f in findings),
            "findings": [f.canonical_dict() for f in findings]}
    return {"request_id": request.request_id, "before": dict(previous_counts), "after": after,
        "delta": {key: after[key] - previous_counts[key] for key in sorted(keys)},
        "entities": entities, "all_state_generatable": bool(entities) and all(e["disposition"] == "GENERATABLE" for e in entities),
        "eligible_for_backend_generation": request.eligible_for_generation,
        "module_request_count": len(request.module_requests),
        "dependency_plan": request.dependency_plan.canonical_dict(), "remaining_by_capability": groups}
