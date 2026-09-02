from dataclasses import dataclass
from typing import Any


@dataclass
class Field:
    name: str

    python_type: str
    sqlalchemy_type: str

    # Parameterized types
    type_arguments: list[str] | None = None

    # Enum metadata
    enum_name: str | None = None
    enum_values: list[str] | None = None

    primary_key: bool = False
    nullable: bool = False
    unique: bool = False
    index: bool = False

    default: Any = None
    max_length: int | None = None

    foreign_key: str | None = None
    relationship_name: str | None = None
    relationship_class: str | None = None
    relationship_table: str | None = None
    relationship_type: str | None = None
    back_populates: str | None = None


TYPE_MAP = {
    "str": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "text": "Text",
    "uuid": "UUID",
    "enum": "Enum",
    "decimal": "Numeric",
    "json": "JSON",
    "array": "ARRAY",
    "choice": "Choice",
}

# Array elements use simple types; parameterized elements are excluded.
ARRAY_ELEMENT_TYPES = {
    name: sqlalchemy_type
    for name, sqlalchemy_type in TYPE_MAP.items()
    if name not in {"array", "enum", "decimal", "choice"}
}


def parse_fields(
    module_name: str,
    field_strings: list[str],
) -> list[Field]:
    fields: list[Field] = []

    for field in field_strings:
        parts = field.split(":")
        if len(parts) < 2:
            raise ValueError(f"Invalid field definition: {field}")

        name = parts[0]
        raw_type = parts[1]
        type_arguments = None

        if "(" in raw_type and raw_type.endswith(")"):
            base_type = raw_type.split("(", 1)[0]
            arguments = raw_type[raw_type.index("(") + 1 : -1]
            type_arguments = [
                arg.strip()
                for arg in arguments.split(",")
                if arg.strip()
            ]

            if base_type in {"array", "choice"}:
                # Keep empty arguments so trailing commas are rejected.
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

        parsed = Field(
            name=name,
            python_type=base_type,
            sqlalchemy_type=TYPE_MAP[base_type],
            type_arguments=type_arguments,
        )

        if parsed.python_type == "enum" and parsed.type_arguments:
            parsed.enum_name = f"{module_name.capitalize()}{name.capitalize()}"
            parsed.enum_values = parsed.type_arguments

        if parsed.python_type == "decimal" and parsed.type_arguments:
            if len(parsed.type_arguments) != 2:
                raise ValueError("decimal() requires precision and scale.")

        for modifier in parts[2:]:
            if modifier == "pk":
                parsed.primary_key = True
            elif modifier == "nullable":
                parsed.nullable = True
            elif modifier == "unique":
                parsed.unique = True
            elif modifier == "index":
                parsed.index = True
            elif modifier.startswith("length="):
                parsed.max_length = int(modifier.split("=")[1])
            elif modifier.startswith("default="):
                parsed.default = modifier.split("=", 1)[1]
            elif modifier.startswith("fk="):
                fk = modifier.split("=", 1)[1]
                parsed.foreign_key = fk
                table = fk.split(".")[0]
                parsed.relationship_table = table
                if parsed.name.endswith("_id"):
                    parsed.relationship_name = parsed.name[:-3]
                else:
                    parsed.relationship_name = table
                parsed.relationship_class = parsed.relationship_name.capitalize()
                parsed.relationship_type = "many_to_one"
                parsed.back_populates = f"{module_name.lower()}s"
            else:
                raise ValueError(f"Unknown modifier: {modifier}")

        fields.append(parsed)

    return fields
