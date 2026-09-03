import ast
from dataclasses import dataclass, field as dataclass_field
from keyword import iskeyword
from typing import Any

from tools.core.cascade_parser import validate_delete_cascades
from tools.core.computed_parser import validate_computed_fields
from tools.core.custom_validator_parser import validate_custom_validators
from tools.core.hybrid_property_parser import validate_hybrid_properties
from tools.core.relationship_parser import configure_one_to_many, validate_one_to_many_names
from tools.core.self_relationship_parser import configure_self_relationship, validate_self_relationships


@dataclass
class Field:
    name: str
    python_type: str
    sqlalchemy_type: str
    type_arguments: list[str] | None = None
    enum_name: str | None = None
    enum_values: list[str] | None = None
    primary_key: bool = False
    nullable: bool = False
    unique: bool = False
    index: bool = False
    default: Any = None
    max_length: int | None = None
    minimum: str | None = None
    maximum: str | None = None
    min_length: int | None = None
    pattern: str | None = None
    computed_expression: str | None = None
    computed_sql: str | None = None
    hybrid_expression: str | None = None
    hybrid_python: str | None = None
    hybrid_class: str | None = None
    hybrid_references: list[str] = dataclass_field(default_factory=list)
    foreign_key: str | None = None
    relationship_name: str | None = None
    relationship_class: str | None = None
    relationship_table: str | None = None
    relationship_type: str | None = None
    back_populates: str | None = None
    backref: str | None = None
    association_table: str | None = None
    relationship_key: str | None = None
    cascade_delete: bool = False
    passive_deletes: bool = False
    format: str | None = None
    validators: list[str] = dataclass_field(default_factory=list)


TYPE_MAP = {
    "str": "String", "int": "Integer", "float": "Float", "bool": "Boolean",
    "datetime": "DateTime", "date": "Date", "text": "Text", "uuid": "UUID",
    "enum": "Enum", "decimal": "Numeric", "json": "JSON", "array": "ARRAY",
    "choice": "Choice", "many_to_many": "Relationship",
}
ARRAY_ELEMENT_TYPES = {
    name: sqlalchemy_type
    for name, sqlalchemy_type in TYPE_MAP.items()
    if name not in {"array", "enum", "decimal", "choice", "many_to_many"}
}


def validate_format(field: Field):
    if field.format is None:
        return
    if field.format not in {"email", "phone", "slug", "url"}:
        raise ValueError(f"{field.name}: format= supports email, phone, slug, or url only.")
    if (field.python_type, field.sqlalchemy_type) not in {("str", "String"), ("text", "Text")}:
        raise ValueError(f"{field.name}: format={field.format} requires a str or text field.")
    if field.relationship_type == "many_to_many":
        raise ValueError(f"{field.name}: format={field.format} requires a scalar field.")


def _split_field_definition(definition: str) -> list[str]:
    """Split top-level modifiers while preserving quoted values and regex text."""
    parts = []
    start = 0
    position = 0
    quote = None
    depth = 0
    while position < len(definition):
        if (
            quote is None
            and depth == 0
            and position == start
            and len(parts) >= 2
            and definition.startswith("regex=", start)
        ):
            parts.append(definition[start:])
            return parts
        character = definition[position]
        if quote is not None:
            if character == "\\":
                position += 2
                continue
            if character == quote:
                quote = None
        elif (
            character in {"'", '"'}
            and len(parts) >= 2
            and definition.startswith(("default=", "hybrid="), start)
        ):
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character == ":" and depth == 0:
            parts.append(definition[start:position])
            start = position + 1
        position += 1
    if quote is not None:
        raise ValueError("Unterminated quoted value.")
    parts.append(definition[start:])

    for modifier in parts[2:]:
        if not modifier.startswith("default="):
            continue
        value = modifier.partition("=")[2].lstrip()
        if value.startswith(("'", '"')):
            try:
                ast.literal_eval(value)
            except (SyntaxError, ValueError) as error:
                raise ValueError(
                    "Quoted default must be one complete Python literal."
                ) from error
    return parts

def parse_fields(module_name: str, field_strings: list[str]) -> list[Field]:
    fields: list[Field] = []
    for field in field_strings:
        parts = _split_field_definition(field)
        if len(parts) < 2:
            raise ValueError(f"Invalid field definition: {field}")
        name = parts[0]
        raw_type = parts[1]
        type_arguments = None
        if "(" in raw_type and raw_type.endswith(")"):
            base_type = raw_type.split("(", 1)[0]
            arguments = raw_type[raw_type.index("(") + 1 : -1]
            type_arguments = [arg.strip() for arg in arguments.split(",") if arg.strip()]
            if base_type in {"array", "choice", "many_to_many"}:
                type_arguments = [arg.strip() for arg in arguments.split(",")]
        else:
            base_type = raw_type
        if base_type not in TYPE_MAP:
            raise ValueError(f"Unsupported type: {base_type}")
        if base_type == "array":
            if not type_arguments or len(type_arguments) != 1 or not type_arguments[0]:
                raise ValueError("array() requires exactly one element type.")
            if type_arguments[0] not in ARRAY_ELEMENT_TYPES:
                raise ValueError(f"Unsupported array element type: {type_arguments[0]}")
        if base_type == "choice":
            if not type_arguments or any(not value for value in type_arguments):
                raise ValueError("choice() requires non-empty string values.")
            if len(set(type_arguments)) != len(type_arguments):
                raise ValueError("choice() values must be unique.")
            if any("(" in value or ")" in value for value in type_arguments):
                raise ValueError("choice() values cannot contain parentheses.")
        parsed = Field(name=name, python_type=base_type,
                       sqlalchemy_type=TYPE_MAP[base_type], type_arguments=type_arguments)
        if base_type == "many_to_many":
            if not type_arguments or len(type_arguments) not in {1, 2} or not all(type_arguments):
                raise ValueError("many_to_many() requires Model and optionally table.column.")
            target = type_arguments[0]
            if any(not value.isidentifier() or iskeyword(value) for value in (name, module_name, target)):
                raise ValueError("many_to_many() requires valid field and model identifiers.")
            if len(parts) != 2:
                raise ValueError(f"{name}: column modifiers are not valid for many_to_many.")
            target_reference = type_arguments[1] if len(type_arguments) == 2 else f"{target.lower()}s.id"
            target_parts = target_reference.split(".")
            if len(target_parts) != 2 or not all(part.isidentifier() for part in target_parts):
                raise ValueError("many_to_many() target must be table.column.")
            if target.lower() == module_name.lower() or target_parts[0] == f"{module_name.lower()}s":
                raise ValueError("Self-referencing many_to_many relationships are not supported yet.")
            parsed.relationship_name = name
            parsed.relationship_class = target.capitalize()
            parsed.relationship_table, parsed.relationship_key = target_parts
            parsed.relationship_type = "many_to_many"
            parsed.association_table = f"{module_name.lower()}_{name}"
            parsed.backref = f"{module_name.lower()}s"
            fields.append(parsed)
            continue
        if parsed.python_type == "enum" and parsed.type_arguments:
            parsed.enum_name = f"{module_name.capitalize()}{name.capitalize()}"
            parsed.enum_values = parsed.type_arguments
        if parsed.python_type == "decimal" and parsed.type_arguments:
            if len(parsed.type_arguments) != 2:
                raise ValueError("decimal() requires precision and scale.")
        one_to_one = False
        one_to_many = None
        self_relationship = None
        seen_validation = set()
        for modifier in parts[2:]:
            key, _, value = modifier.partition("=")
            if key in {"min", "max", "min_length", "length", "regex", "computed", "hybrid", "format"}:
                if key in seen_validation:
                    raise ValueError(f"{name}: duplicate {key} modifier.")
                seen_validation.add(key)
            if modifier == "pk":
                parsed.primary_key = True
            elif modifier == "nullable":
                parsed.nullable = True
            elif modifier == "unique":
                parsed.unique = True
            elif modifier == "index":
                parsed.index = True
            elif modifier == "cascade_delete":
                if parsed.cascade_delete:
                    raise ValueError(f"{name}: duplicate cascade_delete modifier.")
                parsed.cascade_delete = True
            elif modifier == "passive_deletes":
                if parsed.passive_deletes:
                    raise ValueError(f"{name}: duplicate passive_deletes modifier.")
                parsed.passive_deletes = True
            elif modifier == "one_to_one":
                one_to_one = True
            elif modifier == "one_to_many" or modifier.startswith("one_to_many("):
                if one_to_many is not None:
                    raise ValueError(f"{name}: duplicate one_to_many modifier.")
                one_to_many = modifier
            elif modifier == "self_relationship" or modifier.startswith("self_relationship("):
                if self_relationship is not None:
                    raise ValueError(f"{name}: duplicate self_relationship modifier.")
                self_relationship = modifier
            elif modifier.startswith("length="):
                parsed.max_length = int(value)
            elif modifier.startswith("min_length="):
                parsed.min_length = int(value)
            elif modifier.startswith("min="):
                parsed.minimum = value
            elif modifier.startswith("max="):
                parsed.maximum = value
            elif modifier.startswith("regex="):
                parsed.pattern = value
            elif modifier.startswith("format="):
                parsed.format = value
            elif modifier.startswith("validator="):
                parsed.validators.append(value)
            elif modifier.startswith("computed="):
                parsed.computed_expression = value.strip()
            elif modifier.startswith("hybrid="):
                parsed.hybrid_expression = value.strip()
            elif modifier.startswith("default="):
                parsed.default = value
            elif modifier.startswith("fk="):
                parsed.foreign_key = value
                table = value.split(".")[0]
                parsed.relationship_table = table
                parsed.relationship_name = parsed.name[:-3] if parsed.name.endswith("_id") else table
                parsed.relationship_class = parsed.relationship_name.capitalize()
                parsed.relationship_type = "many_to_one"
                parsed.back_populates = f"{module_name.lower()}s"
            else:
                raise ValueError(f"Unknown modifier: {modifier}")
        validate_format(parsed)
        validate_custom_validators(parsed)
        if one_to_one:
            target_parts = (parsed.foreign_key or "").split(".")
            if len(target_parts) != 2 or not all(part.isidentifier() for part in target_parts):
                raise ValueError(f"{name}: one_to_one requires fk=table.column.")
            if parsed.sqlalchemy_type in {"ARRAY", "JSON"}:
                raise ValueError(f"{name}: one_to_one requires a scalar foreign key.")
            parsed.relationship_type = "one_to_one"
            parsed.unique = True
            parsed.back_populates = None
            parsed.backref = module_name.lower()
        if self_relationship is not None:
            if one_to_one or one_to_many is not None:
                raise ValueError(f"{name}: self_relationship cannot be combined with other relationship modifiers.")
            configure_self_relationship(parsed, module_name, self_relationship)
        if one_to_many is not None:
            configure_one_to_many(parsed, module_name, one_to_many)
        fields.append(parsed)
    validate_one_to_many_names(fields)
    validate_self_relationships(fields)
    validate_computed_fields(fields)
    validate_hybrid_properties(fields)
    validate_delete_cascades(fields, f"{module_name.lower()}s")
    return fields
