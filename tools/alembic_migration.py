"""Fail-closed deterministic Alembic generation from schema evolution plans."""

import ast
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from tools.core.engine import write_text_atomic
from tools.core.constraint_parser import constraint_name
from tools.core.field_parser import Field
from tools.core.module_definition import (
    CheckRule, CompositeIndex, ModuleDefinition, UniqueTogether,
    _validate_normalized_sql, valid_public_identifier, validate_module_definition,
)
from tools.schema_evolution import ChangeKind, SchemaEvolutionPlan
from tools.type_evolution import TypeCompatibility, added_enum_values, classify_type_transition


class UnsafeMigrationError(ValueError):
    """The plan needs a policy or operation not safely supported yet."""


class TransformKind(str, Enum):
    LITERAL = "literal"
    COPY_FIELD = "copy_field"
    LOWER = "lower"
    UPPER = "upper"
    TRIM = "trim"


class AssertionKind(str, Enum):
    ROW_COUNT = "row_count"
    NULL_COUNT = "null_count"
    UNIQUE = "unique"


@dataclass(frozen=True)
class DataTransform:
    kind: TransformKind
    value: str | int | float | bool | None = None
    source_field: str | None = None

    def __post_init__(self):
        if not isinstance(self.kind, TransformKind):
            raise ValueError("Transformation kind must be allowlisted.")
        if self.kind == TransformKind.LITERAL:
            if self.source_field is not None or type(self.value) not in {str, int, float, bool, type(None)}:
                raise ValueError("Literal transformations accept one scalar value.")
            if isinstance(self.value, str) and (len(self.value) > 4096 or any(ord(c) < 32 for c in self.value)):
                raise ValueError("Literal transformation strings must be bounded and printable.")
            if isinstance(self.value, float) and not math.isfinite(self.value):
                raise ValueError("Literal transformation numbers must be finite.")
        elif self.value is not None or not valid_public_identifier(self.source_field):
            raise ValueError("Field transformations require one safe source field.")

    def canonical_dict(self):
        return {"kind": self.kind.value, "source_field": self.source_field, "value": self.value}


@dataclass(frozen=True)
class BackfillPolicy:
    target_field: str
    transform: DataTransform

    def __post_init__(self):
        if not valid_public_identifier(self.target_field) or not isinstance(self.transform, DataTransform):
            raise ValueError("Backfill policy fields and transformations must be validated.")
        if self.transform.source_field == self.target_field:
            raise ValueError("A backfill cannot read from its own new target field.")

    def canonical_dict(self):
        return {"target_field": self.target_field, "transform": self.transform.canonical_dict()}


@dataclass(frozen=True)
class DataAssertion:
    kind: AssertionKind
    fields: tuple[str, ...] = field(default_factory=tuple)
    expected_count: int = 0

    def __post_init__(self):
        if not isinstance(self.kind, AssertionKind):
            raise ValueError("Assertion kind must be allowlisted.")
        if not isinstance(self.fields, tuple) or not self.fields or any(not valid_public_identifier(v) for v in self.fields):
            raise ValueError("Assertions require safe field identifiers.")
        if self.kind != AssertionKind.UNIQUE and len(self.fields) != 1:
            raise ValueError("Count assertions require exactly one field.")
        if type(self.expected_count) is not int or self.expected_count < 0 or self.expected_count > 2**63 - 1:
            raise ValueError("Assertion counts must be bounded non-negative integers.")

    def canonical_dict(self):
        return {"expected_count": self.expected_count, "fields": list(self.fields), "kind": self.kind.value}


@dataclass(frozen=True)
class MigrationPolicy:
    authorized_index_removals: tuple[str, ...] = field(default_factory=tuple)
    verified_data_preconditions: tuple[str, ...] = field(default_factory=tuple)
    backfills: tuple[BackfillPolicy, ...] = field(default_factory=tuple)
    assertions: tuple[DataAssertion, ...] = field(default_factory=tuple)

    def __post_init__(self):
        for values, label in (
            (self.authorized_index_removals, "index-removal authorization"),
            (self.verified_data_preconditions, "data precondition"),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value or len(value) > 256
                for value in values
            ):
                raise ValueError(f"Migration {label} entries must be bounded strings.")
            if len(set(values)) != len(values):
                raise ValueError(f"Migration {label} entries must be unique.")
        if not isinstance(self.backfills, tuple) or any(not isinstance(v, BackfillPolicy) for v in self.backfills):
            raise ValueError("Migration backfills must be immutable BackfillPolicy values.")
        if len({v.target_field for v in self.backfills}) != len(self.backfills):
            raise ValueError("Migration backfills must have unique targets.")
        if not isinstance(self.assertions, tuple) or any(not isinstance(v, DataAssertion) for v in self.assertions):
            raise ValueError("Migration assertions must be immutable DataAssertion values.")

    def canonical_dict(self):
        return {
            "authorized_index_removals": sorted(self.authorized_index_removals),
            "assertions": [v.canonical_dict() for v in sorted(self.assertions, key=lambda x: (x.kind.value, x.fields, x.expected_count))],
            "backfills": [v.canonical_dict() for v in sorted(self.backfills, key=lambda x: x.target_field)],
            "verified_data_preconditions": sorted(self.verified_data_preconditions),
        }


@dataclass(frozen=True)
class AlembicMigration:
    module: str
    revision: str
    down_revision: str | None
    plan_sha256: str
    content: str

    @property
    def filename(self) -> str:
        return f"{self.revision}_{self.module}_schema_evolution.py"


_REVISION = re.compile(r"[0-9a-f]{12}")
_TARGET = re.compile(r"(?:module|field|index|constraint):([A-Za-z][A-Za-z0-9_]*)")


def _module_from_state(state):
    if not isinstance(state, dict):
        raise ValueError("Module plan state must be a mapping.")
    audit = state.get("audit_fields")
    if audit is not None:
        from tools.core.audit_field_parser import AuditFieldDefinition
        audit = AuditFieldDefinition(**audit)
    module = ModuleDefinition(
        name=state.get("name"), class_name=state.get("class_name"),
        module_name=state.get("module_name"), table_name=state.get("table_name"),
        fields=[Field(**value) for value in state.get("fields", [])],
        indexes=[CompositeIndex(**value) for value in state.get("indexes", [])],
        soft_delete=state.get("soft_delete", False),
        unique_constraints=[UniqueTogether(**value) for value in state.get("unique_constraints", [])],
        check_constraints=[CheckRule(**value) for value in state.get("check_constraints", [])],
        audit_fields=audit, version_column=state.get("version_column", False),
    )
    validate_module_definition(module)
    return module


def _validate_constraint_state(state, table):
    if not isinstance(state, dict) or not valid_public_identifier(state.get("name")):
        raise ValueError("Constraint plan state contains an invalid name.")
    if "columns" in state:
        columns = state["columns"]
        if not isinstance(columns, list) or len(columns) < 2 or any(
            not valid_public_identifier(value) for value in columns
        ):
            raise ValueError("Constraint plan state contains invalid columns.")
        expected = constraint_name(f"uq_{table}_{'_'.join(columns)}")
    else:
        expression = state.get("expression")
        columns = set(re.findall(r'"([A-Za-z][A-Za-z0-9_]*)"', expression or ""))
        _validate_normalized_sql(
            expression, columns, {"AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE"},
            "Migration check constraint",
        )
        expected = constraint_name(
            f"ck_{table}_{sha256(expression.encode('utf-8')).hexdigest()[:10]}"
        )
    if state["name"] != expected:
        raise ValueError("Constraint plan state is not canonical.")


def _validate_plan(plan):
    table = f"{plan.module.lower()}s"
    for change in plan.changes:
        match = _TARGET.fullmatch(change.target)
        if match is None:
            raise ValueError("Migration plan contains a non-canonical target.")
        if change.kind == ChangeKind.MODULE_ADDED:
            module = _module_from_state(change.after)
            if module.name != plan.module:
                raise ValueError("Migration plan module state does not match its identity.")
        elif change.kind == ChangeKind.FIELD_ADDED:
            if not isinstance(change.after, dict) or change.after.get("name") != match.group(1):
                raise ValueError("Added-field plan state does not match its target.")
            candidate = ModuleDefinition(
                plan.module, plan.module.capitalize(), plan.module.lower(), table,
                [Field(**change.after)],
            )
            validate_module_definition(candidate)
        elif change.kind in {ChangeKind.INDEX_ADDED, ChangeKind.INDEX_REMOVED}:
            state = change.after if change.after is not None else change.before
            if not isinstance(state, dict) or state.get("name") != match.group(1):
                raise ValueError("Index plan state does not match its target.")
            candidate = CompositeIndex(**state)
            if not valid_public_identifier(candidate.name) or any(
                not valid_public_identifier(column) for column in candidate.columns
            ):
                raise ValueError("Index plan state contains invalid identifiers.")
        elif change.kind == ChangeKind.CONSTRAINT_ADDED:
            _validate_constraint_state(change.after, table)
        elif change.kind == ChangeKind.FOREIGN_KEY_ADDED:
            from tools.core.field_parser import validate_foreign_key_target
            validate_foreign_key_target(match.group(1), change.after)
        elif change.kind == ChangeKind.FIELD_TYPE_CHANGED:
            classify_type_transition(change)
        elif change.kind == ChangeKind.ENUM_CHANGED:
            from tools.core.field_parser import validate_enum_values
            added_enum_values(change)
            validate_enum_values(match.group(1), change.before["values"])
            validate_enum_values(match.group(1), change.after["values"])


def _require_precondition(policy: MigrationPolicy, target: str):
    if target not in policy.verified_data_preconditions:
        raise UnsafeMigrationError(
            f"{target} requires a verified existing-data precondition."
        )


def _sql_literal(default):
    if not isinstance(default, str):
        raise UnsafeMigrationError("Migration defaults must use validated string metadata.")
    try:
        value = ast.literal_eval(default)
    except (SyntaxError, ValueError) as error:
        raise UnsafeMigrationError(
            "Callable or expression defaults are not supported for migrations."
        ) from error
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise UnsafeMigrationError("Migration numeric defaults must be finite.")
        return repr(value)
    if isinstance(value, str):
        if any(ord(character) < 32 for character in value):
            raise UnsafeMigrationError("Migration string defaults cannot contain control characters.")
        return "'" + value.replace("'", "''") + "'"
    raise UnsafeMigrationError("Only scalar literal migration defaults are supported.")


def _value_sql_literal(value):
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise UnsafeMigrationError("Backfill numeric values must be finite.")
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise UnsafeMigrationError("Unsupported backfill literal.")


def _backfill_expression(transform):
    if transform.kind == TransformKind.LITERAL:
        return _value_sql_literal(transform.value)
    source = f'"{transform.source_field}"'
    if transform.kind == TransformKind.COPY_FIELD:
        return source
    functions = {
        TransformKind.LOWER: "lower",
        TransformKind.UPPER: "upper",
        TransformKind.TRIM: "btrim",
    }
    return f"{functions[transform.kind]}({source})"


def _assertion_sql(table, assertion):
    if assertion.kind == AssertionKind.ROW_COUNT:
        query = f'SELECT count(*) FROM "{table}"'
    elif assertion.kind == AssertionKind.NULL_COUNT:
        query = f'SELECT count(*) FROM "{table}" WHERE "{assertion.fields[0]}" IS NULL'
    else:
        columns = ", ".join(f'"{value}"' for value in assertion.fields)
        query = (
            f'SELECT count(*) FROM (SELECT {columns} FROM "{table}" '
            f'GROUP BY {columns} HAVING count(*) > 1) AS duplicates'
        )
    message = f"ArcaCore migration assertion failed: {assertion.kind.value}:{','.join(assertion.fields)}"
    return (
        "op.execute(sa.text(" + repr(
            "DO $arcacore$ BEGIN IF (" + query + f") <> {assertion.expected_count} "
            + "THEN RAISE EXCEPTION '" + message + "'; END IF; END; $arcacore$"
        ) + "))"
    )


def _type_expression(state):
    python_type = state["python_type"]
    if python_type == "str":
        length = state.get("max_length")
        return f"sa.String(length={length})" if length is not None else "sa.String()"
    if python_type == "decimal":
        precision, scale = (int(value) for value in state["type_arguments"])
        return f"sa.Numeric(precision={precision}, scale={scale})"
    if python_type == "enum":
        values = ", ".join(repr(value) for value in state["enum_values"])
        return f"sa.Enum({values}, name={state['enum_name'].lower()!r})"
    if python_type == "array":
        elements = {
            "str": "sa.String()", "int": "sa.Integer()", "float": "sa.Float()",
            "bool": "sa.Boolean()", "datetime": "sa.DateTime()", "date": "sa.Date()",
            "text": "sa.Text()", "uuid": "sa.Uuid()", "json": "sa.JSON()",
        }
        element = elements.get(state["type_arguments"][0])
        if element is None:
            raise UnsafeMigrationError("Unsupported array element type in migration plan.")
        return f"sa.ARRAY({element})"
    expressions = {
        "int": "sa.Integer()", "float": "sa.Float()", "bool": "sa.Boolean()",
        "datetime": "sa.DateTime()", "date": "sa.Date()", "text": "sa.Text()",
        "uuid": "sa.Uuid()", "json": "sa.JSON()",
    }
    expression = expressions.get(python_type)
    if expression is None:
        raise UnsafeMigrationError(f"Unsupported migration column type: {python_type}")
    return expression


def _column_expression(state, *, include_foreign_key=False):
    options = []
    if include_foreign_key and state.get("foreign_key"):
        options.append(f"sa.ForeignKey({state['foreign_key']!r})")
    options.append(f"nullable={state['nullable']!r}")
    if state.get("primary_key"):
        options.append("primary_key=True")
    if state.get("unique"):
        options.append("unique=True")
    if state.get("default") is not None:
        options.append(f"server_default=sa.text({_sql_literal(state['default'])!r})")
    stored_type = "sa.Text()" if state.get("encrypted") else _type_expression(state)
    return f"sa.Column({state['name']!r}, {stored_type}, {', '.join(options)})"


def _index_create(state, table):
    if state.get("where") is not None or state.get("expressions") is not None:
        raise UnsafeMigrationError("Partial and expression index migrations are not supported yet.")
    return f"op.create_index({state['name']!r}, {table!r}, {state['columns']!r}, unique={state['unique']!r})"


def _constraint_add(state, table):
    if "columns" in state:
        return f"op.create_unique_constraint({state['name']!r}, {table!r}, {state['columns']!r})"
    return f"op.create_check_constraint({state['name']!r}, {table!r}, {state['expression']!r})"


def _render_operations(plan, policy):
    table = f"{plan.module.lower()}s"
    upgrade, downgrade = [], []
    fk_targets = {change.target for change in plan.changes if change.kind == ChangeKind.FOREIGN_KEY_ADDED}
    priorities = {
        ChangeKind.MODULE_ADDED: 0,
        ChangeKind.INDEX_REMOVED: 10,
        ChangeKind.FIELD_INDEX_REMOVED: 10,
        ChangeKind.FIELD_ADDED: 20,
        ChangeKind.FIELD_TYPE_CHANGED: 25,
        ChangeKind.ENUM_CHANGED: 25,
        ChangeKind.DEFAULT_CHANGED: 30,
        ChangeKind.FOREIGN_KEY_ADDED: 40,
        ChangeKind.RELATIONSHIP_CHANGED: 41,
        ChangeKind.UNIQUE_CHANGED: 50,
        ChangeKind.CONSTRAINT_ADDED: 50,
        ChangeKind.FIELD_INDEX_ADDED: 60,
        ChangeKind.INDEX_ADDED: 60,
    }
    ordered_changes = sorted(
        plan.changes,
        key=lambda value: (priorities.get(value.kind, 100), value.target, value.kind.value),
    )
    backfills = {value.target_field: value for value in policy.backfills}
    required_additions = {
        change.target.split(":", 1)[1]
        for change in plan.changes
        if change.kind == ChangeKind.FIELD_ADDED
        and not change.after["nullable"]
        and change.after.get("default") is None
    }
    if set(backfills) != required_additions:
        missing = sorted(required_additions - set(backfills))
        extra = sorted(set(backfills) - required_additions)
        detail = f"missing={missing}, incompatible={extra}"
        raise UnsafeMigrationError(f"Required-field backfill policy mismatch: {detail}")
    upgrade.extend(_assertion_sql(table, value) for value in sorted(
        policy.assertions, key=lambda x: (x.kind.value, x.fields, x.expected_count)
    ))
    for change in ordered_changes:
        kind = change.kind
        if kind == ChangeKind.MODULE_ADDED:
            state = change.after
            for value in state["fields"]:
                if (
                    value["python_type"] == "many_to_many"
                    or value["computed_expression"] is not None
                    or value["hybrid_expression"] is not None
                    or value["python_type"] == "enum"
                ):
                    raise UnsafeMigrationError(
                        "New-module migrations do not yet support collection, computed, hybrid, or enum fields."
                    )
            columns = [_column_expression(value, include_foreign_key=True) for value in state["fields"]]
            if not any(value["primary_key"] for value in state["fields"]):
                columns.insert(0, "sa.Column('id', sa.Integer(), nullable=False, primary_key=True)")
            columns.extend([
                "sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))",
                "sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))",
            ])
            if state["soft_delete"]:
                columns.append("sa.Column('deleted_at', sa.DateTime(), nullable=True)")
            if state["audit_fields"] is not None:
                actor_type = {"int": "sa.Integer()", "str": "sa.String()", "uuid": "sa.Uuid()"}[state["audit_fields"]["python_type"]]
                columns.extend([
                    f"sa.Column('created_by', {actor_type}, nullable=True)",
                    f"sa.Column('updated_by', {actor_type}, nullable=True)",
                ])
            if state["version_column"]:
                columns.append("sa.Column('version_id', sa.Integer(), nullable=False, server_default=sa.text('1'))")
            columns.extend(
                f"sa.UniqueConstraint({', '.join(repr(column) for column in value['columns'])}, name={value['name']!r})"
                for value in state["unique_constraints"]
            )
            columns.extend(
                f"sa.CheckConstraint({value['expression']!r}, name={value['name']!r})"
                for value in state["check_constraints"]
            )
            upgrade.append(f"op.create_table({state['table_name']!r},\n        " + ",\n        ".join(columns) + ",\n    )")
            upgrade.extend(_index_create(value, state["table_name"]) for value in state["indexes"])
            downgrade.insert(0, f"op.drop_table({state['table_name']!r})")
        elif kind == ChangeKind.FIELD_ADDED:
            state = change.after
            if not state["nullable"] and state.get("default") is None:
                backfill = backfills[state["name"]]
                nullable_state = dict(state)
                nullable_state["nullable"] = True
                upgrade.append(f"op.add_column({table!r}, {_column_expression(nullable_state)})")
                expression = _backfill_expression(backfill.transform)
                update_sql = (
                    f'UPDATE "{table}" SET "{state["name"]}" = {expression} '
                    f'WHERE "{state["name"]}" IS NULL'
                )
                upgrade.append(f"op.execute(sa.text({update_sql!r}))")
                required_assertion = DataAssertion(AssertionKind.NULL_COUNT, (state["name"],), 0)
                upgrade.append(_assertion_sql(table, required_assertion))
                upgrade.append(f"op.alter_column({table!r}, {state['name']!r}, nullable=False)")
                downgrade.insert(0, f"op.drop_column({table!r}, {state['name']!r})")
                continue
            if state.get("unique") or state.get("foreign_key"):
                _require_precondition(policy, change.target)
            upgrade.append(f"op.add_column({table!r}, {_column_expression(state)})")
            if state.get("foreign_key"):
                target_table, target_column = state["foreign_key"].split(".")
                name = f"fk_{table}_{state['name']}_{target_table}"
                upgrade.append(f"op.create_foreign_key({name!r}, {table!r}, {target_table!r}, {[state['name']]!r}, {[target_column]!r})")
            if state.get("index"):
                name = f"ix_{table}_{state['name']}"
                upgrade.append(f"op.create_index({name!r}, {table!r}, {[state['name']]!r}, unique=False)")
            downgrade.insert(0, f"op.drop_column({table!r}, {state['name']!r})")
        elif kind == ChangeKind.FIELD_TYPE_CHANGED:
            decision = classify_type_transition(change)
            if decision.classification != TypeCompatibility.SAFE_WIDENING:
                raise UnsafeMigrationError(
                    f"Type transition is not an approved safe widening: {change.target} "
                    f"({decision.classification.value})"
                )
            field_name = change.target.split(":", 1)[1]
            old_type = _type_expression(change.before)
            new_type = _type_expression(change.after)
            upgrade.append(
                f"op.alter_column({table!r}, {field_name!r}, "
                f"existing_type={old_type}, type_={new_type})"
            )
            downgrade.insert(0, (
                f"raise RuntimeError({f'Downgrade requires validated data-fit precondition: {change.target}'!r})"
            ))
        elif kind == ChangeKind.ENUM_CHANGED:
            values = added_enum_values(change)
            enum_name = change.after["name"].lower()
            for value in values:
                sql = f'ALTER TYPE "{enum_name}" ADD VALUE IF NOT EXISTS \'{value}\''
                upgrade.append(f"op.execute(sa.text({sql!r}))")
            downgrade.insert(0, f"raise RuntimeError({f'Enum value removal is not safely reversible: {change.target}'!r})")
        elif kind in {ChangeKind.FIELD_INDEX_ADDED, ChangeKind.INDEX_ADDED}:
            state = change.after
            if kind == ChangeKind.FIELD_INDEX_ADDED:
                field_name = change.target.split(":", 1)[1]
                state = {"name": f"ix_{table}_{field_name}", "columns": [field_name], "unique": False, "where": None, "expressions": None}
            upgrade.append(_index_create(state, table))
            downgrade.insert(0, f"op.drop_index({state['name']!r}, table_name={table!r})")
        elif kind in {ChangeKind.FIELD_INDEX_REMOVED, ChangeKind.INDEX_REMOVED}:
            state = change.before
            if kind == ChangeKind.FIELD_INDEX_REMOVED:
                field_name = change.target.split(":", 1)[1]
                state = {"name": f"ix_{table}_{field_name}", "columns": [field_name], "unique": False, "where": None, "expressions": None}
            if state["name"] not in policy.authorized_index_removals:
                raise UnsafeMigrationError(f"Index removal is not authorized: {state['name']}")
            upgrade.append(f"op.drop_index({state['name']!r}, table_name={table!r})")
            downgrade.insert(0, _index_create(state, table))
        elif kind == ChangeKind.CONSTRAINT_ADDED:
            _require_precondition(policy, change.target)
            state = change.after
            upgrade.append(_constraint_add(state, table))
            constraint_type = "unique" if "columns" in state else "check"
            downgrade.insert(0, f"op.drop_constraint({state['name']!r}, {table!r}, type_={constraint_type!r})")
        elif kind == ChangeKind.FOREIGN_KEY_ADDED:
            _require_precondition(policy, change.target)
            field_name = change.target.split(":", 1)[1]
            target_table, target_column = change.after.split(".")
            name = f"fk_{table}_{field_name}_{target_table}"
            upgrade.append(f"op.create_foreign_key({name!r}, {table!r}, {target_table!r}, {[field_name]!r}, {[target_column]!r})")
            downgrade.insert(0, f"op.drop_constraint({name!r}, {table!r}, type_='foreignkey')")
        elif kind == ChangeKind.RELATIONSHIP_CHANGED and change.target in fk_targets:
            continue
        elif kind == ChangeKind.UNIQUE_CHANGED and change.after is True:
            _require_precondition(policy, change.target)
            field_name = change.target.split(":", 1)[1]
            name = f"uq_{table}_{field_name}"
            upgrade.append(f"op.create_unique_constraint({name!r}, {table!r}, {[field_name]!r})")
            downgrade.insert(0, f"op.drop_constraint({name!r}, {table!r}, type_='unique')")
        elif kind == ChangeKind.DEFAULT_CHANGED:
            _require_precondition(policy, change.target)
            field_name = change.target.split(":", 1)[1]
            new_default = "None" if change.after is None else f"sa.text({_sql_literal(change.after)!r})"
            old_default = "None" if change.before is None else f"sa.text({_sql_literal(change.before)!r})"
            upgrade.append(f"op.alter_column({table!r}, {field_name!r}, server_default={new_default})")
            downgrade.insert(0, f"op.alter_column({table!r}, {field_name!r}, server_default={old_default})")
        else:
            raise UnsafeMigrationError(
                f"Unsupported or destructive migration operation: {kind.value} ({change.target})"
            )
    return upgrade, downgrade


def generate_alembic_migration(plan: SchemaEvolutionPlan, *, policy=None, down_revision=None):
    if not isinstance(plan, SchemaEvolutionPlan):
        raise ValueError("Migration input must be a SchemaEvolutionPlan.")
    if policy is None:
        policy = MigrationPolicy()
    if not isinstance(policy, MigrationPolicy):
        raise ValueError("Migration policy must be a MigrationPolicy.")
    if down_revision is not None and (not isinstance(down_revision, str) or not _REVISION.fullmatch(down_revision)):
        raise ValueError("down_revision must be a 12-character lowercase hexadecimal revision.")
    if plan.is_empty:
        raise UnsafeMigrationError("An empty schema plan does not need a migration.")
    _validate_plan(plan)
    upgrade, downgrade = _render_operations(plan, policy)
    plan_bytes = plan.canonical_json().encode("utf-8")
    plan_digest = sha256(plan_bytes).hexdigest()
    identity = json.dumps(
        {"plan_sha256": plan_digest, "policy": policy.canonical_dict(), "down_revision": down_revision},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    revision = sha256(b"arcacore-alembic/v1\0" + identity).hexdigest()[:12]
    indent = lambda values: "\n".join("    " + line.replace("\n", "\n    ") for line in values) or "    pass"
    content = (
        '"""Deterministic migration generated from an ArcaCore schema plan."""\n\n'
        "from alembic import op\nimport sqlalchemy as sa\n\n"
        f"revision = {revision!r}\n"
        f"down_revision = {down_revision!r}\n"
        "branch_labels = None\ndepends_on = None\n"
        f"plan_sha256 = {plan_digest!r}\n\n\n"
        "def upgrade():\n" + indent(upgrade) + "\n\n\n"
        "def downgrade():\n" + indent(downgrade) + "\n"
    )
    compile(content, "<generated-alembic-migration>", "exec")
    return AlembicMigration(plan.module, revision, down_revision, plan_digest, content)


def write_alembic_migration(
    directory: Path,
    plan: SchemaEvolutionPlan,
    *,
    policy: MigrationPolicy | None = None,
    down_revision: str | None = None,
) -> Path:
    """Validate, generate, and atomically write one migration.

    Accepting the plan rather than a caller-constructed artifact prevents the
    filesystem API from becoming a bypass around plan and payload validation.
    """

    migration = generate_alembic_migration(
        plan,
        policy=policy,
        down_revision=down_revision,
    )
    directory = Path(directory).resolve()
    output = (directory / migration.filename).resolve()
    try:
        output.relative_to(directory)
    except ValueError as error:
        raise ValueError("Migration output path escapes its directory.") from error
    write_text_atomic(output, migration.content)
    return output
