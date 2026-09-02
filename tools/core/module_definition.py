from dataclasses import dataclass

from tools.core.field_parser import Field


@dataclass
class ModuleDefinition:
    name: str
    class_name: str
    module_name: str
    table_name: str
    fields: list[Field]

    @property
    def has_relationships(self) -> bool:

        return any(
            field.relationship_name
            for field in self.fields
        )

    @property
    def has_primary_key(self) -> bool:

        return any(
            field.primary_key
            for field in self.fields
        )

    @property
    def has_uuid(self) -> bool:

        return any(
            field.sqlalchemy_type == "UUID"
            for field in self.fields
        )

    @property
    def has_enum(self) -> bool:

        return any(
            field.enum_name is not None
            for field in self.fields
        )

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

            enums.append(
                (
                    field.enum_name,
                    field.enum_values,
                )
            )

        return enums