import ast
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from tools.core.field_parser import Field
from tools.core.module_definition import CheckRule, UniqueTogether


def constraint_name(value: str) -> str:
    if len(value.encode("utf-8")) <= 63:
        return value
    prefix = value.encode("utf-8")[:52].decode("utf-8", errors="ignore")
    return f"{prefix}_{sha256(value.encode('utf-8')).hexdigest()[:10]}"


def parse_check(expression: str, columns: set[str]) -> str:
    try:
        root = ast.parse(expression, mode="eval").body
    except (SyntaxError, ValueError) as error:
        raise ValueError("check() requires a valid comparison expression.") from error

    def operand(node):
        if isinstance(node, ast.Name):
            if node.id not in columns:
                raise ValueError(f"check(): unknown or non-column field: {node.id}")
            return '"' + node.id.replace('"', '""') + '"'
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "NULL"
            if isinstance(node.value, bool):
                return "TRUE" if node.value else "FALSE"
            if isinstance(node.value, str):
                if any(ord(char) < 32 or char == "\\" for char in node.value):
                    raise ValueError("check() strings cannot contain control characters or backslashes.")
                return "'" + node.value.replace("'", "''") + "'"
            if type(node.value) in {int, float}:
                literal = ast.get_source_segment(expression, node).replace("_", "")
                try:
                    if not Decimal(literal).is_finite():
                        raise ValueError("check() numbers must be finite.")
                except InvalidOperation as error:
                    raise ValueError("check() requires decimal numeric literals.") from error
                return literal
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.USub, ast.UAdd))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in {int, float}
        ):
            sign = "-" if isinstance(node.op, ast.USub) else "+"
            return sign + operand(node.operand)
        raise ValueError("check() operands must be columns or literal values.")

    def predicate(node):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            separator = " AND " if isinstance(node.op, ast.And) else " OR "
            return "(" + separator.join(predicate(value) for value in node.values) + ")"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(NOT {predicate(node.operand)})"
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            raise ValueError("check() requires comparisons joined with and, or, or not.")
        left, right = node.left, node.comparators[0]
        if not isinstance(left, ast.Name) and not isinstance(right, ast.Name):
            raise ValueError("Each check() comparison must reference a column.")
        op = node.ops[0]
        operators = {ast.Eq: "=", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
        if isinstance(op, (ast.Is, ast.IsNot)):
            if not isinstance(right, ast.Constant) or right.value is not None:
                raise ValueError("check() supports is/is not only with None.")
            operator = "IS" if isinstance(op, ast.Is) else "IS NOT"
        else:
            operator = operators.get(type(op))
            if operator is None:
                raise ValueError("Unsupported check() comparison operator.")
            if any(isinstance(value, ast.Constant) and value.value is None for value in (left, right)):
                raise ValueError("Use is None or is not None for check() null comparisons.")
        return f"({operand(left)} {operator} {operand(right)})"

    return predicate(root)


def parse_constraints(
    table_name: str,
    definitions: list[str],
    fields: list[Field],
    soft_delete: bool = False,
) -> tuple[list[UniqueTogether], list[CheckRule]]:
    columns = {
        field.name
        for field in fields
        if (
            field.relationship_type != "many_to_many"
            and field.hybrid_expression is None
            and not field.encrypted
        )
    }
    columns.update({"created_at", "updated_at"})
    if not any(field.primary_key for field in fields):
        columns.add("id")
    if soft_delete:
        columns.add("deleted_at")

    uniques, checks = [], []
    seen_columns, seen_checks, seen_names = set(), set(), set()
    for definition in definitions:
        if definition.startswith("unique_together("):
            match = re.fullmatch(r"unique_together\(([^()]*)\)", definition)
            if not match:
                raise ValueError("Use unique_together(column1,column2).")
            selected = [value.strip() for value in match.group(1).split(",")]
            if len(selected) < 2 or not all(selected):
                raise ValueError("unique_together() requires at least two column names.")
            if len(set(selected)) != len(selected):
                raise ValueError("unique_together() cannot repeat a column.")
            for column in selected:
                if column not in columns:
                    raise ValueError(f"unique_together(): unknown or non-column field: {column}")
            key = frozenset(selected)
            if key in seen_columns:
                raise ValueError("Duplicate unique_together() constraint.")
            seen_columns.add(key)
            name = constraint_name(f"uq_{table_name}_{'_'.join(selected)}")
            uniques.append(UniqueTogether(name, selected))
        elif definition.startswith("check(") and definition.endswith(")"):
            expression = parse_check(definition[6:-1].strip(), columns)
            if expression in seen_checks:
                raise ValueError("Duplicate check() constraint.")
            seen_checks.add(expression)
            digest = sha256(expression.encode("utf-8")).hexdigest()[:10]
            name = constraint_name(f"ck_{table_name}_{digest}")
            checks.append(CheckRule(name, expression))
        else:
            raise ValueError("Use unique_together(columns) or check(expression).")
        if name in seen_names:
            raise ValueError(f"Duplicate constraint name: {name}")
        seen_names.add(name)

    return uniques, checks
