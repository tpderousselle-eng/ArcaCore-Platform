"""Validate adjacency-list relationships whose foreign key targets the same model."""
import re

from tools.core.relationship_parser import RESERVED_NAMES, valid_name


SELF_RESERVED_NAMES = RESERVED_NAMES | {"relationship", "backref"}


def configure_self_relationship(field, module_name, declaration):
    target_parts = (field.foreign_key or "").split(".")
    if len(target_parts) != 2 or not all(valid_name(part) for part in target_parts):
        raise ValueError(f"{field.name}: self_relationship requires fk=table.column.")
    if not valid_name(module_name) or target_parts[0] != f"{module_name.lower()}s":
        raise ValueError(f"{field.name}: self_relationship must reference this model's table.")
    if field.python_type not in {"int", "uuid", "str"}:
        raise ValueError(f"{field.name}: self_relationship requires an int, uuid, or str foreign key.")
    if field.primary_key or field.unique or field.computed_expression is not None:
        raise ValueError(f"{field.name}: self_relationship cannot be primary, unique, or computed.")
    if declaration == "self_relationship":
        collection = "children"
    else:
        match = re.fullmatch(r"self_relationship\(([^(),]+)\)", declaration)
        if not match:
            raise ValueError("Use self_relationship or self_relationship(collection).")
        collection = match.group(1).strip()
    for value in (field.relationship_name, collection):
        if not value or not valid_name(value) or value in SELF_RESERVED_NAMES:
            raise ValueError(f"{field.name}: invalid or reserved self-relationship name: {value}")
    field.relationship_class = module_name.capitalize()
    field.relationship_type = "self_many_to_one"
    field.relationship_key = target_parts[1]
    field.back_populates = None
    field.backref = collection


def validate_self_relationships(fields):
    configured = [field for field in fields if field.relationship_type == "self_many_to_one"]
    if not configured:
        return
    primary_keys = [field for field in fields if field.primary_key]
    if len(primary_keys) > 1:
        raise ValueError("self_relationship requires a single primary key.")
    key = primary_keys[0] if primary_keys else None
    key_name = key.name if key else "id"
    key_type = key.python_type if key else "int"
    if key is None and any(field.name == "id" for field in fields):
        raise ValueError("An explicit id field must have pk when using self_relationship.")
    if key and key.computed_expression is not None:
        raise ValueError("self_relationship cannot target a computed primary key.")
    for field in configured:
        if field.relationship_key != key_name:
            raise ValueError(f"{field.name}: self_relationship must reference primary key {key_name}.")
        if field.python_type != key_type:
            raise ValueError(f"{field.name}: foreign key type must match primary key type {key_type}.")
        if field.name == key_name:
            raise ValueError(f"{field.name}: a self foreign key must be separate from the primary key.")
        if field.relationship_name == field.backref:
            raise ValueError(f"{field.name}: scalar and collection names must differ.")
        for name in (field.relationship_name, field.backref):
            if any(other.name == name for other in fields):
                raise ValueError(f"Self relationship {name} conflicts with a field name.")
            for other in fields:
                if other is field:
                    continue
                if other.relationship_name == name:
                    raise ValueError(f"Duplicate relationship name: {name}")
                if other.relationship_class == field.relationship_class and other.backref == name:
                    raise ValueError(f"Duplicate reverse relationship name: {name}")
