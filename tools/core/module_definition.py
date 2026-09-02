from dataclasses import dataclass, field as dataclass_field

from tools.core.field_parser import Field


@dataclass
class CompositeIndex:
    name: str
    columns: list[str]


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

    def __post_init__(self):
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
