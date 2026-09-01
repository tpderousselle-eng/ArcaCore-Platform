from dataclasses import dataclass
from typing import Any


@dataclass
class Field:
    name: str
    python_type: str
    sqlalchemy_type: str

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
}


def parse_fields(
    module_name: str,
    field_strings: list[str],
) -> list[Field]:

    fields: list[Field] = []

    for field in field_strings:

        parts = field.split(":")

        if len(parts) < 2:
            raise ValueError(
                f"Invalid field definition: {field}"
            )

        name = parts[0]
        field_type = parts[1]

        if field_type not in TYPE_MAP:
            raise ValueError(
                f"Unsupported type: {field_type}"
            )

        parsed = Field(
            name=name,
            python_type=field_type,
            sqlalchemy_type=TYPE_MAP[field_type],
        )

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
                parsed.max_length = int(
                    modifier.split("=")[1]
                )

            elif modifier.startswith("default="):
                parsed.default = modifier.split(
                    "=",
                    1,
                )[1]

            elif modifier.startswith("fk="):

                fk = modifier.split(
                    "=",
                    1,
                )[1]

                parsed.foreign_key = fk

                table = fk.split(".")[0]

                parsed.relationship_table = table

                if parsed.name.endswith("_id"):
                    parsed.relationship_name = (
                        parsed.name[:-3]
                    )
                else:
                    parsed.relationship_name = table

                parsed.relationship_class = (
                    parsed.relationship_name.capitalize()
                )

                parsed.relationship_type = "many_to_one"

                parsed.back_populates = (
                    f"{module_name.lower()}s"
                )

            else:
                raise ValueError(
                    f"Unknown modifier: {modifier}"
                )

        fields.append(parsed)

    return fields