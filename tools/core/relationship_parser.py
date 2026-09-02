"""Configure explicit one-to-many collections from a child foreign key."""
from keyword import iskeyword
import re


RESERVED_NAMES = {"id", "metadata", "registry", "created_at", "updated_at", "deleted_at"}


def valid_name(value):
    return value.isidentifier() and not iskeyword(value) and not value.startswith("_")


def configure_one_to_many(field, module_name, declaration):
    target_parts = (field.foreign_key or "").split(".")
    if len(target_parts) != 2 or not all(valid_name(part) for part in target_parts):
        raise ValueError(f"{field.name}: one_to_many requires fk=table.column.")
    if field.python_type not in {"int", "uuid", "str"}:
        raise ValueError(f"{field.name}: one_to_many requires an int, uuid, or str foreign key.")
    if field.primary_key or field.unique or field.computed_expression is not None:
        raise ValueError(f"{field.name}: one_to_many cannot be primary, unique, or computed.")
    if field.relationship_type == "one_to_one":
        raise ValueError(f"{field.name}: one_to_one and one_to_many cannot be combined.")
    if declaration == "one_to_many":
        target = field.relationship_class
        collection = f"{module_name.lower()}s"
    else:
        match = re.fullmatch(r"one_to_many\(([^(),]+),([^(),]+)\)", declaration)
        if not match:
            raise ValueError("Use one_to_many or one_to_many(Model,collection).")
        target, collection = (part.strip() for part in match.groups())
    if not target or not valid_name(target) or not valid_name(collection):
        raise ValueError(f"{field.name}: invalid one_to_many model or collection name.")
    if collection in RESERVED_NAMES:
        raise ValueError(f"{field.name}: reserved collection name: {collection}")
    if not valid_name(field.relationship_name) or field.relationship_name in RESERVED_NAMES:
        raise ValueError(f"{field.name}: invalid or reserved relationship name.")
    if target.lower() == module_name.lower() or target_parts[0] == f"{module_name.lower()}s":
        raise ValueError("Self relationships require a separate self-relationship declaration.")
    field.relationship_type = "many_to_one"
    field.relationship_class = target.capitalize()
    field.relationship_key = target_parts[1]
    field.back_populates = None
    field.backref = collection


def validate_one_to_many_names(fields):
    configured = [field for field in fields if field.relationship_type == "many_to_one" and field.backref]
    for field in configured:
        if any(other.name == field.relationship_name for other in fields):
            raise ValueError(f"Relationship {field.relationship_name} conflicts with a field name.")
        for other in fields:
            if other is field:
                continue
            if other.relationship_name == field.relationship_name:
                raise ValueError(f"Duplicate relationship name: {field.relationship_name}")
            if other.relationship_class == field.relationship_class and other.backref == field.backref:
                raise ValueError(f"Duplicate reverse collection: {field.relationship_class}.{field.backref}")
