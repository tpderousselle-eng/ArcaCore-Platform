"""Provider-neutral logical models. All content is inert; no implementation output.

Names are presentation labels. Responsibility is bound to frozen architecture
capabilities. Unapproved logical choices must cite an explicit blocking question.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import lru_cache
from decimal import Decimal
import re
import unicodedata

from .architecture_models_handoff import ArchitectureModelsHandoff, validate_architecture_models_handoff
from .architecture_specification import Record, _exact, _identity, _json, _parse, _safe, _strings, _text
from .project import BuildStage

ARCADEV_DOMAIN_MODEL_SPECIFICATION_SCHEMA = "arcadev.domain_model_specification"
ARCADEV_DOMAIN_MODEL_SPECIFICATION_SCHEMA_VERSION = 1


class LogicalType(str, Enum):
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    ENUM = "enum"
    JSON = "json"
    BINARY_REFERENCE = "binary_reference"
    EXTERNAL_REFERENCE = "external_reference"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"
    EXTERNAL_IDENTIFIER = "external_identifier"


class ModelArea(str, Enum):
    IDENTITY = "identity"
    FIELD = "field"
    RELATIONSHIP = "relationship"
    LIFECYCLE = "lifecycle"
    EXTERNAL_REFERENCE = "external_reference"
    PRINCIPAL_REFERENCE = "principal_reference"
    RETENTION = "retention"
    UNIQUENESS = "uniqueness"
    LOOKUP = "lookup"


class ModelProvenance(str, Enum):
    ARCHITECTURE = "approved_architecture"
    DECISION = "approved_architecture_decision"
    DERIVED = "deterministic_model_derivation"
    QUESTION = "unresolved_model_question"


def _norm(value):
    return unicodedata.normalize("NFKC", _text(value)).casefold()


def _model_safe(value):
    _safe(value)
    # Common opaque credentials also need rejection without a key=value label.
    def visit(item):
        if type(item) is str:
            if re.search(r"(?i)(?:password|passwd|secret|api[_ -]?key|(?:access|refresh)[_ -]?token|private[_ -]?key)\s*(?:=|:)\s*[^\s,;]+", item):
                raise ValueError("Model data contains a literal credential.")
            if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{16,}|Bearer\s+\S+|ya29\.[A-Za-z0-9._-]+|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", item):
                raise ValueError("Model data contains a credential/token.")
        if type(item) is dict:
            for key, child in item.items():
                if re.fullmatch(r"(?i)(password|passwd|client_secret|access_token|refresh_token|api_key|private_key)", key) and child is not None:
                    raise ValueError("Model data contains credential material.")
                visit(child)
        elif type(item) is list:
            for child in item:
                visit(child)
    visit(value)


@lru_cache(maxsize=8)
def _certified_handoff(text):
    # Cache complete canonical bytes, never an asserted identity or object id.
    return validate_architecture_models_handoff(text)


def model_handoff(handoff):
    if type(handoff) is not ArchitectureModelsHandoff:
        raise ValueError("Models require a certified ArchitectureModelsHandoff.")
    return _certified_handoff(handoff.canonical_json())


def model_architecture_sources(handoff):
    """Source IDs refer to frozen architecture records, never live PLAN inference."""
    package = handoff.frozen_approved_architecture.package
    spec = package.original_architecture
    result = {spec.architecture_id: (spec.objective.value, ModelProvenance.ARCHITECTURE)}
    for item in spec.components:
        result[item.component_id] = (item.responsibility.value, ModelProvenance.ARCHITECTURE)
    for item in spec.aspects:
        result[item.aspect_id] = (item.responsibility.value, ModelProvenance.ARCHITECTURE)
    for item in package.architecture_finalization.decisions:
        result[item.decision_id] = ("; ".join(item.accepted_values), ModelProvenance.DECISION)
    return result


def persistent_model_capabilities(handoff):
    """Storage ownership and integration boundaries are the bounded state rule.

An integration owner needs safe external reference state; identity providers
remain external credential owners. Capability identities survive renaming.
"""
    spec = handoff.frozen_approved_architecture.package.original_architecture
    storage_sources = {s for c in spec.components if c.category == "storage" for s in c.responsibility.source_requirements}
    storage_sources.update(s for a in spec.aspects if a.area.value == "storage" for s in a.responsibility.source_requirements)
    result = {}
    for component in spec.components:
        if component.category == "identity":
            continue
        for capability in component.owned_capabilities:
            if capability in storage_sources or component.category == "adapter":
                result[capability] = component.component_id
    return result


_RULES = {
    "model_objective": "Logical domain model preserving: {source}",
    "capability_state": "Persistent domain state for: {source}",
    "entity_identity": "Stable logical identity required by: {source}",
    "external_reference": "Non-secret external reference required by: {source}",
    "ownership_boundary": "Logical ownership boundary preserving: {source}",
    "lifecycle_state": "Lifecycle representation requires an explicit choice for: {source}",
    "lookup_requirement": "Logical access requirement preserving: {source}",
}


@dataclass(frozen=True)
class ModelFact(Record):
    value: str
    source_requirements: tuple[str, ...]
    provenance: ModelProvenance
    derivation: str | None = None
    question_id: str | None = None

    @classmethod
    def create(cls, *, handoff, source_requirements, derivation=None, question_id=None, value=None, provenance=None):
        sources = _strings(source_requirements, required=True)
        catalog = model_architecture_sources(handoff)
        if not set(sources) <= catalog.keys():
            raise ValueError("Model source does not exist in frozen ApprovedArchitecture.")
        if question_id is not None:
            if derivation is not None:
                raise ValueError("An unresolved choice cannot claim deterministic derivation.")
            expected, origin = _text(value), ModelProvenance.QUESTION
            _text(question_id)
        elif derivation is not None:
            if type(derivation) is not str or derivation not in _RULES:
                raise ValueError("Unsupported model derivation.")
            expected = _RULES[derivation].format(source="; ".join(catalog[s][0] for s in sources))
            origin = ModelProvenance.DERIVED
        else:
            if len(sources) != 1:
                raise ValueError("Approved model facts require one exact source.")
            expected, origin = catalog[sources[0]]
        if value is not None and _text(value) != expected:
            raise ValueError("Model fact invents or changes frozen content.")
        if provenance is not None and provenance != origin:
            raise ValueError("Forged model provenance.")
        result = cls(expected, sources, origin, derivation, question_id)
        _model_safe(result.canonical_dict())
        return result


@dataclass(frozen=True)
class ModelQuestion(Record):
    question_id: str
    question: str
    blocking: bool
    area: ModelArea
    source_requirements: tuple[str, ...]
    entity_ids: tuple[str, ...] = ()
    relationship_ids: tuple[str, ...] = ()

    @classmethod
    def create(cls, *, handoff, question, blocking, area, source_requirements, entity_ids=(), relationship_ids=()):
        if type(blocking) is not bool:
            raise ValueError("Model question blocking must be boolean.")
        sources = _strings(source_requirements, required=True)
        if not set(sources) <= model_architecture_sources(handoff).keys():
            raise ValueError("Model question has nonexistent architecture sources.")
        result = cls("", _text(question, maximum=2000), blocking, ModelArea(area), sources, _strings(entity_ids), _strings(relationship_ids))
        body = result.canonical_dict()
        body.pop("question_id")
        return replace(result, question_id=_identity("model_question", body))


def model_question_id(question):
    body = question.canonical_dict()
    body.pop("question_id")
    return _identity("model_question", body)


@dataclass(frozen=True)
class ModelField(Record):
    field_id: str
    name: str
    logical_type: LogicalType
    required: bool
    collection: bool
    mutable: bool | None
    unique: bool | None
    classification: DataClassification
    evidence: ModelFact
    value_domain_id: str | None = None
    default_json: str | None = None


@dataclass(frozen=True)
class ModelEntity(Record):
    entity_id: str
    name: str
    responsibility: ModelFact
    owned_capabilities: tuple[str, ...]
    fields: tuple[ModelField, ...] = ()
    aggregate_role: str | None = None
    classification: DataClassification = DataClassification.INTERNAL
    identity_field_ids: tuple[str, ...] = ()
    identity_question_id: str | None = None
    lifecycle_domain_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelValueDomain(Record):
    domain_id: str
    name: str
    values: tuple[str, ...]
    evidence: ModelFact


@dataclass(frozen=True)
class ModelRelationship(Record):
    relationship_id: str
    name: str
    source_entity_id: str
    target_entity_id: str
    source_cardinality: str
    target_cardinality: str
    required: bool
    evidence: ModelFact
    ownership: str | None = None
    deletion_behavior: str | None = None


@dataclass(frozen=True)
class ModelConstraint(Record):
    constraint_id: str
    kind: str
    entity_id: str
    field_ids: tuple[str, ...]
    value_json: str
    evidence: ModelFact


@dataclass(frozen=True)
class ModelAccessRequirement(Record):
    access_id: str
    name: str
    entity_id: str
    field_ids: tuple[str, ...]
    unique: bool
    evidence: ModelFact


@dataclass(frozen=True)
class ModelReadiness(Record):
    structurally_valid: bool
    ready_for_finalization: bool
    blocking_reasons: tuple[str, ...]


_IDS = {ModelField: "field_id", ModelEntity: "entity_id", ModelValueDomain: "domain_id", ModelRelationship: "relationship_id", ModelConstraint: "constraint_id", ModelAccessRequirement: "access_id"}


def model_element_id(kind, *, name, source_requirements, scope=()):
    """Stable content-derived graph handle; the specification hashes full content."""
    if kind not in {"entity", "field", "domain", "relationship", "constraint", "access"}:
        raise ValueError("Unsupported logical element kind.")
    return _identity("model_" + kind, {"name": _text(name), "sources": list(_strings(source_requirements, required=True)), "scope": list(_strings(scope))})


def _bool(value, nullable=False):
    if type(value) is not bool and not (nullable and value is None):
        raise ValueError("Model boolean semantics must be explicit booleans.")
    return value


def _records(values, cls, handoff):
    if type(values) not in (list, tuple) or len(values) > 256:
        raise ValueError("Model records require a bounded collection.")
    result = []
    for raw in values:
        value = raw.canonical_dict() if type(raw) is cls else raw
        _model_safe(value)
        _exact(value, (f.name for f in fields(cls)))
        args = dict(value)
        if cls is ModelFact:
            item = cls.create(handoff=handoff, **args)
        elif cls is ModelQuestion:
            claimed = args.pop("question_id")
            item = cls.create(handoff=handoff, **args)
            if claimed != item.question_id:
                raise ValueError("Forged model question identity.")
        else:
            for key in ("name", "kind", "source_cardinality", "target_cardinality", "ownership", "deletion_behavior", "aggregate_role"):
                if key in args and args[key] is not None:
                    args[key] = _text(args[key], maximum=240)
            for key in ("owned_capabilities", "identity_field_ids", "lifecycle_domain_ids", "field_ids", "values"):
                if key in args:
                    args[key] = _strings(args[key], required=key == "values")
                    if len({_norm(v) for v in args[key]}) != len(args[key]):
                        raise ValueError("Duplicate normalized model values.")
            for key in ("responsibility", "evidence"):
                if key in args:
                    args[key] = _records([args[key]], ModelFact, handoff)[0]
            if "fields" in args:
                args["fields"] = _records(args["fields"], ModelField, handoff)
            if "logical_type" in args:
                args["logical_type"] = LogicalType(args["logical_type"])
            if "classification" in args:
                args["classification"] = DataClassification(args["classification"])
            for key in ("required", "collection", "mutable", "unique"):
                if key in args:
                    args[key] = _bool(args[key], nullable=cls is ModelField and key in {"mutable", "unique"})
            for key in ("value_json", "default_json"):
                if key in args and args[key] is not None:
                    inert = _parse(args[key])
                    _model_safe(inert)
                    args[key] = _json(inert).strip()
            item = cls(**args)
            # Field identity includes its declared graph scope supplied by the entity
            # at specification validation. Other handles are checked there as well.
        result.append(item)
    result.sort(key=lambda item: item.canonical_json())
    if len({v.canonical_json() for v in result}) != len(result):
        raise ValueError("Duplicate canonical model records.")
    return tuple(result)


def _fact_scope(fact, questions, entity_ids=(), areas=()):
    if fact.question_id is None:
        return
    question = questions.get(fact.question_id)
    if question is None or not question.blocking or not set(fact.source_requirements) <= set(question.source_requirements):
        raise ValueError("Unapproved model content requires a grounded blocking question.")
    if not set(entity_ids) <= set(question.entity_ids) or (areas and question.area not in areas):
        raise ValueError("Model choice escapes its question area or affected entities.")


def _explicit_choice(fact, payload, questions, entity_ids=(), areas=()):
    """A source citation alone cannot authorize invented types/states/defaults.

An approved choice repeats an exact declarative architecture decision value;
otherwise the whole proposed choice stays behind its blocking model question.
"""
    _fact_scope(fact, questions, entity_ids, areas)
    if fact.question_id is None and (fact.provenance not in {ModelProvenance.ARCHITECTURE, ModelProvenance.DECISION} or fact.value != _json(payload).strip()):
        raise ValueError("Logical choice requires exact approved declarative evidence or an unresolved question.")


_COLLECTIONS = {"entities": ModelEntity, "value_domains": ModelValueDomain, "relationships": ModelRelationship,
                "constraints": ModelConstraint, "access_requirements": ModelAccessRequirement, "open_model_questions": ModelQuestion}


@dataclass(frozen=True)
class DomainModelSpecification(Record):
    model_id: str
    handoff_id: str
    project_id: str
    plan_handoff_id: str
    approved_architecture_id: str
    architecture_id: str
    architecture_finalization_id: str
    objective: ModelFact
    entities: tuple[ModelEntity, ...]
    value_domains: tuple[ModelValueDomain, ...]
    relationships: tuple[ModelRelationship, ...]
    constraints: tuple[ModelConstraint, ...]
    access_requirements: tuple[ModelAccessRequirement, ...]
    open_model_questions: tuple[ModelQuestion, ...]
    readiness: ModelReadiness
    project_stage: BuildStage = BuildStage.MODELS
    schema: str = ARCADEV_DOMAIN_MODEL_SPECIFICATION_SCHEMA
    schema_version: int = 1

    @classmethod
    def create(cls, *, handoff, objective, entities=(), value_domains=(), relationships=(), constraints=(), access_requirements=(), open_model_questions=()):
        handoff = model_handoff(handoff)
        objective = _records([objective], ModelFact, handoff)[0]
        if objective.derivation != "model_objective" or objective.source_requirements != (handoff.architecture_id,):
            raise ValueError("Model objective must preserve the exact frozen architecture objective.")
        supplied = locals()
        collections = {key: _records(supplied[key], typ, handoff) for key, typ in _COLLECTIONS.items()}
        entities = collections["entities"]
        questions = {q.question_id: q for q in collections["open_model_questions"]}
        entity_map = {e.entity_id: e for e in entities}
        domains = {d.domain_id: d for d in collections["value_domains"]}
        relationships = {r.relationship_id: r for r in collections["relationships"]}
        required = persistent_model_capabilities(handoff)
        architecture = handoff.frozen_approved_architecture.package.original_architecture
        allowed = {capability: component.component_id for component in architecture.components
                   if component.category in {"application", "service", "adapter"} for capability in component.owned_capabilities}
        owned = [c for e in entities for c in e.owned_capabilities]
        if not set(required) <= set(owned) or not set(owned) <= set(allowed) or len(owned) != len(set(owned)):
            raise ValueError("Required persistent architecture state needs exactly one owner; unsupported or removed state.")
        all_fields = [f for e in entities for f in e.fields]
        if len({f.field_id for f in all_fields}) != len(all_fields):
            raise ValueError("Duplicate field identities across model.")
        for name, typ in _COLLECTIONS.items():
            if typ is ModelQuestion:
                continue
            records = collections[name]
            key = _IDS[typ]
            if len({getattr(v, key) for v in records}) != len(records):
                raise ValueError("Duplicate model identities.")
            if typ in (ModelEntity, ModelValueDomain) and len({_norm(v.name) for v in records}) != len(records):
                raise ValueError("Duplicate normalized model names.")
        for q in questions.values():
            if not set(q.entity_ids) <= entity_map.keys() or not set(q.relationship_ids) <= relationships.keys():
                raise ValueError("Question references nonexistent model elements.")
        for entity in entities:
            sources = tuple(sorted({allowed[c] for c in entity.owned_capabilities}))
            if not sources or entity.responsibility.derivation != "capability_state" or entity.responsibility.source_requirements != sources:
                raise ValueError("Entity responsibility must derive exactly from its owned persistent capabilities.")
            expected = model_element_id("entity", name=entity.name, source_requirements=sources, scope=entity.owned_capabilities)
            if entity.entity_id != expected:
                raise ValueError("Forged entity identity.")
            if set(entity.owned_capabilities) - set(required) and not any(q.blocking and q.area is ModelArea.LIFECYCLE
                    and entity.entity_id in q.entity_ids and set(sources) <= set(q.source_requirements) for q in questions.values()):
                raise ValueError("Persistence not assigned by architecture requires a blocking lifecycle question.")
            if entity.aggregate_role not in (None, "aggregate_root", "entity", "dependent_entity", "reference", "external_reference"):
                raise ValueError("Unsupported aggregate role.")
            if entity.aggregate_role is not None:
                if not any(q.area is ModelArea.RELATIONSHIP and q.blocking and entity.entity_id in q.entity_ids for q in questions.values()):
                    raise ValueError("Aggregate role needs an explicit model ownership question.")
            if len({_norm(f.name) for f in entity.fields}) != len(entity.fields):
                raise ValueError("Duplicate field names in entity.")
            field_map = {f.field_id: f for f in entity.fields}
            if not set(entity.identity_field_ids) <= field_map.keys() or not set(entity.lifecycle_domain_ids) <= domains.keys():
                raise ValueError("Invalid identity/lifecycle reference.")
            if bool(entity.identity_field_ids) == bool(entity.identity_question_id):
                raise ValueError("Entity needs exactly one stable identity representation or unresolved identity question.")
            if entity.identity_question_id:
                q = questions.get(entity.identity_question_id)
                if q is None or q.area is not ModelArea.IDENTITY or not q.blocking or entity.entity_id not in q.entity_ids or not set(sources) <= set(q.source_requirements):
                    raise ValueError("Invalid identity question binding.")
            for identity in entity.identity_field_ids:
                field = field_map[identity]
                if not field.required or field.collection or field.mutable is not False or field.logical_type not in {LogicalType.STRING, LogicalType.INTEGER, LogicalType.UUID, LogicalType.EXTERNAL_REFERENCE}:
                    raise ValueError("Stable entity identity must be required, scalar and immutable.")
            for field in entity.fields:
                if field.field_id != model_element_id("field", name=field.name, source_requirements=field.evidence.source_requirements, scope=(entity.entity_id,)):
                    raise ValueError("Forged field identity.")
                if (field.logical_type is LogicalType.ENUM) != (field.value_domain_id is not None) or (field.value_domain_id is not None and field.value_domain_id not in domains):
                    raise ValueError("Invalid enum/value-domain reference.")
                if re.search(r"(?i)password|passwd|(?:access|refresh|oauth)[_ -]?token|(?:client|oauth)[_ -]?secret|private[_ -]?key", field.name):
                    raise ValueError("Credential storage must remain an external ownership boundary.")
                payload = field.canonical_dict()
                for key in ("field_id", "evidence"):
                    payload.pop(key)
                _explicit_choice(field.evidence, payload, questions, (entity.entity_id,), tuple(ModelArea))
                if field.default_json is not None and field.evidence.question_id is not None:
                    raise ValueError("Defaults require explicit approved authorization, not proposed question content.")
            if any(c.category == "adapter" and c.component_id in sources for c in architecture.components):
                safe_reference = any(f.logical_type is LogicalType.EXTERNAL_REFERENCE and f.classification is DataClassification.EXTERNAL_IDENTIFIER for f in entity.fields)
                reference_question = any(q.blocking and q.area is ModelArea.EXTERNAL_REFERENCE and entity.entity_id in q.entity_ids
                                         and set(sources) <= set(q.source_requirements) for q in questions.values())
                if not safe_reference and not reference_question:
                    raise ValueError("Required integration state needs safe external references or a blocking identifier question.")
        for domain in domains.values():
            if domain.domain_id != model_element_id("domain", name=domain.name, source_requirements=domain.evidence.source_requirements):
                raise ValueError("Forged value-domain identity.")
            _explicit_choice(domain.evidence, {"name": domain.name, "values": list(domain.values)}, questions, areas=(ModelArea.LIFECYCLE, ModelArea.RETENTION, ModelArea.FIELD))
        semantic_edges = set()
        for edge in relationships.values():
            if edge.source_entity_id not in entity_map or edge.target_entity_id not in entity_map:
                raise ValueError("Relationship references nonexistent entity.")
            if edge.source_cardinality not in {"one", "zero_or_one", "many"} or edge.target_cardinality not in {"one", "zero_or_one", "many"}:
                raise ValueError("Invalid logical cardinality.")
            if edge.required != (edge.target_cardinality == "one"):
                raise ValueError("Contradictory required/optional cardinality.")
            if edge.ownership not in {None, "independent", "source_owns_target", "target_owns_source"} or edge.deletion_behavior not in {None, "retain", "restrict", "detach", "delete_dependent"}:
                raise ValueError("Unsupported logical ownership/deletion behavior.")
            endpoints = (edge.source_entity_id, edge.target_entity_id)
            if edge.relationship_id != model_element_id("relationship", name=edge.name, source_requirements=edge.evidence.source_requirements, scope=tuple(set(endpoints))):
                raise ValueError("Forged relationship identity.")
            semantic = (edge.source_entity_id, edge.target_entity_id, _norm(edge.name))
            if semantic in semantic_edges:
                raise ValueError("Duplicate canonical relationship.")
            semantic_edges.add(semantic)
            payload = edge.canonical_dict()
            payload.pop("relationship_id")
            payload.pop("evidence")
            _explicit_choice(edge.evidence, payload, questions, endpoints, (ModelArea.RELATIONSHIP,))
        for name in ("constraints", "access_requirements"):
            for item in collections[name]:
                if item.entity_id not in entity_map or not set(item.field_ids) <= {f.field_id for f in entity_map[item.entity_id].fields}:
                    raise ValueError("Constraint/access requirement has invalid entity or field references.")
                if not item.field_ids:
                    raise ValueError("Constraint/access requirements need explicit logical fields.")
                kind = "constraint" if name == "constraints" else "access"
                label = item.kind if kind == "constraint" else item.name
                expected = model_element_id(kind, name=label, source_requirements=item.evidence.source_requirements, scope=(item.entity_id, *item.field_ids))
                if getattr(item, _IDS[type(item)]) != expected:
                    raise ValueError("Forged constraint/access identity.")
                if kind == "constraint":
                    _validate_constraint(item)
                payload = item.canonical_dict()
                payload.pop(_IDS[type(item)])
                payload.pop("evidence")
                _explicit_choice(item.evidence, payload, questions, (item.entity_id,), (ModelArea.FIELD, ModelArea.UNIQUENESS, ModelArea.LOOKUP, ModelArea.LIFECYCLE, ModelArea.RETENTION, ModelArea.RELATIONSHIP))
        bounds = {}
        for item in collections["constraints"]:
            if item.kind in {"min_length", "max_length", "min_value", "max_value"}:
                key = (item.entity_id, item.field_ids, item.kind.split("_", 1)[1])
                slot = bounds.setdefault(key, {})
                number = Decimal(str(_parse(item.value_json)))
                side = item.kind.split("_", 1)[0]
                slot[side] = (max if side == "min" else min)(slot.get(side, number), number)
        if any("min" in b and "max" in b and b["min"] > b["max"] for b in bounds.values()):
            raise ValueError("Contradictory logical constraint bounds.")
        blockers = ("blocking_model_questions",) if any(q.blocking for q in questions.values()) else ()
        readiness = ModelReadiness(True, not blockers, blockers)
        result = cls("", handoff.handoff_id, handoff.source_project_id, handoff.plan_handoff_id, handoff.approved_architecture_id,
                     handoff.architecture_id, handoff.architecture_finalization_id, objective, readiness=readiness, **collections)
        body = result.canonical_dict()
        body.pop("model_id")
        body.pop("readiness")
        result = replace(result, model_id=_identity("domain_model", body))
        _model_safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value, *, handoff):
        _model_safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_DOMAIN_MODEL_SPECIFICATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported domain model schema/version.")
        result = cls.create(handoff=handoff, objective=value["objective"], **{key: value[key] for key in _COLLECTIONS})
        # Reordered collections are equivalent, but supplied identities, stage,
        # exact upstream binding, and readiness can never be caller assertions.
        for key in ("model_id", "handoff_id", "project_id", "plan_handoff_id", "approved_architecture_id", "architecture_id", "architecture_finalization_id", "project_stage", "readiness"):
            if _json(value[key]) != _json(result.canonical_dict()[key]):
                raise ValueError("Forged model identity, handoff binding, stage or readiness.")
        return result

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def _validate_constraint(item):
    value = _parse(item.value_json)
    if item.kind in {"min_length", "max_length"}:
        if type(value) is not int or value < 0:
            raise ValueError("Length constraint requires a nonnegative integer.")
    elif item.kind in {"min_value", "max_value"}:
        if type(value) is not int and not (type(value) is str and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value)):
            raise ValueError("Numeric bounds require an integer or canonical decimal text.")
    elif item.kind == "allowed_values":
        values = _strings(value, required=True)
        if len({_norm(v) for v in values}) != len(values):
            raise ValueError("Duplicate normalized allowed values.")
    elif item.kind == "format":
        if value not in ("email", "uri", "uuid", "date", "datetime"):
            raise ValueError("Unsupported declarative format.")
    elif item.kind == "pattern":
        _text(value, maximum=500)  # Deliberately never compiled or evaluated.
    elif item.kind in {"unique", "composite_unique", "required_combination"}:
        if value is not True or (item.kind == "composite_unique" and len(item.field_ids) < 2):
            raise ValueError("Invalid declarative uniqueness/combination.")
    elif item.kind in {"lifecycle_invariant", "ownership_invariant"}:
        if value not in ("immutable_after_terminal", "owner_required", "same_owner"):
            raise ValueError("Unsupported bounded invariant; ask a model question.")
    else:
        raise ValueError("Unsupported logical constraint; executable expressions are forbidden.")


def validate_domain_model_specification(candidate, *, handoff):
    if type(candidate) is DomainModelSpecification:
        candidate = candidate.canonical_dict()
    if type(candidate) is str:
        return DomainModelSpecification.from_json(candidate, handoff=handoff)
    return DomainModelSpecification.from_dict(candidate, handoff=handoff)
