"""Translate structured logical constraints, never expressions from prose."""
import json
from decimal import Decimal, InvalidOperation

from tools.core.constraint_parser import parse_constraints


def constraint_declarations(entity, constraints, names, parsed_fields):
    fields = {f.field_id: f for f in entity.approved_fields}
    result = set()
    for constraint in constraints:
        selected = tuple(sorted(names[fid] for fid in constraint.field_ids))
        value = json.loads(constraint.value_json)
        if constraint.kind == "composite_unique" and value is True and len(selected) >= 2:
            if any(not fields[fid].required or fields[fid].logical_type.value == "json" for fid in constraint.field_ids):
                raise ValueError("Composite uniqueness needs non-null fields with certified database equality semantics.")
            result.add("unique_together(" + ",".join(selected) + ")")
        elif constraint.kind == "unique" and value is True and len(selected) == 1:
            field = fields[constraint.field_ids[0]]
            if not field.unique and field.field_id not in entity.identity_field_ids:
                raise ValueError("A uniqueness constraint conflicts with absent field uniqueness certification.")
            # Already enforced by the approved field/identity declaration.
        elif constraint.kind in {"min_value", "max_value"} and len(selected) == 1:
            field = fields[constraint.field_ids[0]]
            if field.logical_type.value != "integer" or field.collection:
                raise ValueError("Bounded checks currently certify scalar integer bounds only.")
            try:
                number = Decimal(str(value))
            except InvalidOperation as error:
                raise ValueError("Invalid integer bound.") from error
            if not number.is_finite() or number != number.to_integral_value() or not -(2**31) <= number < 2**31:
                raise ValueError("The integer bound is not exactly representable by the public Integer contract.")
            operator = ">=" if constraint.kind == "min_value" else "<="
            result.add(f"check({selected[0]} {operator} {int(number)})")
        else:
            raise ValueError("Logical constraint " + constraint.kind + " has no certified exact public representation.")
    result = tuple(sorted(result))
    # Use the existing bounded grammar as the authoritative physical validator.
    parse_constraints("certification", list(result), parsed_fields)
    return result


def certify_access(entity, requirements):
    for requirement in requirements:
        if tuple(requirement.field_ids) != tuple(entity.identity_field_ids) or len(requirement.field_ids) != 1 or requirement.unique is not True:
            raise ValueError("Logical lookup is not a database index; only exact standard CRUD identity lookup is certified.")


def relationship_blocker(relationship):
    return (f"Relationship {relationship.relationship_id} ({relationship.source_cardinality} to "
        f"{relationship.target_cardinality}, ownership={relationship.ownership}, deletion={relationship.deletion_behavior}) "
        "has no approved FK-field binding, reverse-name or tenant-scope contract. Public relationship support does not supply that authority.")
