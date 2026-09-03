"""Validate a small numeric expression language without evaluating user code."""
import ast
from decimal import Decimal, InvalidOperation
import math
import re


NUMERIC_TYPES = {"int", "float", "decimal"}
OPERATORS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}


def validate_computed_fields(fields):
    by_name = {field.name: field for field in fields}
    for field in fields:
        if field.computed_expression is None:
            continue
        expression = field.computed_expression
        if field.python_type not in NUMERIC_TYPES:
            raise ValueError(f"{field.name}: computed= requires int, float, or decimal.")
        if field.primary_key or field.default is not None or field.foreign_key is not None:
            raise ValueError(f"{field.name}: computed fields cannot have pk, default, or fk modifiers.")
        if field.name in {"id", "created_at", "updated_at", "deleted_at"}:
            raise ValueError(f"{field.name}: generated field name is reserved.")
        if field.python_type == "decimal":
            args = field.type_arguments or []
            if len(args) != 2 or not all(re.fullmatch(r"[0-9]+", arg) for arg in args):
                raise ValueError(f"{field.name}: computed decimals require precision and scale.")
            precision, scale = map(int, args)
            if precision < 1 or scale > precision:
                raise ValueError(f"{field.name}: invalid decimal precision or scale.")
        if not expression or len(expression) > 2000:
            raise ValueError(f"{field.name}: computed expression must contain 1 to 2000 characters.")
        try:
            root = ast.parse(expression, mode="eval").body
        except (SyntaxError, ValueError, RecursionError) as error:
            raise ValueError(f"{field.name}: invalid computed expression.") from error
        if sum(1 for _ in ast.walk(root)) > 100:
            raise ValueError(f"{field.name}: computed expression is too complex.")
        references = set()

        def render(node):
            if isinstance(node, ast.Name):
                source = by_name.get(node.id)
                if source is None:
                    raise ValueError(f"{field.name}: unknown computed reference: {node.id}")
                if (
                    source.computed_expression is not None
                    or source.hybrid_expression is not None
                    or source.encrypted
                ):
                    raise ValueError(f"{field.name}: computed fields require stored source columns.")
                if source.python_type not in NUMERIC_TYPES:
                    raise ValueError(f"{field.name}: computed references must be numeric columns.")
                if field.python_type == "int" and source.python_type != "int":
                    raise ValueError(f"{field.name}: integer expressions require integer source columns.")
                if source.nullable and not field.nullable:
                    raise ValueError(f"{field.name}: add nullable when referencing nullable columns.")
                references.add(node.id)
                return '"' + node.id.replace('"', '""') + '"'
            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                literal = ast.get_source_segment(expression, node).replace("_", "")
                try:
                    value = Decimal(literal)
                except InvalidOperation as error:
                    raise ValueError(f"{field.name}: use decimal numeric literals.") from error
                if not value.is_finite() or (type(node.value) is float and not math.isfinite(node.value)):
                    raise ValueError(f"{field.name}: computed constants must be finite.")
                if field.python_type == "int" and not re.fullmatch(r"[0-9]+", literal):
                    raise ValueError(f"{field.name}: integer expressions require integer literals.")
                return literal
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                sign = "+" if isinstance(node.op, ast.UAdd) else "-"
                return f"({sign}{render(node.operand)})"
            if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
                return f"({render(node.left)} {OPERATORS[type(node.op)]} {render(node.right)})"
            raise ValueError(f"{field.name}: computed expressions support columns, numbers, +, -, and * only.")

        sql = render(root)
        if not references:
            raise ValueError(f"{field.name}: computed expressions must reference a column.")
        field.computed_sql = sql
