"""Immutable declarative architecture, grounded in a certified frozen PLAN.

Labels are inert presentation text. Material assertions are ArchitectureFacts:
exact approved values or the output of a named, bounded derivation rule.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
import hashlib
import json
import re
import unicodedata

from .plan_architecture_handoff import PlanArchitectureHandoff
from .project import BuildStage

ARCADEV_ARCHITECTURE_SPECIFICATION_SCHEMA = "arcadev.architecture_specification"
ARCADEV_ARCHITECTURE_SPECIFICATION_SCHEMA_VERSION = 1
MAX_ARCHITECTURE_BYTES = 5_000_000
MAX_ARCHITECTURE_ITEMS = 256
_SECRET = re.compile(r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)\s*(?:=|:)\s*[^\s,;]{4,}|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _identity(kind, value):
    return "arcadev_" + kind + "_" + hashlib.sha256(("arcadev-" + kind + "/v1\0" + _json(value)).encode("utf-8")).hexdigest()[:32]


def _text(value, label="architecture text", maximum=8000, *, preserve=False):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} is empty, malformed, or exceeds its size limit.")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{label} contains malformed Unicode.") from error
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET.search(value):
        raise ValueError(f"{label} contains a secret or private key.")
    return value if preserve else " ".join(value.split())


def _safe(value, depth=0):
    """Bound JSON data before recursion, hashing, or domain reconstruction."""
    if depth > 40:
        raise ValueError("Architecture nesting exceeds its safety limit.")
    if type(value) is str:
        _text(value, maximum=100_000)
    elif type(value) is dict:
        if len(value) > MAX_ARCHITECTURE_ITEMS:
            raise ValueError("Architecture object exceeds its safety limit.")
        for key, item in value.items():
            _text(key, maximum=240)
            _safe(item, depth + 1)
    elif type(value) is list:
        if len(value) > MAX_ARCHITECTURE_ITEMS:
            raise ValueError("Architecture array exceeds its safety limit.")
        for item in value:
            _safe(item, depth + 1)
    elif value is not None and type(value) not in (bool, int):
        raise ValueError("Architecture requires inert JSON values.")
    if depth == 0 and len(_json(value).encode("utf-8")) > MAX_ARCHITECTURE_BYTES:
        raise ValueError("Architecture document exceeds its safety limit.")


def _pairs(pairs):
    result = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("Architecture document contains a duplicate JSON key.")
        result[key] = item
    return result


def _parse(text):
    try:
        if type(text) is not str or len(text.encode("utf-8")) > MAX_ARCHITECTURE_BYTES:
            raise ValueError("Architecture JSON exceeds its safety limit.")
        value = json.loads(text, object_pairs_hook=_pairs)
        _safe(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Architecture is not valid JSON.") from error


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("Architecture record has an invalid shape or unknown fields.")


def _strings(values, *, required=False):
    if type(values) not in (tuple, list) or len(values) > MAX_ARCHITECTURE_ITEMS:
        raise ValueError("Architecture values must be a bounded collection.")
    result = tuple(sorted((_text(value) for value in values), key=lambda v: (v.casefold(), v)))
    if (required and not result) or len({v.casefold() for v in result}) != len(result):
        raise ValueError("Architecture values are empty or duplicate normalized values.")
    return result


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Record):
        return value.canonical_dict()
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    return value


class Record:
    def canonical_dict(self):
        return {field.name: _encode(getattr(self, field.name)) for field in fields(self)}

    def canonical_json(self):
        return _json(self.canonical_dict())


class ArchitectureProvenance(str, Enum):
    APPROVED_PLAN = "approved_plan"
    APPROVED_PLANNING_DECISION = "approved_planning_decision"
    DERIVED = "deterministic_architecture_derivation"


class ArchitectureArea(str, Enum):
    CONTEXT = "context"
    STYLE = "style"
    COMPONENT = "component"
    INTERFACE = "interface"
    DATA_FLOW = "data_flow"
    STORAGE = "storage"
    INTEGRATION = "integration"
    AUTHENTICATION = "authentication"
    BACKGROUND = "background"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    RESILIENCE = "resilience"
    RISK = "risk"
    FRONTEND = "frontend"


def approved_architecture_sources(handoff):
    """Stable references to material PLAN items and accepted planning decisions."""
    plan = handoff.frozen_approved_plan.package.plan_finalization.original_plan
    result = {}

    def visit(value):
        if isinstance(value, dict):
            if set(value) == {"value", "provenance", "source_requirements"}:
                result[_identity("plan_source", value)] = (value["value"], ArchitectureProvenance.APPROVED_PLAN)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(plan.canonical_dict())
    for decision in handoff.frozen_approved_plan.package.plan_finalization.decisions:
        result[decision.decision_id] = ("; ".join(decision.accepted_values), ArchitectureProvenance.APPROVED_PLANNING_DECISION)
    return result


def plan_source_id(item):
    return _identity("plan_source", item.canonical_dict())


_DERIVATIONS = {
    "responsibility": "Logical responsibility for: {source}",
    "boundary": "Logical boundary preserving: {source}",
    "interaction": "Exchange required to support: {source}",
    "storage": "Logical persistence responsibility for: {source}",
    "security": "Least-privilege access and secrets ownership boundary for: {source}",
    "observability": "Logical operation outcomes and failure observation for: {source}",
    "resilience": "Isolate dependency failures and review retry/idempotency needs for: {source}",
    "risk": "Implementation choices must preserve: {source}",
    "mitigation": "Validate implementation against approved requirements: {source}",
    "style": "Separate logical responsibilities while preserving: {source}",
}


@dataclass(frozen=True)
class ArchitectureFact(Record):
    value: str
    provenance: ArchitectureProvenance
    source_requirements: tuple[str, ...]
    derivation: str | None = None

    @classmethod
    def create(cls, *, handoff, source_requirements, derivation=None, value=None, provenance=None):
        sources = _strings(source_requirements, required=True)
        catalog = approved_architecture_sources(handoff)
        if any(source not in catalog for source in sources):
            raise ValueError("Architecture source requirement does not exist in approved PLAN.")
        if derivation is None:
            if len(sources) != 1:
                raise ValueError("An approved fact requires one exact source.")
            expected, origin = catalog[sources[0]]
        else:
            if type(derivation) is not str or derivation not in _DERIVATIONS:
                raise ValueError("Unsupported deterministic architecture derivation.")
            expected = _DERIVATIONS[derivation].format(source="; ".join(catalog[source][0] for source in sources))
            origin = ArchitectureProvenance.DERIVED
        if value is not None and _text(value) != expected:
            raise ValueError("Architecture fact is invented or changes approved content.")
        if provenance is not None and provenance != origin:
            raise ValueError("Architecture provenance is forged.")
        return cls(_text(expected), origin, sources, derivation)

    @classmethod
    def from_dict(cls, value, *, handoff):
        _exact(value, (f.name for f in fields(cls)))
        _text(value["value"])
        ArchitectureProvenance(value["provenance"])
        return cls.create(handoff=handoff, **value)


@dataclass(frozen=True)
class ArchitectureQuestion(Record):
    question: str
    blocking: bool
    source_requirements: tuple[str, ...]
    area: ArchitectureArea

    @classmethod
    def create(cls, question, blocking, source_requirements, area, *, handoff):
        if type(blocking) is not bool:
            raise ValueError("Architecture question blocking must be boolean.")
        sources = _strings(source_requirements, required=True)
        if any(source not in approved_architecture_sources(handoff) for source in sources):
            raise ValueError("Architecture question references nonexistent PLAN sources.")
        return cls(_text(question, maximum=2000), blocking, sources, ArchitectureArea(area))

    @classmethod
    def from_dict(cls, value, *, handoff):
        _exact(value, (f.name for f in fields(cls)))
        return cls.create(**value, handoff=handoff)


def architecture_question_id(question):
    return _identity("architecture_question", question.canonical_dict())


@dataclass(frozen=True)
class ArchitectureComponent(Record):
    component_id: str
    name: str
    category: str
    responsibility: ArchitectureFact
    owned_capabilities: tuple[str, ...]
    dependencies: tuple[str, ...]
    exposed_interfaces: tuple[str, ...]
    trust_classification: str


@dataclass(frozen=True)
class ArchitectureConnection(Record):
    """A directed interface or data flow; external endpoints use source IDs."""
    connection_id: str
    source: str
    destination: str
    purpose: ArchitectureFact
    protocol: ArchitectureFact | None = None
    interaction: ArchitectureFact | None = None
    data_classification: ArchitectureFact | None = None
    trust_boundary_crossing: bool = True
    direction: str = "source_to_destination"


@dataclass(frozen=True)
class ArchitectureAspect(Record):
    """Logical storage, auth, deployment, security, risk, or other boundary.

Statements carry lifecycle/access/isolation/retention/failure constraints.
Technology can only repeat a frozen explicit technology preference.
"""
    aspect_id: str
    area: ArchitectureArea
    responsibility: ArchitectureFact
    component_ids: tuple[str, ...]
    constraints: tuple[ArchitectureFact, ...] = ()
    technology: ArchitectureFact | None = None


@dataclass(frozen=True)
class ArchitectureReadiness(Record):
    ready_for_finalization: bool
    blocking_reasons: tuple[str, ...]


def _records(values, cls, handoff):
    if type(values) not in (list, tuple) or len(values) > MAX_ARCHITECTURE_ITEMS:
        raise ValueError("Architecture records must be a bounded collection.")
    result = []
    for raw in values:
        value = raw.canonical_dict() if type(raw) is cls else raw
        _exact(value, (f.name for f in fields(cls)))
        args = dict(value)
        for key in ("component_id", "name", "category", "trust_classification", "connection_id", "source", "destination", "direction", "aspect_id"):
            if key in args:
                args[key] = _text(args[key], maximum=240)
        for key in ("responsibility", "purpose", "protocol", "interaction", "data_classification", "technology"):
            if key in args and args[key] is not None:
                args[key] = ArchitectureFact.from_dict(args[key], handoff=handoff)
        for key in ("owned_capabilities", "dependencies", "exposed_interfaces", "component_ids"):
            if key in args:
                args[key] = _strings(args[key])
        if "constraints" in args:
            args["constraints"] = _records(args["constraints"], ArchitectureFact, handoff)
        if cls in (ArchitectureFact, ArchitectureQuestion):
            item = cls.from_dict(value, handoff=handoff)
        else:
            if "area" in args:
                args["area"] = ArchitectureArea(args["area"])
            item = cls(**args)
        _safe(item.canonical_dict())
        result.append(item)
    result.sort(key=lambda v: v.canonical_json())
    if len({v.canonical_json() for v in result}) != len(result):
        raise ValueError("Duplicate canonical architecture records.")
    return tuple(result)


def _validated_handoff(handoff):
    if type(handoff) is not PlanArchitectureHandoff:
        raise ValueError("Architecture requires a certified PLAN architecture handoff.")
    return PlanArchitectureHandoff.from_dict(handoff.canonical_dict())


@dataclass(frozen=True)
class ArchitectureSpecification(Record):
    architecture_id: str
    handoff_id: str
    project_id: str
    idea_handoff_id: str
    software_plan_id: str
    plan_finalization_id: str
    approved_plan_id: str
    objective: ArchitectureFact
    system_boundary: ArchitectureFact
    style: ArchitectureFact
    external_entities: tuple[ArchitectureFact, ...]
    approved_constraints: tuple[ArchitectureFact, ...]
    components: tuple[ArchitectureComponent, ...]
    interfaces: tuple[ArchitectureConnection, ...]
    data_flows: tuple[ArchitectureConnection, ...]
    aspects: tuple[ArchitectureAspect, ...]
    open_architecture_questions: tuple[ArchitectureQuestion, ...]
    readiness: ArchitectureReadiness
    project_stage: BuildStage = BuildStage.ARCHITECTURE
    schema: str = ARCADEV_ARCHITECTURE_SPECIFICATION_SCHEMA
    schema_version: int = ARCADEV_ARCHITECTURE_SPECIFICATION_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff, objective, system_boundary, style, external_entities=(), approved_constraints=(),
               components=(), interfaces=(), data_flows=(), aspects=(), open_architecture_questions=()):
        handoff = _validated_handoff(handoff)
        plan = handoff.frozen_approved_plan.package.plan_finalization.original_plan
        facts = [ArchitectureFact.from_dict(v.canonical_dict(), handoff=handoff) for v in (objective, system_boundary, style)]
        collections = {}
        for name, values, typ in (
            ("external_entities", external_entities, ArchitectureFact), ("approved_constraints", approved_constraints, ArchitectureFact),
            ("components", components, ArchitectureComponent), ("interfaces", interfaces, ArchitectureConnection),
            ("data_flows", data_flows, ArchitectureConnection), ("aspects", aspects, ArchitectureAspect),
            ("open_architecture_questions", open_architecture_questions, ArchitectureQuestion),
        ):
            collections[name] = _records(values, typ, handoff)
        components = collections["components"]
        interfaces, flows, aspects = (collections[key] for key in ("interfaces", "data_flows", "aspects"))
        ids = {item.component_id for item in components}
        for records, key in ((components, "component_id"), (interfaces, "connection_id"), (flows, "connection_id"), (aspects, "aspect_id")):
            identities = [_text(getattr(item, key), maximum=240) for item in records]
            if len(set(identities)) != len(identities):
                raise ValueError("Duplicate architecture component/interface/flow/aspect identities.")
        if len({item.name.casefold() for item in components}) != len(components):
            raise ValueError("Duplicate canonical component names.")
        meanings = {(item.category, item.responsibility.canonical_json(), item.owned_capabilities) for item in components}
        if len(meanings) != len(components):
            raise ValueError("Duplicate canonical component responsibilities.")
        capabilities = {plan_source_id(item) for item in plan.in_scope_capabilities}
        owned = [source for item in components for source in item.owned_capabilities]
        if set(owned) != capabilities or len(owned) != len(set(owned)):
            raise ValueError("Approved capabilities require exactly one owner; invented or removed capability/contradictory ownership.")
        interface_ids = {item.connection_id for item in interfaces}
        for item in components:
            _text(item.name, maximum=240)
            if item.category not in {"application", "service", "storage", "worker", "adapter", "identity"}:
                raise ValueError("Unsupported component category.")
            if item.trust_classification not in {"application", "isolated", "external"}:
                raise ValueError("Unsupported trust classification.")
            if not set(item.owned_capabilities) <= set(item.responsibility.source_requirements):
                raise ValueError("Component responsibility must trace every owned capability.")
            if not set(item.dependencies) <= ids or item.component_id in item.dependencies:
                raise ValueError("Invalid or self dependency reference.")
            if not set(item.exposed_interfaces) <= interface_ids:
                raise ValueError("Invalid exposed interface reference.")
        external_ids = {source for fact in collections["external_entities"] for source in fact.source_requirements}
        if ids & external_ids:
            raise ValueError("Ambiguous component and external endpoint identities.")
        endpoints = ids | external_ids
        for item in (*interfaces, *flows):
            if item.source not in endpoints or item.destination not in endpoints or item.source == item.destination:
                raise ValueError("Invalid interface or data-flow endpoint reference.")
            if type(item.trust_boundary_crossing) is not bool or item.direction != "source_to_destination":
                raise ValueError("Invalid flow direction or trust boundary.")
            for explicit in (item.protocol, item.interaction, item.data_classification):
                if explicit is not None and explicit.provenance is ArchitectureProvenance.DERIVED:
                    raise ValueError("Protocol, interaction and classification require explicit approved evidence.")
        for item in components:
            for interface_id in item.exposed_interfaces:
                if not any(v.connection_id == interface_id and item.component_id in (v.source, v.destination) for v in interfaces):
                    raise ValueError("Exposed interface does not touch its component.")
        constraints = collections["approved_constraints"]
        expected_constraints = {plan_source_id(item) for item in (*plan.planning_constraints, *plan.integrations)}
        expected_constraints.update(v.decision_id for v in handoff.frozen_approved_plan.package.plan_finalization.decisions)
        actual_constraints = {source for fact in constraints for source in fact.source_requirements}
        if actual_constraints != expected_constraints or any(f.derivation is not None for f in constraints):
            raise ValueError("Approved platforms/authentication/integration/deployment/planning decisions must be preserved exactly.")
        tech_values = {v.value for v in handoff.frozen_approved_plan.package.idea_handoff.snapshot.intake.technology_preferences}
        for item in aspects:
            if not item.component_ids or not set(item.component_ids) <= ids:
                raise ValueError("Architecture aspect requires valid responsible components.")
            if item.technology is not None and (item.technology.derivation is not None or
                    (item.technology.value not in tech_values and item.technology.provenance is not ArchitectureProvenance.APPROVED_PLANNING_DECISION)):
                raise ValueError("Technology choice requires an explicit approved technology preference.")
        missing = []
        areas = {item.area for item in aspects}
        for area in (ArchitectureArea.DEPLOYMENT, ArchitectureArea.SECURITY, ArchitectureArea.RISK):
            if area not in areas:
                missing.append(area.value)
        intake = handoff.frozen_approved_plan.package.idea_handoff.snapshot.intake
        for values, area in ((intake.authentication_requirements, ArchitectureArea.AUTHENTICATION), (intake.integration_requirements, ArchitectureArea.INTEGRATION), (intake.deployment_requirements, ArchitectureArea.DEPLOYMENT)):
            for value in values:
                if value.value.casefold().startswith("no "):
                    continue
                source_ids = {key for key, (text, _) in approved_architecture_sources(handoff).items() if text == value.value}
                if not any(item.area is area and source_ids & set(item.responsibility.source_requirements) for item in aspects):
                    raise ValueError("Required approved integration/authentication/deployment boundary is missing.")
        for component in components:
            for dependency in component.dependencies:
                if not any(v.source == component.component_id and v.destination == dependency for v in interfaces):
                    missing.append("dependency_interfaces")
        if len(components) > 1 and not interfaces:
            missing.append("material_interfaces")
        if not components:
            missing.append("components")
        if any(q.blocking for q in collections["open_architecture_questions"]):
            missing.append("blocking_architecture_questions")
        readiness = ArchitectureReadiness(not missing, tuple(sorted(set(missing))))
        provisional = cls("", handoff.handoff_id, handoff.source_project_id, handoff.idea_handoff_id, handoff.software_plan_id,
                          handoff.plan_finalization_id, handoff.approved_plan_id, *facts, readiness=readiness, **collections)
        body = provisional.canonical_dict()
        body.pop("architecture_id")
        body.pop("readiness")
        result = replace(provisional, architecture_id=_identity("architecture", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value, *, handoff):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_ARCHITECTURE_SPECIFICATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported architecture schema/version.")
        if value["project_stage"] != BuildStage.ARCHITECTURE.value:
            raise ValueError("Architecture must remain at ARCHITECTURE.")
        for key, expected in (("handoff_id", handoff.handoff_id), ("project_id", handoff.source_project_id), ("idea_handoff_id", handoff.idea_handoff_id),
                              ("software_plan_id", handoff.software_plan_id), ("plan_finalization_id", handoff.plan_finalization_id), ("approved_plan_id", handoff.approved_plan_id)):
            if value[key] != expected:
                raise ValueError("Forged architecture source handoff/project binding.")
        args = {key: value[key] for key in ("external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")}
        for key in args:
            if type(args[key]) is not list:
                raise ValueError("Architecture collections must be JSON arrays.")
        for key in ("objective", "system_boundary", "style"):
            args[key] = ArchitectureFact.from_dict(value[key], handoff=handoff)
        result = cls.create(handoff=handoff, **args)
        _exact(value["readiness"], {"ready_for_finalization", "blocking_reasons"})
        if value["architecture_id"] != result.architecture_id or type(value["readiness"].get("ready_for_finalization")) is not bool or value["readiness"] != result.readiness.canonical_dict():
            raise ValueError("Forged architecture identity or readiness.")
        return result

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def validate_architecture_specification(candidate, *, handoff):
    if type(candidate) is ArchitectureSpecification:
        candidate = candidate.canonical_dict()
    if type(candidate) is str:
        return ArchitectureSpecification.from_json(candidate, handoff=handoff)
    return ArchitectureSpecification.from_dict(candidate, handoff=handoff)
