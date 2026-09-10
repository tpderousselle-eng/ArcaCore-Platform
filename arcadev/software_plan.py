"""Canonical, provider-neutral ArcaDev software planning contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable
import unicodedata

from .idea_plan_handoff import IdeaPlanHandoff, validate_idea_plan_handoff
from .project import BuildStage


ARCADEV_SOFTWARE_PLAN_SCHEMA = "arcadev.software_plan"
ARCADEV_SOFTWARE_PLAN_SCHEMA_VERSION = 1
MAX_SOFTWARE_PLAN_BYTES = 5_000_000
MAX_PLAN_ITEMS = 256
MAX_PLAN_TEXT = 8_000
_SECRET = re.compile(r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)\s*(?:=|:)\s*[^\s,;]{4,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class PlanProvenance(str, Enum):
    APPROVED_IDEA = "approved_idea"
    DERIVED = "deterministic_planning_derivation"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Software plan contains duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _text(value: Any, label: str, maximum: int = MAX_PLAN_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = " ".join(value.split())
    if not value or len(value) > maximum:
        raise ValueError(f"{label} is empty or exceeds its size limit.")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{label} is invalid Unicode.") from error
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET.search(value) or _PRIVATE_KEY.search(value):
        raise ValueError(f"{label} appears to contain a credential or secret value.")
    return value


def _approved_values(handoff: IdeaPlanHandoff) -> set[str]:
    intake = handoff.snapshot.intake
    values = {intake.original_user_request}
    for field in ("proposed_project_name", "project_type", "product_description", "primary_goal"):
        item = getattr(intake, field)
        if item is not None:
            values.add(item.value)
    for field in (
        "target_users", "requested_features", "platform_targets", "authentication_requirements",
        "integration_requirements", "deployment_requirements", "explicit_constraints",
        "non_functional_requirements", "technology_preferences",
    ):
        values.update(item.value for item in getattr(intake, field))
    return values


@dataclass(frozen=True)
class PlanItem:
    value: str
    provenance: PlanProvenance
    source_requirements: tuple[str, ...]

    @classmethod
    def create(cls, value: str, provenance: PlanProvenance | str, source_requirements: Iterable[str], *, handoff: IdeaPlanHandoff) -> "PlanItem":
        value = _text(value, "plan item")
        try:
            provenance = PlanProvenance(provenance)
            sources = tuple(sorted((_text(item, "source requirement") for item in source_requirements), key=lambda item: (item.casefold(), item)))
        except (TypeError, ValueError) as error:
            raise ValueError("Plan item provenance or sources are invalid.") from error
        if not sources or len(sources) > MAX_PLAN_ITEMS or len({item.casefold() for item in sources}) != len(sources):
            raise ValueError("Plan item sources are empty, duplicate, or excessive.")
        approved = _approved_values(handoff)
        if any(source not in approved for source in sources):
            raise ValueError("Plan item source is not present in the approved IDEA.")
        if provenance is PlanProvenance.APPROVED_IDEA and value not in approved:
            raise ValueError("Approved-IDEA plan item is not present in the frozen IDEA.")
        return cls(value, provenance, sources)

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "PlanItem":
        value = _exact(value, {"value", "provenance", "source_requirements"}, "Plan item")
        if not isinstance(value["source_requirements"], list):
            raise ValueError("Plan item sources must be an array.")
        return cls.create(**value, handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {"provenance": self.provenance.value, "source_requirements": list(self.source_requirements), "value": self.value}


def _items(values: Iterable[PlanItem], label: str, handoff: IdeaPlanHandoff, *, required: bool = False) -> tuple[PlanItem, ...]:
    try:
        values = tuple(values)
    except TypeError as error:
        raise ValueError(f"{label} must be a collection.") from error
    if required and not values:
        raise ValueError(f"{label} must not be empty.")
    if len(values) > MAX_PLAN_ITEMS or any(not isinstance(item, PlanItem) for item in values):
        raise ValueError(f"{label} is invalid or excessive.")
    values = tuple(PlanItem.from_dict(item.canonical_dict(), handoff=handoff) for item in values)
    values = tuple(sorted(values, key=lambda item: (item.value.casefold(), item.value, item.provenance.value)))
    if len({item.value.casefold() for item in values}) != len(values):
        raise ValueError(f"{label} contains duplicate canonical values.")
    return values


@dataclass(frozen=True)
class PlanScope:
    in_scope: tuple[PlanItem, ...]
    out_of_scope: tuple[PlanItem, ...]

    @classmethod
    def create(cls, in_scope: Iterable[PlanItem], out_of_scope: Iterable[PlanItem], *, handoff: IdeaPlanHandoff) -> "PlanScope":
        inside = _items(in_scope, "in_scope", handoff, required=True)
        outside = _items(out_of_scope, "out_of_scope", handoff)
        overlap = {item.value.casefold() for item in inside} & {item.value.casefold() for item in outside}
        if overlap:
            raise ValueError("Plan scope contains the same item in-scope and out-of-scope.")
        return cls(inside, outside)

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "PlanScope":
        value = _exact(value, {"in_scope", "out_of_scope"}, "Plan scope")
        if not isinstance(value["in_scope"], list) or not isinstance(value["out_of_scope"], list):
            raise ValueError("Plan scope values must be arrays.")
        return cls.create(
            [PlanItem.from_dict(item, handoff=handoff) for item in value["in_scope"]],
            [PlanItem.from_dict(item, handoff=handoff) for item in value["out_of_scope"]],
            handoff=handoff,
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {"in_scope": [item.canonical_dict() for item in self.in_scope], "out_of_scope": [item.canonical_dict() for item in self.out_of_scope]}


@dataclass(frozen=True)
class UserJourney:
    name: str
    steps: tuple[PlanItem, ...]

    @classmethod
    def create(cls, name: str, steps: Iterable[PlanItem], *, handoff: IdeaPlanHandoff) -> "UserJourney":
        return cls(_text(name, "journey name", 240), _items(steps, "journey steps", handoff, required=True))

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "UserJourney":
        value = _exact(value, {"name", "steps"}, "User journey")
        if not isinstance(value["steps"], list):
            raise ValueError("User journey steps must be an array.")
        return cls.create(value["name"], [PlanItem.from_dict(item, handoff=handoff) for item in value["steps"]], handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {"name": self.name, "steps": [item.canonical_dict() for item in self.steps]}


@dataclass(frozen=True)
class Milestone:
    name: str
    deliverables: tuple[PlanItem, ...]

    @classmethod
    def create(cls, name: str, deliverables: Iterable[PlanItem], *, handoff: IdeaPlanHandoff) -> "Milestone":
        return cls(_text(name, "milestone name", 240), _items(deliverables, "milestone deliverables", handoff, required=True))

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "Milestone":
        value = _exact(value, {"name", "deliverables"}, "Milestone")
        if not isinstance(value["deliverables"], list):
            raise ValueError("Milestone deliverables must be an array.")
        return cls.create(value["name"], [PlanItem.from_dict(item, handoff=handoff) for item in value["deliverables"]], handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {"deliverables": [item.canonical_dict() for item in self.deliverables], "name": self.name}


@dataclass(frozen=True)
class PlanRisk:
    risk: PlanItem
    mitigation: PlanItem

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "PlanRisk":
        value = _exact(value, {"risk", "mitigation"}, "Plan risk")
        return cls(PlanItem.from_dict(value["risk"], handoff=handoff), PlanItem.from_dict(value["mitigation"], handoff=handoff))

    def canonical_dict(self) -> dict[str, Any]:
        return {"mitigation": self.mitigation.canonical_dict(), "risk": self.risk.canonical_dict()}


@dataclass(frozen=True)
class PlanningQuestion:
    question: str
    blocking: bool
    source_requirements: tuple[str, ...]

    @classmethod
    def create(cls, question: str, blocking: bool, source_requirements: Iterable[str], *, handoff: IdeaPlanHandoff) -> "PlanningQuestion":
        question = _text(question, "planning question", 2_000)
        if type(blocking) is not bool:
            raise ValueError("Planning question blocking must be boolean.")
        sources = tuple(sorted((_text(item, "question source") for item in source_requirements), key=str.casefold))
        if not sources or len({item.casefold() for item in sources}) != len(sources) or any(item not in _approved_values(handoff) for item in sources):
            raise ValueError("Planning question sources must be unique approved IDEA values.")
        return cls(question, blocking, sources)

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "PlanningQuestion":
        value = _exact(value, {"question", "blocking", "source_requirements"}, "Planning question")
        if not isinstance(value["source_requirements"], list):
            raise ValueError("Planning question sources must be an array.")
        return cls.create(**value, handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {"blocking": self.blocking, "question": self.question, "source_requirements": list(self.source_requirements)}


@dataclass(frozen=True)
class PlanReadiness:
    ready_for_architecture: bool
    blocking_reasons: tuple[str, ...]

    def canonical_dict(self) -> dict[str, Any]:
        return {"blocking_reasons": list(self.blocking_reasons), "ready_for_architecture": self.ready_for_architecture}


@dataclass(frozen=True)
class SoftwarePlan:
    plan_id: str
    handoff_id: str
    project_id: str
    product_objective: PlanItem
    user_problem_statement: PlanItem
    scope: PlanScope
    in_scope_capabilities: tuple[PlanItem, ...]
    user_roles: tuple[PlanItem, ...]
    user_journeys: tuple[UserJourney, ...]
    functional_requirements: tuple[PlanItem, ...]
    non_functional_requirements: tuple[PlanItem, ...]
    milestones: tuple[Milestone, ...]
    dependencies: tuple[PlanItem, ...]
    integrations: tuple[PlanItem, ...]
    assumptions: tuple[PlanItem, ...]
    risks: tuple[PlanRisk, ...]
    open_planning_questions: tuple[PlanningQuestion, ...]
    acceptance_criteria: tuple[PlanItem, ...]
    planning_constraints: tuple[PlanItem, ...]
    readiness: PlanReadiness
    project_stage: BuildStage = BuildStage.PLAN
    schema: str = ARCADEV_SOFTWARE_PLAN_SCHEMA
    schema_version: int = ARCADEV_SOFTWARE_PLAN_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff: IdeaPlanHandoff, product_objective: PlanItem, user_problem_statement: PlanItem,
               scope: PlanScope, in_scope_capabilities=(), user_roles=(), user_journeys=(), functional_requirements=(),
               non_functional_requirements=(), milestones=(), dependencies=(), integrations=(), assumptions=(), risks=(),
               open_planning_questions=(), acceptance_criteria=(), planning_constraints=()) -> "SoftwarePlan":
        handoff = validate_idea_plan_handoff(handoff.canonical_dict()) if isinstance(handoff, IdeaPlanHandoff) else None
        if handoff is None or not handoff.eligible or handoff.resulting_project.current_build_stage is not BuildStage.PLAN:
            raise ValueError("Software plan requires an eligible approved IDEA handoff at PLAN.")
        product_objective = PlanItem.from_dict(product_objective.canonical_dict(), handoff=handoff)
        user_problem_statement = PlanItem.from_dict(user_problem_statement.canonical_dict(), handoff=handoff)
        if not isinstance(scope, PlanScope):
            raise ValueError("Software plan requires a validated scope.")
        scope = PlanScope.from_dict(scope.canonical_dict(), handoff=handoff)
        collections = {
            "in_scope_capabilities": _items(in_scope_capabilities, "in_scope_capabilities", handoff),
            "user_roles": _items(user_roles, "user_roles", handoff),
            "functional_requirements": _items(functional_requirements, "functional_requirements", handoff),
            "non_functional_requirements": _items(non_functional_requirements, "non_functional_requirements", handoff),
            "dependencies": _items(dependencies, "dependencies", handoff),
            "integrations": _items(integrations, "integrations", handoff),
            "assumptions": _items(assumptions, "assumptions", handoff),
            "acceptance_criteria": _items(acceptance_criteria, "acceptance_criteria", handoff),
            "planning_constraints": _items(planning_constraints, "planning_constraints", handoff),
        }
        journeys = tuple(sorted((UserJourney.from_dict(item.canonical_dict(), handoff=handoff) for item in user_journeys), key=lambda item: item.name.casefold()))
        phases = tuple(sorted((Milestone.from_dict(item.canonical_dict(), handoff=handoff) for item in milestones), key=lambda item: item.name.casefold()))
        risk_values = tuple(sorted((PlanRisk.from_dict(item.canonical_dict(), handoff=handoff) for item in risks), key=lambda item: item.risk.value.casefold()))
        questions = tuple(sorted((PlanningQuestion.from_dict(item.canonical_dict(), handoff=handoff) for item in open_planning_questions), key=lambda item: item.question.casefold()))
        for label, values, key in (("user_journeys", journeys, lambda item: item.name.casefold()), ("milestones", phases, lambda item: item.name.casefold()), ("risks", risk_values, lambda item: item.risk.value.casefold()), ("open_planning_questions", questions, lambda item: item.question.casefold())):
            if len(values) > MAX_PLAN_ITEMS or len({key(item) for item in values}) != len(values):
                raise ValueError(f"{label} contains duplicate or excessive values.")
        missing = []
        required = {
            "defined_scope": scope.in_scope,
            "required_capabilities": collections["in_scope_capabilities"],
            "core_workflows": journeys,
            "functional_requirements": collections["functional_requirements"],
            "non_functional_requirements": collections["non_functional_requirements"],
            "milestones": phases,
            "dependencies": collections["dependencies"],
            "risks": risk_values,
            "acceptance_criteria": collections["acceptance_criteria"],
        }
        missing.extend(name for name, values in required.items() if not values)
        if any(item.blocking for item in questions):
            missing.append("blocking_planning_questions")
        readiness = PlanReadiness(not missing, tuple(sorted(missing)))
        provisional = cls("", handoff.handoff_id, handoff.source_project_id, product_objective, user_problem_statement, scope,
            user_journeys=journeys, milestones=phases, risks=risk_values, open_planning_questions=questions,
            readiness=readiness, **collections)
        body = provisional.canonical_dict()
        body.pop("plan_id")
        body.pop("readiness")
        digest = hashlib.sha256(("arcadev-software-plan-identity/v1\0" + _json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_plan_{digest[:32]}", handoff.handoff_id, handoff.source_project_id, product_objective,
            user_problem_statement, scope, user_journeys=journeys, milestones=phases, risks=risk_values,
            open_planning_questions=questions, readiness=readiness, **collections)

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "SoftwarePlan":
        fields = {"plan_id", "handoff_id", "project_id", "product_objective", "user_problem_statement", "scope",
            "in_scope_capabilities", "user_roles", "user_journeys", "functional_requirements", "non_functional_requirements",
            "milestones", "dependencies", "integrations", "assumptions", "risks", "open_planning_questions",
            "acceptance_criteria", "planning_constraints", "readiness", "project_stage", "schema", "schema_version"}
        value = _exact(value, fields, "Software plan")
        if value["schema"] != ARCADEV_SOFTWARE_PLAN_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_SOFTWARE_PLAN_SCHEMA_VERSION:
            raise ValueError("Software plan schema or version is unsupported.")
        if value["handoff_id"] != handoff.handoff_id or value["project_id"] != handoff.source_project_id:
            raise ValueError("Software plan has the wrong approved handoff or project identity.")
        if value["project_stage"] != BuildStage.PLAN.value:
            raise ValueError("Software plan cannot transition beyond PLAN.")
        list_fields = fields - {"plan_id", "handoff_id", "project_id", "product_objective", "user_problem_statement", "scope", "readiness", "project_stage", "schema", "schema_version"}
        if any(not isinstance(value[field], list) for field in list_fields):
            raise ValueError("Software plan collections must be arrays.")
        kwargs = {
            field: [PlanItem.from_dict(item, handoff=handoff) for item in value[field]]
            for field in ("in_scope_capabilities", "user_roles", "functional_requirements", "non_functional_requirements", "dependencies", "integrations", "assumptions", "acceptance_criteria", "planning_constraints")
        }
        kwargs.update({
            "user_journeys": [UserJourney.from_dict(item, handoff=handoff) for item in value["user_journeys"]],
            "milestones": [Milestone.from_dict(item, handoff=handoff) for item in value["milestones"]],
            "risks": [PlanRisk.from_dict(item, handoff=handoff) for item in value["risks"]],
            "open_planning_questions": [PlanningQuestion.from_dict(item, handoff=handoff) for item in value["open_planning_questions"]],
        })
        result = cls.create(handoff=handoff, product_objective=PlanItem.from_dict(value["product_objective"], handoff=handoff),
            user_problem_statement=PlanItem.from_dict(value["user_problem_statement"], handoff=handoff),
            scope=PlanScope.from_dict(value["scope"], handoff=handoff), **kwargs)
        expected_readiness = _exact(value["readiness"], {"ready_for_architecture", "blocking_reasons"}, "Plan readiness")
        if value["plan_id"] != result.plan_id:
            raise ValueError("Software plan identity is forged.")
        if expected_readiness != result.readiness.canonical_dict():
            raise ValueError("Software plan readiness is forged.")
        if value != result.canonical_dict():
            raise ValueError("Software plan serialization is not canonical.")
        return result

    @classmethod
    def from_json(cls, text: str, *, handoff: IdeaPlanHandoff) -> "SoftwarePlan":
        if not isinstance(text, str):
            raise ValueError("Software plan must be JSON text.")
        try:
            if len(text.encode("utf-8")) > MAX_SOFTWARE_PLAN_BYTES:
                raise ValueError("Software plan exceeds the safety limit.")
            value = json.loads(text, object_pairs_hook=_unique)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Software plan is not valid JSON.") from error
        return cls.from_dict(value, handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "acceptance_criteria": [item.canonical_dict() for item in self.acceptance_criteria],
            "assumptions": [item.canonical_dict() for item in self.assumptions],
            "dependencies": [item.canonical_dict() for item in self.dependencies],
            "functional_requirements": [item.canonical_dict() for item in self.functional_requirements],
            "handoff_id": self.handoff_id,
            "in_scope_capabilities": [item.canonical_dict() for item in self.in_scope_capabilities],
            "integrations": [item.canonical_dict() for item in self.integrations],
            "milestones": [item.canonical_dict() for item in self.milestones],
            "non_functional_requirements": [item.canonical_dict() for item in self.non_functional_requirements],
            "open_planning_questions": [item.canonical_dict() for item in self.open_planning_questions],
            "plan_id": self.plan_id,
            "planning_constraints": [item.canonical_dict() for item in self.planning_constraints],
            "product_objective": self.product_objective.canonical_dict(),
            "project_id": self.project_id,
            "project_stage": self.project_stage.value,
            "readiness": self.readiness.canonical_dict(),
            "risks": [item.canonical_dict() for item in self.risks],
            "schema": self.schema,
            "schema_version": self.schema_version,
            "scope": self.scope.canonical_dict(),
            "user_journeys": [item.canonical_dict() for item in self.user_journeys],
            "user_problem_statement": self.user_problem_statement.canonical_dict(),
            "user_roles": [item.canonical_dict() for item in self.user_roles],
        }

    def canonical_json(self) -> str:
        return _json(self.canonical_dict())


def validate_software_plan_candidate(candidate: SoftwarePlan | dict[str, Any] | str, *, handoff: IdeaPlanHandoff) -> SoftwarePlan:
    if isinstance(candidate, SoftwarePlan):
        return SoftwarePlan.from_dict(candidate.canonical_dict(), handoff=handoff)
    if isinstance(candidate, str):
        return SoftwarePlan.from_json(candidate, handoff=handoff)
    if isinstance(candidate, dict):
        return SoftwarePlan.from_dict(candidate, handoff=handoff)
    raise ValueError("Software plan candidate must be a validated plan, JSON object, or JSON text.")
