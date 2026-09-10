"""Deterministic IDEA-stage intake and intent-normalization contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any, Iterable, Mapping
import unicodedata

from .project import (
    ArcaDevProject,
    BuildStage,
    MAX_COLLECTION_ITEMS,
    MAX_ITEM_LENGTH,
    MAX_REQUEST_LENGTH,
    ProjectMetadata,
    ProjectSpecification,
    ProjectStatus,
)


ARCADEV_IDEA_INTAKE_SCHEMA = "arcadev.idea_intake"
ARCADEV_IDEA_INTAKE_SCHEMA_VERSION = 1
MAX_IDEA_INTAKE_BYTES = 1_000_000

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)"
    r"\s*(?:=|:)\s*[^\s,;]{4,}"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class IntentProvenance(str, Enum):
    """How a normalized value relates to the user's unchanged wording."""

    EXPLICIT = "explicitly_stated"
    DERIVED = "deterministically_derived"
    ASSUMED = "inferred_assumption"
    UNRESOLVED = "unresolved"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Idea intake contains duplicate key: {key}")
        result[key] = value
    return result


def _require_exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _validate_text(value: Any, label: str, *, maximum: int, preserve: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    normalized = value if preserve else " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} is empty or exceeds its size limit.")
    try:
        normalized.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{label} is not valid Unicode text.") from error
    if any(
        unicodedata.category(character) == "Cc" and character not in "\n\r\t"
        for character in normalized
    ):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET_ASSIGNMENT.search(normalized) or _PRIVATE_KEY.search(normalized):
        raise ValueError(f"{label} appears to contain a credential or secret value.")
    return normalized


def _validate_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a canonical lowercase identifier.")
    return value


def _canonical_texts(values: Iterable[str], label: str, *, maximum: int = MAX_ITEM_LENGTH) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a collection of text values.")
    try:
        normalized = tuple(_validate_text(value, label, maximum=maximum) for value in values)
    except TypeError as error:
        raise ValueError(f"{label} must be a collection of text values.") from error
    if len(normalized) > MAX_COLLECTION_ITEMS:
        raise ValueError(f"{label} exceeds its item limit.")
    canonical = tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))
    if len({item.casefold() for item in canonical}) != len(canonical):
        raise ValueError(f"{label} contains duplicate values.")
    return canonical


@dataclass(frozen=True)
class IntentValue:
    value: str
    provenance: IntentProvenance
    confidence: Confidence
    evidence: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        value: str,
        provenance: IntentProvenance | str,
        confidence: Confidence | str,
        evidence: Iterable[str],
        original_user_request: str,
        maximum: int = 4_000,
    ) -> IntentValue:
        normalized = _validate_text(value, "intent value", maximum=maximum)
        try:
            source = IntentProvenance(provenance)
            certainty = Confidence(confidence)
        except (TypeError, ValueError) as error:
            raise ValueError("Intent provenance or confidence is unsupported.") from error
        citations = _canonical_texts(evidence, "intent evidence", maximum=2_000)
        if source in {IntentProvenance.EXPLICIT, IntentProvenance.DERIVED} and not citations:
            raise ValueError("Explicit and derived values require source evidence.")
        if source is IntentProvenance.UNRESOLVED:
            raise ValueError("Unresolved information belongs in clarification requirements.")
        compact_request = " ".join(original_user_request.split())
        for citation in citations:
            if citation not in original_user_request and " ".join(citation.split()) not in compact_request:
                raise ValueError("Intent evidence must quote the unchanged original request.")
        return cls(normalized, source, certainty, citations)

    @classmethod
    def from_dict(cls, value: Any, *, original_user_request: str) -> IntentValue:
        value = _require_exact_dict(
            value, {"value", "provenance", "confidence", "evidence"}, "Intent value"
        )
        if not isinstance(value["evidence"], list):
            raise ValueError("Intent evidence must be a JSON array.")
        return cls.create(original_user_request=original_user_request, **value)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence.value,
            "evidence": list(self.evidence),
            "provenance": self.provenance.value,
            "value": self.value,
        }


@dataclass(frozen=True)
class ClarificationRequirement:
    requirement: str
    question: str
    blocking: bool
    evidence: tuple[str, ...] = ()
    provenance: IntentProvenance = IntentProvenance.UNRESOLVED

    @classmethod
    def create(
        cls,
        *,
        requirement: str,
        question: str,
        blocking: bool,
        evidence: Iterable[str] = (),
        original_user_request: str,
    ) -> ClarificationRequirement:
        key = _validate_identifier(requirement, "clarification requirement")
        prompt = _validate_text(question, "clarification question", maximum=1_000)
        if type(blocking) is not bool:
            raise ValueError("Clarification blocking must be a boolean.")
        citations = _canonical_texts(evidence, "clarification evidence", maximum=2_000)
        compact_request = " ".join(original_user_request.split())
        for citation in citations:
            if citation not in original_user_request and " ".join(citation.split()) not in compact_request:
                raise ValueError("Clarification evidence must quote the unchanged original request.")
        return cls(key, prompt, blocking, citations)

    @classmethod
    def from_dict(cls, value: Any, *, original_user_request: str) -> ClarificationRequirement:
        value = _require_exact_dict(
            value,
            {"requirement", "question", "blocking", "evidence", "provenance"},
            "Clarification requirement",
        )
        if value["provenance"] != IntentProvenance.UNRESOLVED.value:
            raise ValueError("Clarification requirements must have unresolved provenance.")
        if not isinstance(value["evidence"], list):
            raise ValueError("Clarification evidence must be a JSON array.")
        return cls.create(
            requirement=value["requirement"],
            question=value["question"],
            blocking=value["blocking"],
            evidence=value["evidence"],
            original_user_request=original_user_request,
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.blocking,
            "evidence": list(self.evidence),
            "provenance": self.provenance.value,
            "question": self.question,
            "requirement": self.requirement,
        }


@dataclass(frozen=True)
class ReadinessEvaluation:
    ready_for_plan: bool
    blocking_requirements: tuple[str, ...]

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "blocking_requirements": list(self.blocking_requirements),
            "ready_for_plan": self.ready_for_plan,
        }


_SCALAR_FIELDS = (
    "proposed_project_name",
    "project_type",
    "product_description",
    "primary_goal",
)
_COLLECTION_FIELDS = (
    "target_users",
    "requested_features",
    "platform_targets",
    "authentication_requirements",
    "integration_requirements",
    "deployment_requirements",
    "explicit_constraints",
    "non_functional_requirements",
    "technology_preferences",
    "assumptions",
)
_READINESS_REQUIRED = (
    "proposed_project_name",
    "project_type",
    "product_description",
    "target_users",
    "primary_goal",
    "requested_features",
    "platform_targets",
    "authentication_requirements",
    "integration_requirements",
    "deployment_requirements",
)


def _canonical_intent_values(
    values: Iterable[IntentValue], label: str, *, allow_assumptions: bool = False
) -> tuple[IntentValue, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a collection of intent values.")
    try:
        result = tuple(values)
    except TypeError as error:
        raise ValueError(f"{label} must be a collection of intent values.") from error
    if len(result) > MAX_COLLECTION_ITEMS or any(not isinstance(item, IntentValue) for item in result):
        raise ValueError(f"{label} contains invalid or excessive values.")
    permitted = {IntentProvenance.ASSUMED} if allow_assumptions else {
        IntentProvenance.EXPLICIT,
        IntentProvenance.DERIVED,
    }
    if any(item.provenance not in permitted for item in result):
        raise ValueError(f"{label} contains provenance that is not permitted for this field.")
    ordered = tuple(sorted(result, key=lambda item: (item.value.casefold(), item.value)))
    if len({item.value.casefold() for item in ordered}) != len(ordered):
        raise ValueError(f"{label} contains duplicate normalized values.")
    return ordered


@dataclass(frozen=True)
class IdeaIntake:
    original_user_request: str
    proposed_project_name: IntentValue | None
    project_type: IntentValue | None
    product_description: IntentValue | None
    target_users: tuple[IntentValue, ...]
    primary_goal: IntentValue | None
    requested_features: tuple[IntentValue, ...]
    platform_targets: tuple[IntentValue, ...]
    authentication_requirements: tuple[IntentValue, ...]
    integration_requirements: tuple[IntentValue, ...]
    deployment_requirements: tuple[IntentValue, ...]
    explicit_constraints: tuple[IntentValue, ...]
    non_functional_requirements: tuple[IntentValue, ...]
    technology_preferences: tuple[IntentValue, ...]
    unresolved_requirements: tuple[ClarificationRequirement, ...]
    assumptions: tuple[IntentValue, ...]
    readiness: ReadinessEvaluation
    schema: str = ARCADEV_IDEA_INTAKE_SCHEMA
    schema_version: int = ARCADEV_IDEA_INTAKE_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        original_user_request: str,
        proposed_project_name: IntentValue | None = None,
        project_type: IntentValue | None = None,
        product_description: IntentValue | None = None,
        target_users: Iterable[IntentValue] = (),
        primary_goal: IntentValue | None = None,
        requested_features: Iterable[IntentValue] = (),
        platform_targets: Iterable[IntentValue] = (),
        authentication_requirements: Iterable[IntentValue] = (),
        integration_requirements: Iterable[IntentValue] = (),
        deployment_requirements: Iterable[IntentValue] = (),
        explicit_constraints: Iterable[IntentValue] = (),
        non_functional_requirements: Iterable[IntentValue] = (),
        technology_preferences: Iterable[IntentValue] = (),
        unresolved_requirements: Iterable[ClarificationRequirement] = (),
        assumptions: Iterable[IntentValue] = (),
    ) -> IdeaIntake:
        request = _validate_text(
            original_user_request,
            "original_user_request",
            maximum=MAX_REQUEST_LENGTH,
            preserve=True,
        )
        scalars = {
            "proposed_project_name": proposed_project_name,
            "project_type": project_type,
            "product_description": product_description,
            "primary_goal": primary_goal,
        }
        for label, value in scalars.items():
            if value is not None and not isinstance(value, IntentValue):
                raise ValueError(f"{label} must be a validated intent value or null.")
            if value is not None and value.provenance not in {
                IntentProvenance.EXPLICIT,
                IntentProvenance.DERIVED,
            }:
                raise ValueError(f"{label} cannot silently promote an assumption.")
            if value is not None:
                IntentValue.create(
                    **value.canonical_dict(), original_user_request=request
                )
        if project_type is not None:
            _validate_identifier(project_type.value, "project_type")

        collections = {
            "target_users": _canonical_intent_values(target_users, "target_users"),
            "requested_features": _canonical_intent_values(requested_features, "requested_features"),
            "platform_targets": _canonical_intent_values(platform_targets, "platform_targets"),
            "authentication_requirements": _canonical_intent_values(
                authentication_requirements, "authentication_requirements"
            ),
            "integration_requirements": _canonical_intent_values(
                integration_requirements, "integration_requirements"
            ),
            "deployment_requirements": _canonical_intent_values(
                deployment_requirements, "deployment_requirements"
            ),
            "explicit_constraints": _canonical_intent_values(explicit_constraints, "explicit_constraints"),
            "non_functional_requirements": _canonical_intent_values(
                non_functional_requirements, "non_functional_requirements"
            ),
            "technology_preferences": _canonical_intent_values(
                technology_preferences, "technology_preferences"
            ),
            "assumptions": _canonical_intent_values(
                assumptions, "assumptions", allow_assumptions=True
            ),
        }
        for values in collections.values():
            for item in values:
                IntentValue.create(**item.canonical_dict(), original_user_request=request)
        try:
            clarifications = tuple(unresolved_requirements)
        except TypeError as error:
            raise ValueError("unresolved_requirements must be a collection.") from error
        if len(clarifications) > MAX_COLLECTION_ITEMS or any(
            not isinstance(item, ClarificationRequirement) for item in clarifications
        ):
            raise ValueError("unresolved_requirements contains invalid or excessive values.")
        clarifications = tuple(
            sorted(clarifications, key=lambda item: (item.requirement, item.question.casefold(), item.question))
        )
        for item in clarifications:
            ClarificationRequirement.create(
                requirement=item.requirement,
                question=item.question,
                blocking=item.blocking,
                evidence=item.evidence,
                original_user_request=request,
            )
        clarification_keys = [(item.requirement, item.question.casefold()) for item in clarifications]
        if len(set(clarification_keys)) != len(clarification_keys):
            raise ValueError("unresolved_requirements contains duplicate values.")

        missing = []
        for field in _READINESS_REQUIRED:
            value = scalars.get(field, collections.get(field))
            if value is None or value == ():
                missing.append(field)
        blocking = set(missing)
        blocking.update(item.requirement for item in clarifications if item.blocking)
        if collections["assumptions"]:
            blocking.add("assumptions")
        blocking_requirements = tuple(sorted(blocking))
        readiness = ReadinessEvaluation(not blocking_requirements, blocking_requirements)
        return cls(
            original_user_request=request,
            unresolved_requirements=clarifications,
            readiness=readiness,
            **scalars,
            **collections,
        )

    @classmethod
    def from_dict(cls, value: Any) -> IdeaIntake:
        keys = {
            "schema",
            "schema_version",
            "original_user_request",
            *_SCALAR_FIELDS,
            *_COLLECTION_FIELDS,
            "unresolved_requirements",
            "readiness",
        }
        value = _require_exact_dict(value, keys, "Idea intake")
        if value["schema"] != ARCADEV_IDEA_INTAKE_SCHEMA:
            raise ValueError("Idea intake schema is unsupported.")
        if type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_IDEA_INTAKE_SCHEMA_VERSION:
            raise ValueError("Idea intake schema version is unsupported.")
        request = _validate_text(
            value["original_user_request"],
            "original_user_request",
            maximum=MAX_REQUEST_LENGTH,
            preserve=True,
        )
        scalar_values = {}
        for field in _SCALAR_FIELDS:
            raw = value[field]
            scalar_values[field] = None if raw is None else IntentValue.from_dict(
                raw, original_user_request=request
            )
        collection_values = {}
        for field in _COLLECTION_FIELDS:
            raw = value[field]
            if not isinstance(raw, list):
                raise ValueError(f"{field} must be a JSON array.")
            collection_values[field] = [
                IntentValue.from_dict(item, original_user_request=request) for item in raw
            ]
        raw_clarifications = value["unresolved_requirements"]
        if not isinstance(raw_clarifications, list):
            raise ValueError("unresolved_requirements must be a JSON array.")
        result = cls.create(
            original_user_request=request,
            unresolved_requirements=[
                ClarificationRequirement.from_dict(item, original_user_request=request)
                for item in raw_clarifications
            ],
            **scalar_values,
            **collection_values,
        )
        expected_readiness = _require_exact_dict(
            value["readiness"], {"ready_for_plan", "blocking_requirements"}, "Readiness evaluation"
        )
        if type(expected_readiness["ready_for_plan"]) is not bool:
            raise ValueError("ready_for_plan must be a boolean.")
        if not isinstance(expected_readiness["blocking_requirements"], list) or any(
            not isinstance(item, str) for item in expected_readiness["blocking_requirements"]
        ):
            raise ValueError("blocking_requirements must be a JSON array of strings.")
        if expected_readiness != result.readiness.canonical_dict():
            raise ValueError("Idea readiness must match deterministic evaluation.")
        return result

    @classmethod
    def from_json(cls, text: str) -> IdeaIntake:
        if not isinstance(text, str):
            raise ValueError("Idea intake must be JSON text.")
        try:
            size = len(text.encode("utf-8"))
        except UnicodeError as error:
            raise ValueError("Idea intake is not valid Unicode text.") from error
        if size > MAX_IDEA_INTAKE_BYTES:
            raise ValueError("Idea intake exceeds the safety limit.")
        try:
            value = json.loads(text, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as error:
            raise ValueError("Idea intake is not valid JSON.") from error
        return cls.from_dict(value)

    def canonical_dict(self) -> dict[str, Any]:
        result = {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "original_user_request": self.original_user_request,
            "unresolved_requirements": [item.canonical_dict() for item in self.unresolved_requirements],
            "readiness": self.readiness.canonical_dict(),
        }
        for field in _SCALAR_FIELDS:
            item = getattr(self, field)
            result[field] = None if item is None else item.canonical_dict()
        for field in _COLLECTION_FIELDS:
            result[field] = [item.canonical_dict() for item in getattr(self, field)]
        return result

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_dict())

    def to_project(self, *, metadata: ProjectMetadata) -> ArcaDevProject:
        """Convert a ready intake through the certified ArcaDev 1.1 public contract."""

        validated = IdeaIntake.from_dict(self.canonical_dict())
        if not validated.readiness.ready_for_plan:
            raise ValueError("Only a ready IDEA intake can become an ArcaDev project.")
        if not isinstance(metadata, ProjectMetadata):
            raise ValueError("Project metadata must be a validated ArcaDev value.")
        constraints = [item.value for item in validated.explicit_constraints]
        constraints.extend(
            f"Non-functional requirement: {item.value}"
            for item in validated.non_functional_requirements
        )
        constraints.extend(
            f"Technology preference: {item.value}" for item in validated.technology_preferences
        )
        specification = ProjectSpecification.create(
            project_type=validated.project_type.value,
            target_users=[item.value for item in validated.target_users],
            primary_goal=validated.primary_goal.value,
            requested_features=[item.value for item in validated.requested_features],
            platform_targets=[item.value for item in validated.platform_targets],
            authentication_requirements=[
                item.value for item in validated.authentication_requirements
            ],
            integration_requirements=[item.value for item in validated.integration_requirements],
            deployment_targets=[item.value for item in validated.deployment_requirements],
            user_constraints=constraints,
        )
        return ArcaDevProject.create(
            project_name=validated.proposed_project_name.value,
            project_description=validated.product_description.value,
            original_user_request=validated.original_user_request,
            specification=specification,
            metadata=metadata,
            project_status=ProjectStatus.READY,
            current_build_stage=BuildStage.IDEA,
        )


def validate_candidate(original_user_request: str, candidate: Mapping[str, Any] | str) -> IdeaIntake:
    """Validate untrusted adapter output without trusting provider-specific metadata."""

    request = _validate_text(
        original_user_request, "original_user_request", maximum=MAX_REQUEST_LENGTH, preserve=True
    )
    if isinstance(candidate, str):
        result = IdeaIntake.from_json(candidate)
    elif isinstance(candidate, Mapping):
        result = IdeaIntake.from_dict(dict(candidate))
    else:
        raise ValueError("Idea candidate must be a JSON object or JSON text.")
    if result.original_user_request != request:
        raise ValueError("Idea candidate does not preserve the supplied original request.")
    return result


def _match_evidence(pattern: str, text: str, *, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return None if match is None else match.group(0)


def _intent(
    value: str,
    evidence: str,
    request: str,
    *,
    provenance: IntentProvenance = IntentProvenance.DERIVED,
    confidence: Confidence = Confidence.HIGH,
    maximum: int = 4_000,
) -> IntentValue:
    return IntentValue.create(
        value=value,
        provenance=provenance,
        confidence=confidence,
        evidence=[evidence],
        original_user_request=request,
        maximum=maximum,
    )


def _split_items(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip(" ,.")
    if not cleaned:
        return []
    if "," in cleaned:
        cleaned = re.sub(r",\s*(?:and|or)\s+", ",", cleaned, flags=re.IGNORECASE)
        return [item.strip(" ,.") for item in cleaned.split(",") if item.strip(" ,.")]
    return [item.strip(" ,.") for item in re.split(r"\s+and\s+", cleaned, flags=re.IGNORECASE) if item.strip(" ,.")]


_QUESTIONS = {
    "proposed_project_name": "What should the project be called?",
    "project_type": "What type of software should this be?",
    "product_description": "What product or application should be built?",
    "target_users": "Who are the target users?",
    "primary_goal": "What primary outcome should the product achieve?",
    "requested_features": "Which capabilities are required for the first version?",
    "platform_targets": "Which platforms must the product support?",
    "authentication_requirements": "What authentication is required, or should there be none?",
    "integration_requirements": "Which external integrations are required, or are there none?",
    "deployment_requirements": "Where or how should the product be deployed?",
}


def normalize_idea(original_user_request: str) -> IdeaIntake:
    """Apply conservative, deterministic rules to natural-language IDEA input."""

    request = _validate_text(
        original_user_request, "original_user_request", maximum=MAX_REQUEST_LENGTH, preserve=True
    )
    compact = " ".join(request.split())

    name = None
    assumptions: list[IntentValue] = []
    clarifications: list[ClarificationRequirement] = []
    name_match = re.search(
        r"\b(?:called|named)\s+[\"']?([A-Za-z0-9][A-Za-z0-9&'_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9&'_-]*){0,7})",
        compact,
        re.IGNORECASE,
    )
    if name_match:
        raw_name = re.split(r"\s+(?:for|that|which|where|with|to)\b", name_match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        name = _intent(raw_name.strip(" \"'.,"), name_match.group(0), request, provenance=IntentProvenance.EXPLICIT)
    else:
        inferred_name = re.search(
            r"\b(?:[Bb]uild|[Cc]reate|[Mm]ake)(?:\s+me)?\s+an?\s+([A-Z][A-Za-z0-9&'_-]*(?:\s+[A-Z][A-Za-z0-9&'_-]*){0,5})\s+(?:where|that|which|for|with)\b",
            compact,
        )
        if inferred_name:
            evidence = inferred_name.group(0)
            candidate_name = inferred_name.group(1)
            name = _intent(candidate_name, evidence, request, confidence=Confidence.MEDIUM)
            assumptions.append(
                _intent(
                    f"Treat {candidate_name} as the proposed project name.",
                    evidence,
                    request,
                    provenance=IntentProvenance.ASSUMED,
                    confidence=Confidence.MEDIUM,
                )
            )
            clarifications.append(
                ClarificationRequirement.create(
                    requirement="proposed_project_name",
                    question=f"Should the project be named {candidate_name}?",
                    blocking=True,
                    evidence=[evidence],
                    original_user_request=request,
                )
            )

    type_patterns = (
        (r"\bweb\s+(?:app|application)\b|\bwebsite\b", "web_application"),
        (r"\bmobile\s+(?:app|application)\b", "mobile_application"),
        (r"\bdesktop\s+(?:app|application)\b", "desktop_application"),
        (r"\b(?:REST|GraphQL|web)\s+API\b|\bAPI\s+(?:service|application)\b", "api_service"),
        (r"\bcommand[- ]line\s+(?:tool|application)\b|\bCLI\b", "command_line_application"),
    )
    project_type = None
    for pattern, normalized in type_patterns:
        evidence = _match_evidence(pattern, request)
        if evidence:
            project_type = _intent(normalized, evidence, request)
            break

    description_text = compact[:8_000].rstrip()
    description = _intent(
        description_text,
        description_text,
        request,
        confidence=Confidence.HIGH,
        maximum=8_000,
    )

    target_users: list[IntentValue] = []
    user_match = re.search(
        r"\bfor\s+(.+?)(?=\s+to\s+|\s+who\s+|\s+that\s+|\s+where\s+|[,.;]|$)", compact, re.IGNORECASE
    )
    if not user_match:
        user_match = re.search(r"\bwhere\s+(.+?)\s+can\s+", compact, re.IGNORECASE)
    if user_match:
        phrase = user_match.group(1).strip()
        for item in _split_items(phrase):
            target_users.append(_intent(item, user_match.group(0), request, provenance=IntentProvenance.EXPLICIT))

    goal = None
    goal_match = re.search(
        r"\b(?:for\s+.+?\s+to|where\s+.+?\s+can|so\s+that\s+.+?\s+can)\s+(.+?)(?=[.;]|\s+(?:include|including|with|using|deploy|host)\b|$)",
        compact,
        re.IGNORECASE,
    )
    if goal_match:
        goal_text = goal_match.group(1).strip(" ,.")
        goal = _intent(goal_text[0].upper() + goal_text[1:], goal_match.group(0), request)

    requested_features: list[IntentValue] = []
    feature_matches = list(
        re.finditer(
            r"\b(?:include|including|features?(?:\s+include)?|capabilities?(?:\s+include)?)\s*:?\s*(.+?)(?=[.;]|$)",
            compact,
            re.IGNORECASE,
        )
    )
    if feature_matches:
        for match in feature_matches:
            for item in _split_items(match.group(1)):
                item = re.sub(r"^(?:a|an|the)\s+", "", item, flags=re.IGNORECASE)
                requested_features.append(
                    _intent(item[0].upper() + item[1:], match.group(0), request, provenance=IntentProvenance.EXPLICIT)
                )
    elif goal_match:
        for item in _split_items(goal_match.group(1)):
            requested_features.append(_intent(item[0].upper() + item[1:], goal_match.group(0), request))

    platform_targets: list[IntentValue] = []
    for pattern, normalized in (
        (r"\biOS\b", "iOS"),
        (r"\bAndroid\b", "Android"),
        (r"\bmobile\s+(?:app|application)\b", "Mobile"),
        (r"\bweb\s+(?:app|application)\b|\bwebsite\b|\bbrowser\b", "Web"),
        (r"\bdesktop\b", "Desktop"),
    ):
        evidence = _match_evidence(pattern, request)
        if evidence and normalized.casefold() not in {item.value.casefold() for item in platform_targets}:
            platform_targets.append(_intent(normalized, evidence, request))

    authentication: list[IntentValue] = []
    auth_patterns = (
        (r"\b(?:no|without)\s+(?:login|sign[- ]?in|authentication)\b", "No authentication required"),
        (r"\b(?:SSO|single sign-on)\b", "Single sign-on"),
        (r"\b(?:MFA|multi-factor authentication|two-factor authentication|2FA)\b", "Multi-factor authentication"),
        (r"\bemail(?:\s+and|/)?\s+password\s+(?:login|authentication)\b", "Email and password authentication"),
        (r"\bsocial\s+(?:login|sign[- ]?in)\b", "Social sign-in"),
    )
    for pattern, normalized in auth_patterns:
        evidence = _match_evidence(pattern, request)
        if evidence:
            authentication.append(_intent(normalized, evidence, request))

    integrations: list[IntentValue] = []
    no_integration = _match_evidence(r"\bno\s+(?:external\s+)?integrations?\b", request)
    if no_integration:
        integrations.append(_intent("No external integrations required", no_integration, request))
    for match in re.finditer(
        r"\b(?:integrate|integrates|integrating)\s+with\s+([A-Za-z0-9][A-Za-z0-9 .+_-]{0,60}?)(?=[,.;]|\s+and\s+(?:deploy|host|meet|support|use)\b|$)",
        request,
        re.IGNORECASE,
    ):
        for item in _split_items(match.group(1)):
            integrations.append(_intent(item, match.group(0), request, provenance=IntentProvenance.EXPLICIT))
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9.+_-]*(?:\s+[A-Z][A-Za-z0-9.+_-]*){0,3})\s+integration\b",
        request,
    ):
        item = match.group(1).strip()
        if item.casefold() not in {value.value.casefold() for value in integrations}:
            integrations.append(_intent(item, match.group(0), request, provenance=IntentProvenance.EXPLICIT))

    deployments: list[IntentValue] = []
    no_deployment = _match_evidence(r"\bno\s+(?:deployment|hosting)\s+(?:requirement|preference)s?\b", request)
    if no_deployment:
        deployments.append(_intent("No deployment preference", no_deployment, request))
    deployment_matches = re.finditer(
        r"\b(?:deploy|deployed|host|hosted|publish|published)\s+(?:it\s+)?(?:on|to|in|via)\s+(.+?)(?=[.;]|$)",
        request,
        re.IGNORECASE,
    )
    for match in deployment_matches:
        for item in _split_items(match.group(1)):
            deployments.append(_intent(item, match.group(0), request, provenance=IntentProvenance.EXPLICIT))

    constraints: list[IntentValue] = []
    for match in re.finditer(r"(?:^|[.;]\s*)([^.;]*\b(?:must|must not|required to|cannot|budget)\b[^.;]*)", compact, re.IGNORECASE):
        phrase = match.group(1).strip()
        constraints.append(_intent(phrase, phrase, request, provenance=IntentProvenance.EXPLICIT))

    non_functional: list[IntentValue] = []
    for pattern, normalized in (
        (r"\bWCAG\s+[0-9.]+(?:\s+AA|\s+AAA)?\b", "Accessibility: {evidence}"),
        (r"\b(?:work|works|available)\s+offline\b", "Offline operation"),
        (r"\b(?:response|latency)\s+(?:under|below|within)\s+[^,.;]+", "Performance: {evidence}"),
        (r"\b(?:highly available|high availability)\b", "High availability"),
    ):
        evidence = _match_evidence(pattern, request)
        if evidence:
            non_functional.append(_intent(normalized.format(evidence=evidence), evidence, request))

    technologies: list[IntentValue] = []
    for match in re.finditer(
        r"\b(?:use|using|built with|prefer|preference for)\s+(Python|Django|FastAPI|Flask|JavaScript|TypeScript|React|Vue|Angular|PostgreSQL|MySQL|SQLite|MongoDB|Redis|AWS|Azure|GCP)\b",
        request,
        re.IGNORECASE,
    ):
        technologies.append(_intent(match.group(1), match.group(0), request, provenance=IntentProvenance.EXPLICIT))

    current = {
        "proposed_project_name": name,
        "project_type": project_type,
        "product_description": description,
        "target_users": target_users,
        "primary_goal": goal,
        "requested_features": requested_features,
        "platform_targets": platform_targets,
        "authentication_requirements": authentication,
        "integration_requirements": integrations,
        "deployment_requirements": deployments,
    }
    existing_clarification_keys = {item.requirement for item in clarifications}
    for field in _READINESS_REQUIRED:
        value = current[field]
        if (value is None or value == []) and field not in existing_clarification_keys:
            clarifications.append(
                ClarificationRequirement.create(
                    requirement=field,
                    question=_QUESTIONS[field],
                    blocking=True,
                    original_user_request=request,
                )
            )

    if authentication and any(item.value == "No authentication required" for item in authentication) and len(authentication) > 1:
        clarifications.append(
            ClarificationRequirement.create(
                requirement="authentication_requirements",
                question="Should the product have authentication, or explicitly have none?",
                blocking=True,
                evidence=[item.evidence[0] for item in authentication],
                original_user_request=request,
            )
        )
    if integrations and any(item.value == "No external integrations required" for item in integrations) and len(integrations) > 1:
        clarifications.append(
            ClarificationRequirement.create(
                requirement="integration_requirements",
                question="Are external integrations required, or explicitly excluded?",
                blocking=True,
                evidence=[item.evidence[0] for item in integrations],
                original_user_request=request,
            )
        )

    return IdeaIntake.create(
        original_user_request=request,
        proposed_project_name=name,
        project_type=project_type,
        product_description=description,
        target_users=target_users,
        primary_goal=goal,
        requested_features=requested_features,
        platform_targets=platform_targets,
        authentication_requirements=authentication,
        integration_requirements=integrations,
        deployment_requirements=deployments,
        explicit_constraints=constraints,
        non_functional_requirements=non_functional,
        technology_preferences=technologies,
        unresolved_requirements=clarifications,
        assumptions=assumptions,
    )
