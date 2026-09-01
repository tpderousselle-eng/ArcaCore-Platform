from tools.core.field_parser import Field


class FieldValidator:

    @staticmethod
    def validate(
        fields: list[Field],
    ):

        names: set[str] = set()

        for field in fields:

            #
            # Duplicate field names
            #

            if field.name in names:
                raise ValueError(
                    f"Duplicate field name: {field.name}"
                )

            names.add(
                field.name
            )

            #
            # String length validation
            #

            if (
                field.max_length is not None
                and field.sqlalchemy_type != "String"
            ):
                raise ValueError(
                    f"{field.name}: length= is only valid for String fields."
                )

            #
            # Foreign key validation
            #

            if (
                field.foreign_key is not None
                and field.foreign_key.strip() == ""
            ):
                raise ValueError(
                    f"{field.name}: Foreign key cannot be empty."
                )