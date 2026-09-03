"""Parse and validate module-level optimistic-version declarations."""


VERSION_COLUMN_NAME = "version_id"


def parse_version_column(definition: str) -> bool:
    if definition != "version_column":
        raise ValueError("Use version_column without arguments or modifiers.")
    return True


def validate_version_column(version_column, fields):
    if type(version_column) is not bool:
        raise ValueError("version_column metadata must be a boolean.")
    if not version_column:
        return
    for field in fields:
        if field.name == VERSION_COLUMN_NAME or field.relationship_name == VERSION_COLUMN_NAME:
            raise ValueError("version_id is reserved when version_column is enabled.")
