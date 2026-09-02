from tools.core.field_parser import Field


class SQLAlchemyRenderer:

    @staticmethod
    def render(field: Field) -> list[str]:

        arguments: list[str] = []

        #
        # SQLAlchemy Type
        #

        if field.sqlalchemy_type == "String":

            if field.max_length:

                arguments.append(
                    f"String({field.max_length})"
                )

            else:

                arguments.append(
                    "String"
                )

        elif field.sqlalchemy_type == "UUID":

            arguments.append(
                "UUID(as_uuid=True)"
            )

        elif field.sqlalchemy_type == "Enum":

            arguments.append(
                f"Enum({field.enum_name})"
            )

        elif field.sqlalchemy_type == "Numeric":

            precision, scale = field.type_arguments

            arguments.append(
                f"Numeric({precision}, {scale})"
            )

        elif field.sqlalchemy_type == "JSON":

            arguments.append(
                "JSON"
            )

        else:

            arguments.append(
                field.sqlalchemy_type
            )

        if field.foreign_key:

            arguments.append(
                f'ForeignKey("{field.foreign_key}")'
            )

        if field.primary_key:

            arguments.append(
                "primary_key=True"
            )

        if field.nullable:

            arguments.append(
                "nullable=True"
            )

        if field.unique:

            arguments.append(
                "unique=True"
            )

        if field.index:

            arguments.append(
                "index=True"
            )

        if field.default is not None:

            arguments.append(
                f"default={field.default}"
            )

        return arguments

    @staticmethod
    def render_relationship(
        field: Field,
    ) -> list[str]:

        if not field.relationship_name:
            return []

        arguments = [
            f'"{field.relationship_class}"',
        ]

        if field.back_populates:
            arguments.append(
                f'back_populates="{field.back_populates}"'
            )

        return arguments