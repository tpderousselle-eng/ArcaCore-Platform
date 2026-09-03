from decimal import Decimal, InvalidOperation
from keyword import iskeyword
import re

from tools.core.field_parser import Field, validate_format
from tools.core.custom_validator_parser import validate_custom_validators
from tools.core.encrypted_field_parser import validate_encrypted_fields
from tools.core.hybrid_property_parser import validate_hybrid_properties


class FieldValidator:
    @staticmethod
    def validate(fields: list[Field]):
        validate_encrypted_fields(fields)
        validate_hybrid_properties(fields)
        names: set[str] = set()
        for field in fields:
            validate_format(field)
            validate_custom_validators(field)
            if field.name in names:
                raise ValueError(f"Duplicate field name: {field.name}")
            names.add(field.name)
            if not field.name.isidentifier() or iskeyword(field.name) or field.name.startswith("_"):
                raise ValueError(f"Invalid field name: {field.name}")
            if field.name.startswith("model_"):
                raise ValueError(f"{field.name}: model_ is reserved by Pydantic.")
            if field.max_length is not None:
                if field.sqlalchemy_type != "String":
                    raise ValueError(f"{field.name}: length= is only valid for String fields.")
                if field.max_length < 1:
                    raise ValueError(f"{field.name}: length= must be positive.")
            if field.min_length is not None:
                if field.python_type not in {"str", "text"} or field.min_length < 0:
                    raise ValueError(f"{field.name}: min_length= requires a string and a nonnegative integer.")
                if field.max_length is not None and field.min_length > field.max_length:
                    raise ValueError(f"{field.name}: min_length cannot exceed length.")
            bounds = []
            for raw in (field.minimum, field.maximum):
                if raw is None:
                    bounds.append(None)
                    continue
                if field.python_type not in {"int", "float", "decimal"}:
                    raise ValueError(f"{field.name}: min/max require a numeric field.")
                try:
                    bound = Decimal(raw)
                except InvalidOperation as error:
                    raise ValueError(f"{field.name}: invalid numeric bound.") from error
                if not bound.is_finite():
                    raise ValueError(f"{field.name}: bounds must be finite.")
                if field.python_type == "int" and bound != bound.to_integral_value():
                    raise ValueError(f"{field.name}: integer bounds must be whole numbers.")
                if field.python_type == "float" and abs(bound) > Decimal("1.7976931348623157e308"):
                    raise ValueError(f"{field.name}: bound exceeds float range.")
                bounds.append(bound)
            if all(bound is not None for bound in bounds) and bounds[0] > bounds[1]:
                raise ValueError(f"{field.name}: min cannot exceed max.")
            if field.pattern is not None:
                if field.python_type not in {"str", "text"} or not field.pattern:
                    raise ValueError(f"{field.name}: regex= requires a string and a nonempty pattern.")
                try:
                    re.compile(field.pattern)
                except re.error as error:
                    raise ValueError(f"{field.name}: invalid regex: {error}") from error
            if field.foreign_key is not None and field.foreign_key.strip() == "":
                raise ValueError(f"{field.name}: Foreign key cannot be empty.")
