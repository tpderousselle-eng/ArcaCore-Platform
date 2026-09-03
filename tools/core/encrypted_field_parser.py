"""Validate encrypted-field metadata without loading runtime key material."""

import re


DEFAULT_ENCRYPTION_KEY_ENV = "ARCACORE_ENCRYPTION_KEYS"
KEY_ENV_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,127}")


def validate_encrypted_fields(fields):
    for field in fields:
        if type(field.encrypted) is not bool:
            raise ValueError(f"{field.name}: encrypted metadata must be boolean.")
        if not field.encrypted:
            if field.encryption_key_env is not None:
                raise ValueError(
                    f"{field.name}: encryption_key_env requires encrypted=True."
                )
            continue

        if field.python_type not in {"str", "text"}:
            raise ValueError(f"{field.name}: encrypted requires a str or text field.")
        if (
            field.primary_key
            or field.unique
            or field.index
            or field.default is not None
            or field.foreign_key is not None
            or field.relationship_name is not None
            or field.computed_expression is not None
            or field.hybrid_expression is not None
            or field.cascade_delete
            or field.passive_deletes
        ):
            raise ValueError(
                f"{field.name}: encrypted fields cannot be keys, unique, indexed, "
                "defaulted, relationships, computed, hybrid, or delete controls."
            )
        if field.name in {"id", "created_at", "updated_at", "deleted_at"}:
            raise ValueError(f"{field.name}: generated field name is reserved.")

        key_env = (
            DEFAULT_ENCRYPTION_KEY_ENV
            if field.encryption_key_env is None
            else field.encryption_key_env
        )
        if KEY_ENV_PATTERN.fullmatch(key_env) is None:
            raise ValueError(
                f"{field.name}: encrypted key environment name must use "
                "uppercase ASCII letters, digits, and underscores."
            )
        field.encryption_key_env = key_env
