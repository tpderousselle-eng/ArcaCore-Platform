from dataclasses import dataclass, field as dataclass_field
from hashlib import sha256
import json
from keyword import iskeyword
from pathlib import Path
import re

from tools.core.audit_field_parser import AuditFieldDefinition, validate_audit_fields
from tools.core.field_parser import Field
from tools.core.version_column_parser import validate_version_column


@dataclass
class CompositeIndex:
    name: str
    columns: list[str]
    where: str | None = None
    unique: bool = False
    expressions: list[str] | None = None


@dataclass
class UniqueTogether:
    name: str
    columns: list[str]


@dataclass
class CheckRule:
    name: str
    expression: str


@dataclass
class ModuleDefinition:
    name: str
    class_name: str
    module_name: str
    table_name: str
    fields: list[Field]
    indexes: list[CompositeIndex] = dataclass_field(default_factory=list)
    soft_delete: bool = False
    unique_constraints: list[UniqueTogether] = dataclass_field(default_factory=list)
    check_constraints: list[CheckRule] = dataclass_field(default_factory=list)
    audit_fields: AuditFieldDefinition | None = None
    version_column: bool = False

    def __post_init__(self):
        validate_audit_fields(self.audit_fields, self.fields)
        validate_version_column(self.version_column, self.fields)
        if self.soft_delete:
            if any(
                field.name == "deleted_at" or field.relationship_name == "deleted_at"
                for field in self.fields
            ):
                raise ValueError("deleted_at is reserved when soft_delete is enabled.")
            if sum(field.primary_key for field in self.fields) > 1:
                raise ValueError("soft_delete requires a single primary key.")

    @property
    def primary_key_name(self) -> str:
        return next((field.name for field in self.fields if field.primary_key), "id")

    @property
    def has_relationships(self) -> bool:
        return any(field.relationship_name for field in self.fields)

    @property
    def has_primary_key(self) -> bool:
        return any(field.primary_key for field in self.fields)

    @property
    def has_uuid(self) -> bool:
        return any(field.sqlalchemy_type == "UUID" for field in self.fields)

    @property
    def has_enum(self) -> bool:
        return any(field.enum_name is not None for field in self.fields)

    @property
    def enums(self):
        enums = []
        seen = set()
        for field in self.fields:
            if not field.enum_name:
                continue
            if field.enum_name in seen:
                continue
            seen.add(field.enum_name)
            enums.append((field.enum_name, field.enum_values))
        return enums


def valid_public_identifier(value: str) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isidentifier()
        and not iskeyword(value)
        and not value.startswith("_")
    )


_SQL_TOKEN = re.compile(
    r'\s+|"([A-Za-z][A-Za-z0-9_]*)"|\'(?:[^\'\\]|\'\')*\'|'
    r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|'
    r'[A-Za-z][A-Za-z0-9_]*|<=|>=|!=|=|<|>|\+|-|\*|\(|\)'
)


def _validate_normalized_sql(value, columns: set[str], words: set[str], label: str):
    """Accept only tokens emitted by the restricted expression/check parsers."""

    if not isinstance(value, str) or not value or len(value) > 4000:
        raise ValueError(f"{label} must be a non-empty bounded SQL expression.")
    position = 0
    referenced = False
    for match in _SQL_TOKEN.finditer(value):
        if match.start() != position:
            raise ValueError(f"{label} contains unsupported SQL syntax.")
        position = match.end()
        token = match.group(0)
        identifier = match.group(1)
        if identifier is not None:
            if identifier not in columns:
                raise ValueError(f"{label} references an unknown column: {identifier}")
            referenced = True
        elif token[0].isalpha() and token.upper() not in words:
            raise ValueError(f"{label} contains an unsupported SQL keyword or function.")
    if position != len(value) or not referenced:
        raise ValueError(f"{label} must contain only supported SQL and reference a column.")


def _module_columns(module: ModuleDefinition) -> set[str]:
    columns = {
        field.name for field in module.fields
        if field.relationship_type != "many_to_many"
        and field.hybrid_expression is None
        and not field.encrypted
    }
    columns.update({"created_at", "updated_at"})
    if not any(field.primary_key for field in module.fields):
        columns.add("id")
    if module.soft_delete:
        columns.add("deleted_at")
    if module.audit_fields is not None:
        columns.update({"created_by", "updated_by"})
    if module.version_column:
        columns.add("version_id")
    return columns


def _validate_indexes_and_constraints(module: ModuleDefinition):
    from tools.core.constraint_parser import constraint_name

    columns = _module_columns(module)
    if not isinstance(module.indexes, list) or any(
        not isinstance(item, CompositeIndex) for item in module.indexes
    ):
        raise ValueError("Module indexes must be a list of CompositeIndex definitions.")
    if not isinstance(module.unique_constraints, list) or any(
        not isinstance(item, UniqueTogether) for item in module.unique_constraints
    ):
        raise ValueError("Module unique constraints must be UniqueTogether definitions.")
    if not isinstance(module.check_constraints, list) or any(
        not isinstance(item, CheckRule) for item in module.check_constraints
    ):
        raise ValueError("Module check constraints must be CheckRule definitions.")

    seen_names = set()
    for index in module.indexes:
        if (
            not isinstance(index.columns, list) or not index.columns
            or any(column not in columns for column in index.columns)
            or len(set(index.columns)) != len(index.columns)
            or type(index.unique) is not bool
        ):
            raise ValueError("Index metadata contains invalid columns or options.")
        if index.where is not None:
            _validate_normalized_sql(
                index.where, columns, {"AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE"},
                "Index predicate",
            )
        if index.expressions is not None:
            if not isinstance(index.expressions, list) or not index.expressions:
                raise ValueError("Expression index metadata requires expressions.")
            for expression in index.expressions:
                _validate_normalized_sql(
                    expression, columns, {"LOWER", "UPPER", "LENGTH", "ABS"},
                    "Index expression",
                )
        name = f"ix_{module.table_name}_{'_'.join(index.columns)}"
        if index.expressions is not None:
            digest = sha256(json.dumps(
                [index.expressions, index.where, index.unique], ensure_ascii=False
            ).encode("utf-8")).hexdigest()[:10]
            name += f"_expr_{digest}"
        elif index.where is not None:
            digest = sha256(json.dumps(
                [index.columns, index.where, index.unique], ensure_ascii=False
            ).encode("utf-8")).hexdigest()[:10]
            name += f"_partial_{digest}"
        if len(name.encode("utf-8")) > 63:
            digest = sha256(name.encode("utf-8")).hexdigest()[:10]
            prefix = name.encode("utf-8")[:52].decode("utf-8", errors="ignore")
            name = f"{prefix}_{digest}"
        if index.name != name or name in seen_names:
            raise ValueError("Index metadata has a non-canonical or duplicate name.")
        seen_names.add(name)

    seen_unique_columns = set()
    for constraint in module.unique_constraints:
        if (
            not isinstance(constraint.columns, list) or len(constraint.columns) < 2
            or any(column not in columns for column in constraint.columns)
            or len(set(constraint.columns)) != len(constraint.columns)
        ):
            raise ValueError("Unique constraint metadata contains invalid columns.")
        key = frozenset(constraint.columns)
        expected = constraint_name(
            f"uq_{module.table_name}_{'_'.join(constraint.columns)}"
        )
        if key in seen_unique_columns or constraint.name != expected or expected in seen_names:
            raise ValueError("Unique constraint metadata is duplicate or non-canonical.")
        seen_unique_columns.add(key)
        seen_names.add(expected)

    seen_checks = set()
    for constraint in module.check_constraints:
        _validate_normalized_sql(
            constraint.expression, columns,
            {"AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE"},
            "Check constraint",
        )
        expected = constraint_name(
            f"ck_{module.table_name}_{sha256(constraint.expression.encode('utf-8')).hexdigest()[:10]}"
        )
        if (
            constraint.expression in seen_checks
            or constraint.name != expected
            or expected in seen_names
        ):
            raise ValueError("Check constraint metadata is duplicate or non-canonical.")
        seen_checks.add(constraint.expression)
        seen_names.add(expected)


def validate_module_identity(module: ModuleDefinition):
    """Reject module metadata that could alter generated syntax or paths."""

    if not isinstance(module, ModuleDefinition):
        raise ValueError("Module metadata must be a ModuleDefinition.")
    if not valid_public_identifier(module.name):
        raise ValueError("Module name must be a public ASCII Python identifier.")
    expected = (module.name.capitalize(), module.name.lower(), f"{module.name.lower()}s")
    if (module.class_name, module.module_name, module.table_name) != expected:
        raise ValueError(
            "Module class, module, and table names must use canonical derived names."
        )


def validate_module_definition(module: ModuleDefinition):
    """Apply the authoritative validation boundary for every generator entry point."""

    validate_module_identity(module)
    if not isinstance(module.fields, list) or any(
        not isinstance(field, Field) for field in module.fields
    ):
        raise ValueError("Module fields must be a list of Field definitions.")

    # Lazy imports avoid the Field/module-definition import cycle.
    from tools.core.field_parser import (
        ARRAY_ELEMENT_TYPES,
        TYPE_MAP,
        validate_default,
        validate_enum_values,
        validate_foreign_key_target,
    )
    from tools.validators.field_validator import FieldValidator

    FieldValidator.validate(module.fields)
    identifier_attributes = (
        "relationship_name",
        "relationship_class",
        "relationship_table",
        "relationship_key",
        "association_table",
        "back_populates",
        "backref",
    )
    for field in module.fields:
        if field.python_type not in TYPE_MAP or field.sqlalchemy_type != TYPE_MAP[field.python_type]:
            raise ValueError(f"{field.name}: field type metadata is inconsistent.")
        if field.python_type == "decimal":
            arguments = field.type_arguments
            if (
                not isinstance(arguments, list)
                or len(arguments) != 2
                or any(
                    not isinstance(value, str) or not value.isascii() or not value.isdigit()
                    for value in arguments
                )
            ):
                raise ValueError(
                    f"{field.name}: decimal metadata requires numeric precision and scale."
                )
            precision, scale = map(int, arguments)
            if precision < 1 or scale > precision:
                raise ValueError(f"{field.name}: invalid decimal precision or scale.")
        if field.python_type == "array" and (
            not isinstance(field.type_arguments, list)
            or len(field.type_arguments) != 1
            or field.type_arguments[0] not in ARRAY_ELEMENT_TYPES
        ):
            raise ValueError(
                f"{field.name}: array metadata requires one supported element type."
            )
        if field.default is not None:
            validate_default(field.name, field.default)
        if field.foreign_key is not None:
            validate_foreign_key_target(field.name, field.foreign_key)
        if field.python_type == "enum":
            validate_enum_values(field.name, field.enum_values)
            expected_enum = f"{module.class_name}{field.name.capitalize()}"
            if field.enum_name != expected_enum or field.type_arguments != field.enum_values:
                raise ValueError(f"{field.name}: enum metadata is inconsistent.")
        for attribute in identifier_attributes:
            value = getattr(field, attribute)
            if value is not None and not valid_public_identifier(value):
                raise ValueError(f"{field.name}: invalid {attribute} metadata.")
    _validate_indexes_and_constraints(module)


def module_output_path(root: Path, layer: str, module: ModuleDefinition) -> Path:
    validate_module_definition(module)
    root = root.resolve()
    boundary = (root / "backend" / "app" / layer).resolve()
    try:
        boundary.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Generated module output directory escapes the project root."
        ) from error
    output = (boundary / f"{module.module_name}.py").resolve()
    try:
        output.relative_to(boundary)
    except ValueError as error:
        raise ValueError(
            "Generated module output path escapes its layer directory."
        ) from error
    return output
