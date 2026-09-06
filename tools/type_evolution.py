"""Deterministic compatibility decisions for bounded type and enum changes."""

from dataclasses import dataclass
from enum import Enum

from tools.schema_evolution import ChangeKind, SchemaChange


class TypeCompatibility(str, Enum):
    SAFE_WIDENING = "SAFE_WIDENING"
    REQUIRES_VALIDATION = "REQUIRES_VALIDATION"
    REQUIRES_TRANSFORMATION_POLICY = "REQUIRES_TRANSFORMATION_POLICY"
    POTENTIALLY_DESTRUCTIVE = "POTENTIALLY_DESTRUCTIVE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class TypeTransitionDecision:
    classification: TypeCompatibility
    rationale: str
    reversible_without_validation: bool = False

    def canonical_dict(self):
        return {
            "classification": self.classification.value,
            "rationale": self.rationale,
            "reversible_without_validation": self.reversible_without_validation,
        }


def _positive_int(value, label):
    if type(value) is not int or value < 1 or value > 1_000_000:
        raise ValueError(f"{label} must be a bounded positive integer or null.")
    return value


def _decimal(state):
    values = state.get("type_arguments")
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("Decimal transitions require precision and scale.")
    try:
        precision, scale = (int(value) for value in values)
    except (TypeError, ValueError) as error:
        raise ValueError("Decimal transition metadata must be numeric.") from error
    if precision < 1 or precision > 1000 or scale < 0 or scale > precision:
        raise ValueError("Decimal precision and scale are invalid.")
    return precision, scale


def classify_type_transition(change: SchemaChange) -> TypeTransitionDecision:
    """Compute compatibility from canonical states; callers cannot supply a decision."""

    if not isinstance(change, SchemaChange) or change.kind != ChangeKind.FIELD_TYPE_CHANGED:
        raise ValueError("Type compatibility requires a field-type SchemaChange.")
    if not isinstance(change.before, dict) or not isinstance(change.after, dict):
        raise ValueError("Type transition states must be mappings.")
    old, new = change.before, change.after
    old_type, new_type = old.get("python_type"), new.get("python_type")
    if not isinstance(old_type, str) or not isinstance(new_type, str):
        raise ValueError("Type transition states require known type names.")
    if old_type == new_type == "str":
        old_length, new_length = old.get("max_length"), new.get("max_length")
        if old_length is not None:
            _positive_int(old_length, "Old string length")
        if new_length is not None:
            _positive_int(new_length, "New string length")
        if old_length is not None and (new_length is None or new_length > old_length):
            return TypeTransitionDecision(TypeCompatibility.SAFE_WIDENING, "The string bound only increases.")
        if old_length == new_length:
            return TypeTransitionDecision(TypeCompatibility.UNSUPPORTED, "No material string type transition exists.")
        return TypeTransitionDecision(TypeCompatibility.POTENTIALLY_DESTRUCTIVE, "The string bound may truncate existing values.")
    if old_type == "str" and new_type == "text":
        return TypeTransitionDecision(TypeCompatibility.SAFE_WIDENING, "Bounded or variable string widens to text.")
    if old_type == new_type == "decimal":
        old_precision, old_scale = _decimal(old)
        new_precision, new_scale = _decimal(new)
        if new_scale == old_scale and new_precision > old_precision:
            return TypeTransitionDecision(TypeCompatibility.SAFE_WIDENING, "Decimal precision increases without reducing scale.")
        if new_precision < old_precision or new_scale < old_scale:
            return TypeTransitionDecision(TypeCompatibility.POTENTIALLY_DESTRUCTIVE, "Decimal precision or scale reduction may lose data.")
        return TypeTransitionDecision(TypeCompatibility.REQUIRES_VALIDATION, "Decimal scale changes require explicit data validation.")
    if old_type == "int" and new_type == "decimal":
        precision, scale = _decimal(new)
        if precision >= 19 and scale == 0:
            return TypeTransitionDecision(TypeCompatibility.SAFE_WIDENING, "A signed 64-bit integer fits the target numeric range.")
        return TypeTransitionDecision(TypeCompatibility.REQUIRES_VALIDATION, "The numeric target may not contain every integer.")
    if old_type == "float" and new_type == "int":
        return TypeTransitionDecision(TypeCompatibility.POTENTIALLY_DESTRUCTIVE, "Float to integer can round or reject values.")
    if old_type == "text" and new_type == "str":
        return TypeTransitionDecision(TypeCompatibility.REQUIRES_VALIDATION, "Text to string requires a target-length proof.")
    if old_type == "uuid" and new_type == "str":
        return TypeTransitionDecision(TypeCompatibility.REQUIRES_TRANSFORMATION_POLICY, "UUID representation changes require an explicit bounded conversion.")
    if old_type == "json" or new_type == "json" or old_type == "array" or new_type == "array":
        return TypeTransitionDecision(TypeCompatibility.UNSUPPORTED, "JSON and array representation changes are not supported.")
    return TypeTransitionDecision(TypeCompatibility.UNSUPPORTED, "This scalar conversion has no approved compatibility rule.")


def added_enum_values(change: SchemaChange) -> tuple[str, ...]:
    if not isinstance(change, SchemaChange) or change.kind != ChangeKind.ENUM_CHANGED:
        raise ValueError("Enum compatibility requires an enum SchemaChange.")
    if not isinstance(change.before, dict) or not isinstance(change.after, dict):
        raise ValueError("Enum transition states must be mappings.")
    old_values, new_values = change.before.get("values"), change.after.get("values")
    old_name, new_name = change.before.get("name"), change.after.get("name")
    if not isinstance(old_values, list) or not isinstance(new_values, list) or old_name != new_name:
        raise ValueError("Enum transition metadata is incompatible.")
    if not old_values or new_values[:len(old_values)] != old_values or len(new_values) == len(old_values):
        raise ValueError("Only append-only enum evolution is supported.")
    return tuple(new_values[len(old_values):])
