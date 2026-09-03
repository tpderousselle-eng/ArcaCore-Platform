"""Validate parent-to-child hard deletion and opt-in database delegation."""
from tools.core.relationship_parser import RESERVED_NAMES, valid_name


def validate_delete_cascades(fields, table_name):
    for field in fields:
        if field.passive_deletes and not field.cascade_delete:
            raise ValueError(f"{field.name}: passive_deletes requires cascade_delete on the same field.")
    configured = [field for field in fields if field.cascade_delete]
    if not configured:
        return
    for other in fields:
        if other.name in {"backref", "relationship"} or other.relationship_name in {"backref", "relationship"}:
            raise ValueError("backref and relationship are reserved when using cascade_delete.")
    for field in configured:
        if field.relationship_type not in {"many_to_one", "one_to_one", "self_many_to_one"} or not field.backref:
            raise ValueError(f"{field.name}: cascade_delete requires one_to_many, one_to_one, or self_relationship.")
        target_parts = (field.foreign_key or "").split(".")
        if len(target_parts) != 2 or not all(valid_name(part) for part in target_parts):
            raise ValueError(f"{field.name}: cascade_delete requires fk=table.column.")
        if field.python_type not in {"int", "uuid", "str"} or field.computed_expression is not None:
            raise ValueError(f"{field.name}: cascade_delete requires a non-computed int, uuid, or str foreign key.")
        if target_parts[0] == table_name and field.relationship_type != "self_many_to_one":
            raise ValueError(f"{field.name}: use self_relationship for a self-referencing cascade.")
        for value in (field.relationship_name, field.relationship_class, field.backref):
            if not value or not valid_name(value) or value in RESERVED_NAMES:
                raise ValueError(f"{field.name}: invalid or reserved cascade relationship name: {value}")
        if any(other.name == field.relationship_name for other in fields):
            raise ValueError(f"Relationship {field.relationship_name} conflicts with a field name.")
        for other in fields:
            if other is field:
                continue
            if other.relationship_name == field.relationship_name:
                raise ValueError(f"Duplicate relationship name: {field.relationship_name}")
            if other.relationship_class == field.relationship_class and other.backref == field.backref:
                raise ValueError(f"Duplicate reverse relationship: {field.relationship_class}.{field.backref}")
