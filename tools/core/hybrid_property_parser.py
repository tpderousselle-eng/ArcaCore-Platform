"""Compile safe instance and SQLAlchemy expressions for hybrid properties."""

import ast
from decimal import Decimal, InvalidOperation
import math
import re


NUMERIC_TYPES = {"int", "float", "decimal"}
TEXT_TYPES = {"str", "text", "choice", "enum"}
OUTPUT_TYPES = NUMERIC_TYPES | {"str", "text"}
OPERATORS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}


def validate_hybrid_properties(fields):
    by_name = {field.name: field for field in fields}
    for field in fields:
        if field.hybrid_expression is None:
            continue
        expression = field.hybrid_expression
        if field.python_type not in OUTPUT_TYPES:
            raise ValueError(
                f"{field.name}: hybrid= requires int, float, decimal, str, or text."
            )
        if field.computed_expression is not None:
            raise ValueError(f"{field.name}: hybrid and computed cannot be combined.")
        if (
            field.primary_key
            or field.default is not None
            or field.foreign_key is not None
            or field.relationship_name is not None
            or field.unique
            or field.index
            or field.cascade_delete
            or field.passive_deletes
        ):
            raise ValueError(
                f"{field.name}: hybrid properties cannot be columns, keys, relationships, "
                "indexes, unique fields, defaults, or delete controls."
            )
        if field.name in {"id", "created_at", "updated_at", "deleted_at"}:
            raise ValueError(f"{field.name}: generated field name is reserved.")
        if field.python_type == "decimal":
            arguments = field.type_arguments or []
            if len(arguments) != 2 or not all(
                re.fullmatch(r"[0-9]+", argument) for argument in arguments
            ):
                raise ValueError(
                    f"{field.name}: hybrid decimals require precision and scale."
                )
            precision, scale = map(int, arguments)
            if precision < 1 or scale > precision:
                raise ValueError(f"{field.name}: invalid decimal precision or scale.")
        if not expression or len(expression) > 2000:
            raise ValueError(
                f"{field.name}: hybrid expression must contain 1 to 2000 characters."
            )
        try:
            root = ast.parse(expression, mode="eval").body
        except (SyntaxError, ValueError, RecursionError) as error:
            raise ValueError(f"{field.name}: invalid hybrid expression.") from error
        if sum(1 for _ in ast.walk(root)) > 100:
            raise ValueError(f"{field.name}: hybrid expression is too complex.")

        references = []

        def render(node):
            if isinstance(node, ast.Name):
                source = by_name.get(node.id)
                if source is None:
                    raise ValueError(
                        f"{field.name}: unknown hybrid reference: {node.id}"
                    )
                if source is field:
                    raise ValueError(
                        f"{field.name}: hybrid properties cannot reference themselves."
                    )
                if (
                    source.computed_expression is not None
                    or source.hybrid_expression is not None
                    or source.encrypted
                    or source.relationship_type == "many_to_many"
                ):
                    raise ValueError(
                        f"{field.name}: hybrid expressions require stored scalar columns."
                    )
                if source.python_type in NUMERIC_TYPES:
                    kind = source.python_type
                elif source.python_type in TEXT_TYPES:
                    kind = "text"
                else:
                    raise ValueError(
                        f"{field.name}: unsupported hybrid reference: {node.id}"
                    )
                if source.nullable and not field.nullable:
                    raise ValueError(
                        f"{field.name}: add nullable when referencing nullable columns."
                    )
                if node.id not in references:
                    references.append(node.id)
                return f"self.{node.id}", f"cls.{node.id}", kind

            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                literal = ast.get_source_segment(expression, node).replace("_", "")
                try:
                    number = Decimal(literal)
                except InvalidOperation as error:
                    raise ValueError(
                        f"{field.name}: use decimal numeric literals."
                    ) from error
                if not number.is_finite() or (
                    type(node.value) is float and not math.isfinite(node.value)
                ):
                    raise ValueError(
                        f"{field.name}: hybrid constants must be finite."
                    )
                if field.python_type == "decimal" and type(node.value) is float:
                    value = f"_decimal.Decimal({literal!r})"
                    return value, value, "decimal"
                return literal, literal, "int" if type(node.value) is int else "float"

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(ord(character) < 32 for character in node.value):
                    raise ValueError(
                        f"{field.name}: hybrid strings cannot contain control characters."
                    )
                literal = repr(node.value)
                return literal, literal, "text"

            if isinstance(node, ast.UnaryOp) and isinstance(
                node.op, (ast.UAdd, ast.USub)
            ):
                instance, class_expression, kind = render(node.operand)
                if kind not in NUMERIC_TYPES:
                    raise ValueError(
                        f"{field.name}: hybrid unary operators require numeric operands."
                    )
                sign = "+" if isinstance(node.op, ast.UAdd) else "-"
                return (
                    f"({sign}{instance})",
                    f"({sign}{class_expression})",
                    kind,
                )

            if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
                left_instance, left_class, left_kind = render(node.left)
                right_instance, right_class, right_kind = render(node.right)
                operator = OPERATORS[type(node.op)]
                if operator == "+" and left_kind == right_kind == "text":
                    kind = "text"
                elif left_kind in NUMERIC_TYPES and right_kind in NUMERIC_TYPES:
                    kinds = {left_kind, right_kind}
                    if "decimal" in kinds and "float" in kinds:
                        raise ValueError(
                            f"{field.name}: decimal and float cannot be mixed in a hybrid expression."
                        )
                    kind = (
                        "decimal"
                        if "decimal" in kinds
                        else "float"
                        if "float" in kinds
                        else "int"
                    )
                else:
                    raise ValueError(
                        f"{field.name}: hybrid operands must be compatible numeric values "
                        "or text joined with +."
                    )
                if operator != "+" and kind == "text":
                    raise ValueError(
                        f"{field.name}: text hybrid expressions support + only."
                    )
                return (
                    f"({left_instance} {operator} {right_instance})",
                    f"({left_class} {operator} {right_class})",
                    kind,
                )

            raise ValueError(
                f"{field.name}: hybrid expressions support stored columns, numbers, "
                "strings, +, -, and * only."
            )

        instance, class_expression, result_kind = render(root)
        expected = (
            "text" if field.python_type in {"str", "text"} else field.python_type
        )
        compatible = (
            result_kind == expected
            or expected == "float" and result_kind == "int"
            or expected == "decimal" and result_kind == "int"
        )
        if not compatible:
            raise ValueError(
                f"{field.name}: hybrid expression result does not match {field.python_type}."
            )
        if not references:
            raise ValueError(
                f"{field.name}: hybrid expressions must reference a stored column."
            )

        nullable = [
            name for name in references if by_name[name].nullable
        ]
        if nullable:
            guard = " or ".join(f"self.{name} is None" for name in nullable)
            instance = f"None if {guard} else {instance}"

        field.hybrid_python = instance
        field.hybrid_class = class_expression
        field.hybrid_references = references
