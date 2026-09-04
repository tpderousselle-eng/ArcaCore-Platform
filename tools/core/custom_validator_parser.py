"""Validate callable references without importing application code."""

from keyword import iskeyword


TRUSTED_VALIDATOR_ROOTS = {
    "app_rules",
    "application_rules",
    "rules",
    "validation_rules",
}


def validate_custom_validators(field):
    if not isinstance(field.validators, list):
        raise ValueError(f"{field.name}: validators must be a list of dotted function references.")
    if field.validators and field.relationship_type == "many_to_many":
        raise ValueError(f"{field.name}: validators require a schema field, not a relationship collection.")
    seen = set()
    for reference in field.validators:
        if not isinstance(reference, str):
            raise ValueError(f"{field.name}: validator references must be strings.")
        parts = reference.split(".")
        if len(parts) < 2 or any(
            not part.isascii() or not part.isidentifier() or iskeyword(part) or part.startswith("_")
            for part in parts
        ):
            raise ValueError(f"{field.name}: validator= requires a public dotted module.function reference.")
        if reference in seen:
            raise ValueError(f"{field.name}: duplicate validator reference: {reference}")
        if parts[0] not in TRUSTED_VALIDATOR_ROOTS:
            raise ValueError(
                f"{field.name}: validator reference must use an approved application-owned namespace."
            )
        seen.add(reference)
