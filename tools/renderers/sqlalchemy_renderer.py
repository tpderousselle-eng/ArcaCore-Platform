from tools.core.field_parser import ARRAY_ELEMENT_TYPES, Field


class SQLAlchemyRenderer:
    @staticmethod
    def render(field: Field) -> list[str]:
        arguments: list[str] = []

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

        if field.foreign_key:
            arguments.append(f'ForeignKey("{field.foreign_key}")')
        if field.primary_key:
            arguments.append("primary_key=True")
        if field.nullable:
            arguments.append("nullable=True")
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
        if field.relationship_type == "one_to_one":
            arguments.append("uselist=False")
            arguments.append(f"foreign_keys=[{field.name}]")
            arguments.append(f"backref=backref({field.backref!r}, uselist=False)")
        elif field.back_populates:
            arguments.append(f'back_populates="{field.back_populates}"')
        return arguments
