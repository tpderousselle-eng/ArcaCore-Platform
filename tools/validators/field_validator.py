from decimal import Decimal, InvalidOperation
from keyword import iskeyword
import re
from re import _parser as regex_parser

from tools.core.field_parser import Field, validate_format
from tools.core.custom_validator_parser import validate_custom_validators
from tools.core.encrypted_field_parser import validate_encrypted_fields
from tools.core.hybrid_property_parser import validate_hybrid_properties


_UNSAFE_REPEAT_CONTENT = {
    regex_parser.ASSERT,
    regex_parser.ASSERT_NOT,
    regex_parser.BRANCH,
    regex_parser.GROUPREF,
    regex_parser.GROUPREF_EXISTS,
    regex_parser.MAX_REPEAT,
    regex_parser.MIN_REPEAT,
    regex_parser.POSSESSIVE_REPEAT,
}


def _contains_unsafe_repeat_content(tokens) -> bool:
    for operation, argument in tokens:
        if operation in _UNSAFE_REPEAT_CONTENT:
            return True
        if operation is regex_parser.SUBPATTERN and _contains_unsafe_repeat_content(argument[-1]):
            return True
        if operation is regex_parser.ATOMIC_GROUP and _contains_unsafe_repeat_content(argument):
            return True
    return False


def _validate_regex_cost(pattern: str) -> None:
    """Reject constructs with no defensible linear-time runtime bound."""

    if len(pattern) > 512:
        raise ValueError("regex patterns may not exceed 512 characters.")
    parsed = regex_parser.parse(pattern, 0)
    repeat_count = 0

    def visit(tokens) -> None:
        nonlocal repeat_count
        for operation, argument in tokens:
            if operation in {regex_parser.GROUPREF, regex_parser.GROUPREF_EXISTS}:
                raise ValueError("regex backreferences and conditional groups are not supported.")
            if operation in {regex_parser.ASSERT, regex_parser.ASSERT_NOT}:
                raise ValueError("regex lookaround assertions are not supported.")
            if operation in {
                regex_parser.MAX_REPEAT,
                regex_parser.MIN_REPEAT,
                regex_parser.POSSESSIVE_REPEAT,
            }:
                repeat_count += 1
                if repeat_count > 1:
                    raise ValueError("regex patterns may contain only one repetition operator.")
                repeated = argument[-1]
                if _contains_unsafe_repeat_content(repeated):
                    raise ValueError("regex nested or ambiguous repetition is not supported.")
                visit(repeated)
            elif operation is regex_parser.SUBPATTERN:
                visit(argument[-1])
            elif operation is regex_parser.BRANCH:
                for branch in argument[1]:
                    visit(branch)
            elif operation is regex_parser.ATOMIC_GROUP:
                visit(argument)

    visit(parsed)


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
                    _validate_regex_cost(field.pattern)
                except re.error as error:
                    raise ValueError(f"{field.name}: invalid regex: {error}") from error
                except ValueError as error:
                    raise ValueError(f"{field.name}: unsafe regex: {error}") from error
            if field.foreign_key is not None and field.foreign_key.strip() == "":
                raise ValueError(f"{field.name}: Foreign key cannot be empty.")
