from tools.core.field_parser import ARRAY_ELEMENT_TYPES, Field
from tools.core.module_definition import CheckRule, CompositeIndex, UniqueTogether


class SQLAlchemyRenderer:
    @staticmethod
    def render(field: Field) -> list[str]:
        arguments: list[str] = []

        if field.relationship_type == "many_to_many":
            return arguments

        if field.sqlalchemy_type == "String":
            if field.max_length:
                arguments.append(f"String({field.max_length})")
            else:
                arguments.append("String")
        elif field.sqlalchemy_type == "UUID":
            arguments.append("UUID(as_uuid=True)")
        elif field.sqlalchemy_type == "Enum":
            arguments.append(f"Enum({field.enum_name})")
        elif field.sqlalchemy_type == "Choice":
            values = ", ".join(repr(value) for value in field.type_arguments)
            constraint_name = f"{field.name}_choice"
            arguments.append(
                f"SQLEnum({values}, name={constraint_name!r}, "
                "native_enum=False, create_constraint=True, validate_strings=True)"
            )
        elif field.sqlalchemy_type == "Numeric":
            precision, scale = field.type_arguments
            arguments.append(f"Numeric({precision}, {scale})")
        elif field.sqlalchemy_type == "JSON":
            arguments.append("JSON")
        elif field.sqlalchemy_type == "ARRAY":
            element_type = ARRAY_ELEMENT_TYPES[field.type_arguments[0]]
            if element_type == "UUID":
                element_type = "UUID(as_uuid=True)"
            arguments.append(f"ARRAY({element_type})")
        else:
            arguments.append(field.sqlalchemy_type)

        if field.computed_expression is not None:
            if not field.computed_sql:
                raise ValueError(f"{field.name}: computed expression has not been validated.")
            arguments.append(f"Computed({field.computed_sql!r}, persisted=True)")
        if field.foreign_key:
            ondelete = ', ondelete="CASCADE"' if field.cascade_delete else ""
            arguments.append(f'ForeignKey("{field.foreign_key}"{ondelete})')
        if field.primary_key:
            arguments.append("primary_key=True")
        if field.nullable:
            arguments.append("nullable=True")
        elif field.computed_expression is not None or (
            field.relationship_type in {"many_to_one", "self_many_to_one"} and field.backref
        ):
            arguments.append("nullable=False")
        if field.unique:
            arguments.append("unique=True")
        if field.index:
            arguments.append("index=True")
        if field.default is not None:
            arguments.append(f"default={field.default}")

        return arguments

    @staticmethod
    def render_relationship(field: Field) -> list[str]:
        if not field.relationship_name:
            return []

        arguments = [f'"{field.relationship_class}"']
        passive = ", passive_deletes=True" if field.passive_deletes else ""
        if field.relationship_type == "many_to_many":
            arguments.append(f"secondary={field.association_table}")
            arguments.append(f"backref={field.backref!r}")
        elif field.relationship_type == "one_to_one":
            arguments.append("uselist=False")
            arguments.append(f"foreign_keys=[{field.name}]")
            cascade = ', cascade="save-update, merge, delete"' if field.cascade_delete else ""
            arguments.append(f"backref=backref({field.backref!r}, uselist=False{cascade}{passive})")
        elif field.relationship_type in {"many_to_one", "self_many_to_one"} and field.backref:
            arguments.append("uselist=False")
            arguments.append(f"foreign_keys=[{field.name}]")
            if field.relationship_type == "self_many_to_one":
                arguments.append(f"remote_side=[{field.relationship_key}]")
            if field.cascade_delete:
                arguments.append(f'backref=backref({field.backref!r}, cascade="save-update, merge, delete"{passive})')
            else:
                arguments.append(f"backref={field.backref!r}")
        elif field.back_populates:
            arguments.append(f'back_populates="{field.back_populates}"')
        return arguments

    @staticmethod
    def render_index(index: CompositeIndex) -> str:
        arguments = ", ".join(repr(value) for value in [index.name, *index.columns])
        return f"Index({arguments})"

    @staticmethod
    def render_unique(constraint: UniqueTogether) -> str:
        columns = ", ".join(repr(column) for column in constraint.columns)
        return f"UniqueConstraint({columns}, name={constraint.name!r})"

    @staticmethod
    def render_check(constraint: CheckRule) -> str:
        return f"CheckConstraint({constraint.expression!r}, name={constraint.name!r})"
