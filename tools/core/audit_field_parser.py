"""Parse and validate module-level audit-field declarations."""

from dataclasses import dataclass
import re


AUDIT_TYPE_MAP = {
    "int": "Integer",
    "str": "String",
    "uuid": "UUID",
}
AUDIT_NAMES = {"created_by", "updated_by", "created_at", "updated_at"}


@dataclass(frozen=True)
class AuditFieldDefinition:
    target: str
    python_type: str
    sqlalchemy_type: str


def parse_audit_fields(definition: str) -> AuditFieldDefinition:
    if definition == "audit_fields":
        return AuditFieldDefinition("users.id", "int", "Integer")

    match = re.fullmatch(r"audit_fields\(([^()]*)\)", definition)
    if match is None:
        raise ValueError(
            "Use audit_fields or audit_fields(table.column,type)."
        )
    arguments = [value.strip() for value in match.group(1).split(",")]
    if len(arguments) not in {1, 2} or not all(arguments):
        raise ValueError(
            "audit_fields() requires table.column and optionally int, str, or uuid."
        )
    target = arguments[0]
    python_type = arguments[1] if len(arguments) == 2 else "int"
    target_parts = target.split(".")
    if len(target_parts) != 2 or not all(part.isidentifier() for part in target_parts):
        raise ValueError("audit_fields() target must be table.column.")
    if python_type not in AUDIT_TYPE_MAP:
        raise ValueError("audit_fields() type must be int, str, or uuid.")
    return AuditFieldDefinition(target, python_type, AUDIT_TYPE_MAP[python_type])


def validate_audit_fields(audit_fields, fields):
    if audit_fields is None:
        return
    if not isinstance(audit_fields, AuditFieldDefinition):
        raise ValueError("audit_fields metadata must be an AuditFieldDefinition.")
    expected = AUDIT_TYPE_MAP.get(audit_fields.python_type)
    if expected is None or audit_fields.sqlalchemy_type != expected:
        raise ValueError("audit_fields metadata contains an invalid actor type.")
    target_parts = audit_fields.target.split(".")
    if len(target_parts) != 2 or not all(part.isidentifier() for part in target_parts):
        raise ValueError("audit_fields target must be table.column.")
    for field in fields:
        if field.name in AUDIT_NAMES or field.relationship_name in AUDIT_NAMES:
            raise ValueError(
                f"{field.name}: audit_fields reserves created_by, updated_by, "
                "created_at, and updated_at."
            )
