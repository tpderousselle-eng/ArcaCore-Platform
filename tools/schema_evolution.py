"""Deterministic, validated schema-evolution planning.

This module describes schema changes only.  It deliberately performs no file
writes and no database migration execution.
"""

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Any

from tools.core.module_definition import ModuleDefinition, validate_module_definition


class SafetyClassification(str, Enum):
    SAFE_ADDITIVE = "SAFE_ADDITIVE"
    REQUIRES_DATA_MIGRATION = "REQUIRES_DATA_MIGRATION"
    POTENTIALLY_DESTRUCTIVE = "POTENTIALLY_DESTRUCTIVE"
    UNSUPPORTED = "UNSUPPORTED"


class ChangeKind(str, Enum):
    MODULE_ADDED = "module_added"
    MODULE_REMOVED = "module_removed"
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    NULLABLE_CHANGED = "nullable_changed"
    UNIQUE_CHANGED = "unique_changed"
    FIELD_INDEX_ADDED = "field_index_added"
    FIELD_INDEX_REMOVED = "field_index_removed"
    DEFAULT_CHANGED = "default_changed"
    ENUM_CHANGED = "enum_changed"
    FOREIGN_KEY_ADDED = "foreign_key_added"
    FOREIGN_KEY_REMOVED = "foreign_key_removed"
    FOREIGN_KEY_CHANGED = "foreign_key_changed"
    RELATIONSHIP_CHANGED = "relationship_changed"
    ENCRYPTED_METADATA_CHANGED = "encrypted_metadata_changed"
    FIELD_METADATA_CHANGED = "field_metadata_changed"
    INDEX_ADDED = "index_added"
    INDEX_REMOVED = "index_removed"
    CONSTRAINT_ADDED = "constraint_added"
    CONSTRAINT_REMOVED = "constraint_removed"
    AUDIT_METADATA_CHANGED = "audit_metadata_changed"
    VERSION_METADATA_CHANGED = "version_metadata_changed"
    SOFT_DELETE_CHANGED = "soft_delete_changed"


@dataclass(frozen=True)
class SchemaChange:
    kind: ChangeKind
    safety: SafetyClassification
    target: str
    before: Any
    after: Any
    rationale: str

    def canonical_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["kind"] = self.kind.value
        value["safety"] = self.safety.value
        return value


@dataclass(frozen=True)
class SchemaEvolutionPlan:
    module: str
    changes: tuple[SchemaChange, ...]
    schema_version: int = 1

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def executable_without_policy(self) -> bool:
        return all(
            change.safety == SafetyClassification.SAFE_ADDITIVE
            for change in self.changes
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "module": self.module,
            "changes": [change.canonical_dict() for change in self.changes],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


def _field_state(field) -> dict[str, Any]:
    return {
        "name": field.name,
        "python_type": field.python_type,
        "sqlalchemy_type": field.sqlalchemy_type,
        "type_arguments": field.type_arguments,
        "enum_name": field.enum_name,
        "enum_values": field.enum_values,
        "primary_key": field.primary_key,
        "nullable": field.nullable,
        "unique": field.unique,
        "index": field.index,
        "default": field.default,
        "max_length": field.max_length,
        "minimum": field.minimum,
        "maximum": field.maximum,
        "min_length": field.min_length,
        "pattern": field.pattern,
        "computed_expression": field.computed_expression,
        "computed_sql": field.computed_sql,
        "hybrid_expression": field.hybrid_expression,
        "hybrid_python": field.hybrid_python,
        "hybrid_class": field.hybrid_class,
        "hybrid_references": list(field.hybrid_references),
        "encrypted": field.encrypted,
        "encryption_key_env": field.encryption_key_env,
        "foreign_key": field.foreign_key,
        "relationship_name": field.relationship_name,
        "relationship_class": field.relationship_class,
        "relationship_table": field.relationship_table,
        "relationship_type": field.relationship_type,
        "back_populates": field.back_populates,
        "backref": field.backref,
        "association_table": field.association_table,
        "relationship_key": field.relationship_key,
        "cascade_delete": field.cascade_delete,
        "passive_deletes": field.passive_deletes,
        "format": field.format,
        "validators": list(field.validators),
    }


def _module_state(module: ModuleDefinition) -> dict[str, Any]:
    return {
        "name": module.name,
        "class_name": module.class_name,
        "module_name": module.module_name,
        "table_name": module.table_name,
        "fields": [_field_state(field) for field in sorted(module.fields, key=lambda f: f.name)],
        "indexes": [_index_state(value) for value in sorted(module.indexes, key=lambda i: i.name)],
        "unique_constraints": [
            {"name": value.name, "columns": list(value.columns)}
            for value in sorted(module.unique_constraints, key=lambda c: c.name)
        ],
        "check_constraints": [
            {"name": value.name, "expression": value.expression}
            for value in sorted(module.check_constraints, key=lambda c: c.name)
        ],
        "soft_delete": module.soft_delete,
        "audit_fields": _audit_state(module),
        "version_column": module.version_column,
    }


def _index_state(index) -> dict[str, Any]:
    return {
        "name": index.name,
        "columns": list(index.columns),
        "where": index.where,
        "unique": index.unique,
        "expressions": None if index.expressions is None else list(index.expressions),
    }


def _audit_state(module: ModuleDefinition) -> dict[str, Any] | None:
    value = module.audit_fields
    if value is None:
        return None
    return {
        "target": value.target,
        "python_type": value.python_type,
        "sqlalchemy_type": value.sqlalchemy_type,
    }


def _change(kind, safety, target, before, after, rationale):
    return SchemaChange(kind, safety, target, before, after, rationale)


_RELATIONSHIP_ATTRIBUTES = (
    "relationship_name", "relationship_class", "relationship_table",
    "relationship_type", "back_populates", "backref", "association_table",
    "relationship_key", "cascade_delete", "passive_deletes",
)
_OTHER_FIELD_ATTRIBUTES = (
    "primary_key", "max_length", "minimum", "maximum", "min_length",
    "pattern", "computed_expression", "computed_sql", "hybrid_expression",
    "hybrid_python", "hybrid_class", "hybrid_references", "format", "validators",
)


def _field_changes(before_field, after_field) -> list[SchemaChange]:
    before = _field_state(before_field)
    after = _field_state(after_field)
    target = f"field:{before_field.name}"
    changes = []

    old_type = {key: before[key] for key in ("python_type", "sqlalchemy_type", "type_arguments")}
    new_type = {key: after[key] for key in ("python_type", "sqlalchemy_type", "type_arguments")}
    if old_type != new_type:
        changes.append(_change(ChangeKind.FIELD_TYPE_CHANGED, SafetyClassification.POTENTIALLY_DESTRUCTIVE, target, old_type, new_type, "Type changes can truncate, reinterpret, or reject existing values."))
    if before["nullable"] != after["nullable"]:
        safety = SafetyClassification.SAFE_ADDITIVE if after["nullable"] else SafetyClassification.REQUIRES_DATA_MIGRATION
        changes.append(_change(ChangeKind.NULLABLE_CHANGED, safety, target, before["nullable"], after["nullable"], "Allowing null is additive; requiring values needs an existing-data precondition."))
    if before["unique"] != after["unique"]:
        safety = SafetyClassification.REQUIRES_DATA_MIGRATION if after["unique"] else SafetyClassification.POTENTIALLY_DESTRUCTIVE
        changes.append(_change(ChangeKind.UNIQUE_CHANGED, safety, target, before["unique"], after["unique"], "Uniqueness additions require proof about existing rows; removal weakens a data invariant."))
    if before["index"] != after["index"]:
        kind = ChangeKind.FIELD_INDEX_ADDED if after["index"] else ChangeKind.FIELD_INDEX_REMOVED
        safety = SafetyClassification.SAFE_ADDITIVE if after["index"] else SafetyClassification.POTENTIALLY_DESTRUCTIVE
        changes.append(_change(kind, safety, target, before["index"], after["index"], "Index creation preserves row values; removal requires explicit review."))
    if before["default"] != after["default"]:
        changes.append(_change(ChangeKind.DEFAULT_CHANGED, SafetyClassification.REQUIRES_DATA_MIGRATION, target, before["default"], after["default"], "Default changes require an explicit database migration policy."))
    if (before["enum_name"], before["enum_values"]) != (after["enum_name"], after["enum_values"]):
        old_values = before["enum_values"] or []
        new_values = after["enum_values"] or []
        safety = SafetyClassification.SAFE_ADDITIVE if old_values and new_values[:len(old_values)] == old_values else SafetyClassification.POTENTIALLY_DESTRUCTIVE
        changes.append(_change(ChangeKind.ENUM_CHANGED, safety, target, {"name": before["enum_name"], "values": before["enum_values"]}, {"name": after["enum_name"], "values": after["enum_values"]}, "Only append-only enum evolution is safely additive."))
    if before["foreign_key"] != after["foreign_key"]:
        if before["foreign_key"] is None:
            kind, safety = ChangeKind.FOREIGN_KEY_ADDED, SafetyClassification.REQUIRES_DATA_MIGRATION
        elif after["foreign_key"] is None:
            kind, safety = ChangeKind.FOREIGN_KEY_REMOVED, SafetyClassification.POTENTIALLY_DESTRUCTIVE
        else:
            kind, safety = ChangeKind.FOREIGN_KEY_CHANGED, SafetyClassification.POTENTIALLY_DESTRUCTIVE
        changes.append(_change(kind, safety, target, before["foreign_key"], after["foreign_key"], "Foreign-key changes require existing-data validation and explicit referential policy."))
    old_relationship = {key: before[key] for key in _RELATIONSHIP_ATTRIBUTES}
    new_relationship = {key: after[key] for key in _RELATIONSHIP_ATTRIBUTES}
    if old_relationship != new_relationship:
        changes.append(_change(ChangeKind.RELATIONSHIP_CHANGED, SafetyClassification.REQUIRES_DATA_MIGRATION, target, old_relationship, new_relationship, "Relationship semantics affect generated ORM and referential behavior."))
    old_encryption = {key: before[key] for key in ("encrypted", "encryption_key_env")}
    new_encryption = {key: after[key] for key in ("encrypted", "encryption_key_env")}
    if old_encryption != new_encryption:
        safety = SafetyClassification.POTENTIALLY_DESTRUCTIVE if before["encrypted"] and not after["encrypted"] else SafetyClassification.REQUIRES_DATA_MIGRATION
        changes.append(_change(ChangeKind.ENCRYPTED_METADATA_CHANGED, safety, target, old_encryption, new_encryption, "Encryption changes require explicit transformation and must never be silently downgraded."))
    old_other = {key: before[key] for key in _OTHER_FIELD_ATTRIBUTES}
    new_other = {key: after[key] for key in _OTHER_FIELD_ATTRIBUTES}
    if old_other != new_other:
        changes.append(_change(ChangeKind.FIELD_METADATA_CHANGED, SafetyClassification.UNSUPPORTED, target, old_other, new_other, "This field metadata transition has no executable migration policy yet."))
    return changes


def _named_changes(before_values, after_values, state, added_kind, removed_kind, prefix):
    old = {value.name: state(value) for value in before_values}
    new = {value.name: state(value) for value in after_values}
    changes = []
    for name in sorted(old.keys() - new.keys()):
        changes.append(_change(removed_kind, SafetyClassification.POTENTIALLY_DESTRUCTIVE, f"{prefix}:{name}", old[name], None, "Removal requires explicit authorization."))
    for name in sorted(new.keys() - old.keys()):
        changes.append(_change(added_kind, SafetyClassification.REQUIRES_DATA_MIGRATION, f"{prefix}:{name}", None, new[name], "Existing data must satisfy the new database invariant."))
    for name in sorted(old.keys() & new.keys()):
        if old[name] != new[name]:
            changes.append(_change(removed_kind, SafetyClassification.POTENTIALLY_DESTRUCTIVE, f"{prefix}:{name}", old[name], None, "A changed definition removes the old database object first and requires policy."))
            changes.append(_change(added_kind, SafetyClassification.REQUIRES_DATA_MIGRATION, f"{prefix}:{name}", None, new[name], "A changed definition creates a new database invariant after validation."))
    return changes


def plan_schema_evolution(previous: ModuleDefinition | None, proposed: ModuleDefinition | None) -> SchemaEvolutionPlan:
    """Validate both inputs and return a stable, machine-readable change plan."""

    if previous is None and proposed is None:
        raise ValueError("At least one module definition is required.")
    if previous is not None:
        validate_module_definition(previous)
    if proposed is not None:
        validate_module_definition(proposed)
    module = proposed or previous
    assert module is not None
    if previous is None:
        return SchemaEvolutionPlan(module.name, (_change(ChangeKind.MODULE_ADDED, SafetyClassification.SAFE_ADDITIVE, f"module:{module.name}", None, _module_state(module), "A new module is additive."),))
    if proposed is None:
        return SchemaEvolutionPlan(module.name, (_change(ChangeKind.MODULE_REMOVED, SafetyClassification.POTENTIALLY_DESTRUCTIVE, f"module:{module.name}", _module_state(module), None, "Dropping a module can destroy all table data."),))
    if previous.name != proposed.name:
        raise ValueError("Schema evolution requires matching module identities.")

    changes = []
    old_fields = {field.name: field for field in previous.fields}
    new_fields = {field.name: field for field in proposed.fields}
    for name in sorted(old_fields.keys() - new_fields.keys()):
        changes.append(_change(ChangeKind.FIELD_REMOVED, SafetyClassification.POTENTIALLY_DESTRUCTIVE, f"field:{name}", _field_state(old_fields[name]), None, "Dropping a field can permanently destroy stored data."))
    for name in sorted(new_fields.keys() - old_fields.keys()):
        field = new_fields[name]
        safety = SafetyClassification.SAFE_ADDITIVE if field.nullable or field.default is not None else SafetyClassification.REQUIRES_DATA_MIGRATION
        changes.append(_change(ChangeKind.FIELD_ADDED, safety, f"field:{name}", None, _field_state(field), "Nullable or safely defaulted additions are additive; otherwise existing rows require a backfill."))
    for name in sorted(old_fields.keys() & new_fields.keys()):
        changes.extend(_field_changes(old_fields[name], new_fields[name]))

    changes.extend(_named_changes(previous.indexes, proposed.indexes, _index_state, ChangeKind.INDEX_ADDED, ChangeKind.INDEX_REMOVED, "index"))
    constraint_state = lambda value: asdict(value)
    changes.extend(_named_changes(previous.unique_constraints, proposed.unique_constraints, constraint_state, ChangeKind.CONSTRAINT_ADDED, ChangeKind.CONSTRAINT_REMOVED, "constraint"))
    changes.extend(_named_changes(previous.check_constraints, proposed.check_constraints, constraint_state, ChangeKind.CONSTRAINT_ADDED, ChangeKind.CONSTRAINT_REMOVED, "constraint"))
    if _audit_state(previous) != _audit_state(proposed):
        changes.append(_change(ChangeKind.AUDIT_METADATA_CHANGED, SafetyClassification.REQUIRES_DATA_MIGRATION, "module:audit", _audit_state(previous), _audit_state(proposed), "Audit columns and actor references require explicit existing-data handling."))
    if previous.version_column != proposed.version_column:
        changes.append(_change(ChangeKind.VERSION_METADATA_CHANGED, SafetyClassification.REQUIRES_DATA_MIGRATION, "module:version", previous.version_column, proposed.version_column, "Optimistic-version columns require deterministic initialization or explicit removal policy."))
    if previous.soft_delete != proposed.soft_delete:
        safety = SafetyClassification.SAFE_ADDITIVE if proposed.soft_delete else SafetyClassification.POTENTIALLY_DESTRUCTIVE
        changes.append(_change(ChangeKind.SOFT_DELETE_CHANGED, safety, "module:soft_delete", previous.soft_delete, proposed.soft_delete, "Adding soft-delete metadata is additive; removing it changes deletion semantics."))

    changes.sort(key=lambda value: (value.target, value.kind.value, value.safety.value))
    return SchemaEvolutionPlan(proposed.name, tuple(changes))
