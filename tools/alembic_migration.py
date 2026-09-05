"""Fail-closed deterministic Alembic generation from schema evolution plans."""

import ast
from dataclasses import dataclass, field
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


class UnsafeMigrationError(ValueError):
    """The plan needs a policy or operation not safely supported yet."""


@dataclass(frozen=True)
class MigrationPolicy:
    authorized_index_removals: tuple[str, ...] = field(default_factory=tuple)
    verified_data_preconditions: tuple[str, ...] = field(default_factory=tuple)

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

    def canonical_dict(self):
        return {
            "authorized_index_removals": sorted(self.authorized_index_removals),
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
_DIGEST = re.compile(r"[0-9a-f]{64}")
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
    for change in plan.changes:
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
                raise UnsafeMigrationError(f"{change.target} requires a backfill policy before adding a required column.")
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


def write_alembic_migration(directory: Path, migration: AlembicMigration) -> Path:
    if not isinstance(migration, AlembicMigration):
        raise ValueError("Migration output must be an AlembicMigration.")
    if (
        not valid_public_identifier(migration.module)
        or not _REVISION.fullmatch(migration.revision)
        or not _DIGEST.fullmatch(migration.plan_sha256)
        or migration.down_revision is not None
        and not _REVISION.fullmatch(migration.down_revision)
        or not isinstance(migration.content, str)
    ):
        raise ValueError("Migration artifact metadata is invalid.")
    directory = Path(directory).resolve()
    output = (directory / migration.filename).resolve()
    try:
        output.relative_to(directory)
    except ValueError as error:
        raise ValueError("Migration output path escapes its directory.") from error
    write_text_atomic(output, migration.content)
    return output
