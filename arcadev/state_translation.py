"""Bounded state translation. Missing logical authority is never a default."""
from __future__ import annotations

import ast
import json
import re

from tools.core.field_parser import parse_fields, _split_field_definition
from tools.core.module_definition import valid_public_identifier


SCALAR_TYPES = {
    "string": "str", "text": "text", "integer": "int", "boolean": "bool",
    "date": "date", "datetime": "datetime", "uuid": "uuid", "json": "json",
}


def validate_field_declaration(value):
    """Accept only the certified subset, then let the public parser validate it."""
    if type(value) is not str or len(value) > 4096:
        raise ValueError("Uncertified module declaration.")
    parts = _split_field_definition(value)
    if len(parts) < 2 or not valid_public_identifier(parts[0]):
        raise ValueError("Uncertified module declaration.")
    if parts[1] not in SCALAR_TYPES.values() and not re.fullmatch(r"(?:choice|many_to_many)\([^()]+\)", parts[1]):
        raise ValueError("Uncertified field type.")
    for modifier in parts[2:]:
        if modifier in {"pk", "nullable", "unique"}:
            continue
        # Audited public relationship declarations are accepted for dependency
        # inspection. Only frozen-authority reconstruction can grant support.
        if modifier in {"one_to_one", "one_to_many", "self_relationship", "cascade_delete", "passive_deletes", "global_target"}:
            continue
        if re.fullmatch(r"fk=[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*", modifier) or re.fullmatch(
            r"(?:one_to_many|self_relationship)\([A-Za-z][A-Za-z0-9_]*(?:,[A-Za-z][A-Za-z0-9_]*)?\)", modifier
        ):
            continue
        if modifier.startswith("default="):
            try:
                literal = ast.literal_eval(modifier[8:])
            except (ValueError, SyntaxError) as error:
                raise ValueError("Only literal defaults are certified.") from error
            if type(literal) in {str, int, bool} or literal is None:
                continue
        raise ValueError("Uncertified field modifier.")


def field_declaration(field, physical, *, primary=False, domains=()):
    if field.collection:
        raise ValueError("Collections lack approved ordering and duplication semantics; ARRAY translation remains blocked.")
    kind = field.logical_type.value
    if kind == "decimal":
        raise ValueError("Decimal precision and scale are absent from logical authority.")
    if kind in {"external_reference", "binary_reference"}:
        raise ValueError("Reference fields lack an approved physical encoding contract.")
    if field.mutable is not (not primary):
        raise ValueError("Only immutable identities and mutable non-identity fields are certified.")
    if field.unique is None:
        raise ValueError("Field uniqueness must be explicit.")
    if field.unique and (not field.required or kind == "json"):
        raise ValueError("Uniqueness requires certified non-null database equality semantics.")
    if primary and (not field.required or kind not in {"string", "integer", "uuid"}):
        raise ValueError("Identity must be a required scalar with a certified key type.")
    if primary and kind == "uuid":
        raise ValueError("UUID identity adds uuid.uuid4; JSON literal defaults cannot authorize that callable.")
    if primary and kind == "integer" and field.default_json is None:
        raise ValueError("Integer identity adds autoincrement without approved generation semantics.")
    values = None
    if kind == "enum":
        domain = next((d for d in domains if d.domain_id == field.value_domain_id), None)
        if domain is None:
            raise ValueError("The complete approved value domain is required.")
        values = domain.values
        if not values or len(set(values)) != len(values) or any(
            not v or v != v.strip() or any(c in v for c in ",()") or any(ord(c) < 32 for c in v)
            for v in values
        ) or len((physical + "_choice").encode("utf-8")) > 63:
            raise ValueError("Value domain cannot roundtrip through public choice grammar without truncation or normalization.")
        target = "choice(" + ",".join(values) + ")"
    elif kind in SCALAR_TYPES and field.value_domain_id is None:
        target = SCALAR_TYPES[kind]
    else:
        raise ValueError("Logical type has no certified field representation.")
    declaration = physical + ":" + target
    declaration += ":pk" if primary else (":nullable" if not field.required else "")
    if field.unique and not primary:
        declaration += ":unique"
    if field.default_json is not None:
        value = json.loads(field.default_json)
        expected = {"string": str, "text": str, "integer": int, "boolean": bool, "enum": str}
        if value is None:
            if field.required or kind == "json":
                raise ValueError("Null default does not match required/JSON null semantics.")
        elif kind not in expected or type(value) is not expected[kind] or (values is not None and value not in values):
            raise ValueError("Default has no exact certified literal representation for this type.")
        if kind == "integer" and value is not None and not -(2**31) <= value < 2**31:
            raise ValueError("Integer default exceeds the public PostgreSQL Integer range.")
        declaration += ":default=" + repr(value)
    validate_field_declaration(declaration)
    parsed = parse_fields("certification", [declaration])[0]
    if values is not None and tuple(parsed.type_arguments) != values:
        raise ValueError("Public grammar changed the approved domain.")
    return declaration
