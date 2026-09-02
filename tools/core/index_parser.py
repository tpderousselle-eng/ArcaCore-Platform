from hashlib import sha256
import re

from tools.core.field_parser import Field
from tools.core.module_definition import CompositeIndex


def parse_indexes(
    table_name: str,
    definitions: list[str],
    fields: list[Field],
) -> list[CompositeIndex]:
    columns = {
        field.name for field in fields if field.relationship_type != "many_to_many"
    }
    columns.update({"created_at", "updated_at"})
    if not any(field.primary_key for field in fields):
        columns.add("id")

    indexes = []
    seen_names = set()
    for definition in definitions:
        match = re.fullmatch(r"index\(([^()]*)\)", definition)
        if not match:
            raise ValueError("Composite indexes must use index(column1,column2).")
        selected = [column.strip() for column in match.group(1).split(",")]
        if len(selected) < 2 or not all(selected):
            raise ValueError("index() requires at least two non-empty column names.")
        if len(set(selected)) != len(selected):
            raise ValueError("index() cannot repeat a column.")
        for column in selected:
            if column not in columns:
                raise ValueError(f"index(): unknown or non-column field: {column}")

        name = f"ix_{table_name}_{'_'.join(selected)}"
        # Keep generated names within PostgreSQL's identifier byte limit.
        if len(name.encode("utf-8")) > 63:
            digest = sha256(name.encode("utf-8")).hexdigest()[:10]
            prefix = name.encode("utf-8")[:52].decode("utf-8", errors="ignore")
            name = f"{prefix}_{digest}"
        if name in seen_names:
            raise ValueError(f"Duplicate composite index name: {name}")
        seen_names.add(name)
        indexes.append(CompositeIndex(name=name, columns=selected))

    return indexes
