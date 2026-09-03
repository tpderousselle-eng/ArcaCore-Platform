"""Compile a restricted index-expression DSL without executing input code."""

import ast
from decimal import Decimal, InvalidOperation
import math

from tools.core.constraint_parser import parse_check


TEXT_TYPES = {"String", "Text", "Choice"}
NUMERIC_TYPES = {"Integer", "Float", "Numeric"}
SCALAR_TYPES = TEXT_TYPES | NUMERIC_TYPES | {"UUID", "Boolean", "Date", "DateTime", "Enum"}
OPERATORS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}


def parse_expression_index(definition, fields, columns):
    if len(definition) > 4000:
        raise ValueError("expression_index() declarations must not exceed 4000 characters.")
    try:
        root = ast.parse(definition, mode="eval").body
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("Use expression_index(expression,unique=True,where=predicate).") from error
    if not (
        isinstance(root, ast.Call)
        and isinstance(root.func, ast.Name)
        and root.func.id == "expression_index"
        and root.args
    ):
        raise ValueError("expression_index() requires one or more index keys.")
    if sum(1 for _ in ast.walk(root)) > 150:
        raise ValueError("expression_index() declaration is too complex.")
    if all(isinstance(arg, ast.Name) for arg in root.args):
        raise ValueError("expression_index() requires at least one function or arithmetic key.")

    options = {}
    for option in root.keywords:
        if option.arg not in {"where", "unique"} or option.arg in options:
            raise ValueError("expression_index() accepts where and unique once each.")
        options[option.arg] = option.value
    unique = False
    if "unique" in options:
        value = options["unique"]
        if not isinstance(value, ast.Constant) or type(value.value) is not bool:
            raise ValueError("expression_index() unique must be True or False.")
        unique = value.value
    for node in ast.walk(root):
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and not math.isfinite(node.value):
            raise ValueError("expression_index() numeric literals must not overflow to infinity.")

    types = {field.name: field.sqlalchemy_type for field in fields if field.name in columns}
    types.update({name: "DateTime" for name in {"created_at", "updated_at", "deleted_at"} & columns if name not in types})
    if "id" in columns and "id" not in types:
        types["id"] = "Integer"
    references = []
    key_references = set()

    def render(node):
        if isinstance(node, ast.Name):
            if node.id not in columns or types.get(node.id) not in SCALAR_TYPES:
                raise ValueError(f"expression_index(): unknown or unsupported column: {node.id}")
            key_references.add(node.id)
            if node.id not in references:
                references.append(node.id)
            kind = "text" if types[node.id] in TEXT_TYPES else "numeric" if types[node.id] in NUMERIC_TYPES else "scalar"
            return '"' + node.id.replace('"', '""') + '"', kind
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            literal = ast.get_source_segment(definition, node).replace("_", "")
            try:
                value = Decimal(literal)
            except InvalidOperation as error:
                raise ValueError("expression_index() requires decimal numeric literals.") from error
            if not value.is_finite():
                raise ValueError("expression_index() numeric literals must be finite.")
            return literal, "numeric"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(ord(char) < 32 or char == "\\" for char in node.value):
                raise ValueError("expression_index() strings cannot contain controls or backslashes.")
            return "'" + node.value.replace("'", "''") + "'", "text"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand, kind = render(node.operand)
            if kind != "numeric":
                raise ValueError("expression_index() unary operators require numeric operands.")
            sign = "+" if isinstance(node.op, ast.UAdd) else "-"
            return f"({sign}{operand})", "numeric"
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, left_kind = render(node.left)
            right, right_kind = render(node.right)
            if left_kind != "numeric" or right_kind != "numeric":
                raise ValueError("expression_index() arithmetic requires numeric operands.")
            return f"({left} {OPERATORS[type(node.op)]} {right})", "numeric"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = node.func.id
            if function not in {"lower", "upper", "length", "abs"}:
                raise ValueError("expression_index() supports lower, upper, length, and abs only.")
            if len(node.args) != 1 or node.keywords:
                raise ValueError(f"expression_index() {function} requires one positional argument.")
            argument, kind = render(node.args[0])
            required = "numeric" if function == "abs" else "text"
            if kind != required:
                raise ValueError(f"expression_index() {function} requires a {required} argument.")
            result_kind = "numeric" if function in {"length", "abs"} else "text"
            return f"{function}({argument})", result_kind
        raise ValueError("expression_index() supports local columns, literals, approved functions, +, -, and * only.")

    expressions = []
    for argument in root.args:
        key_references.clear()
        sql, _ = render(argument)
        if not key_references:
            raise ValueError("Every expression_index() key must reference a column.")
        if sql in expressions:
            raise ValueError("expression_index() cannot repeat a normalized key.")
        expressions.append(sql)

    where = None
    if "where" in options:
        source = ast.get_source_segment(definition, options["where"])
        try:
            where = parse_check(source, columns)
        except ValueError as error:
            raise ValueError(str(error).replace("check()", "expression_index() where")) from error
    return references, expressions, where, unique
