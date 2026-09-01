from tools.core.field_parser import Field


class SQLAlchemyRenderer:

    @staticmethod
    def render(field: Field) -> list[str]:

        arguments: list[str] = []

        #
        # SQLAlchemy Type
        #

        if (
            field.sqlalchemy_type == "String"
            and field.max_length
        ):
            arguments.append(
                f"String({field.max_length})"
            )
        else:
            arguments.append(
                field.sqlalchemy_type
            )

        #
        # Foreign Key
        #

        if field.foreign_key:
            arguments.append(
                f'ForeignKey("{field.foreign_key}")'
            )

        #
        # Primary Key
        #

        if field.primary_key:
            arguments.append(
                "primary_key=True"
            )

        #
        # Nullable
        #

        if field.nullable:
            arguments.append(
                "nullable=True"
            )

        #
        # Unique
        #

        if field.unique:
            arguments.append(
                "unique=True"
            )

        #
        # Index
        #

        if field.index:
            arguments.append(
                "index=True"
            )

        #
        # Default
        #

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