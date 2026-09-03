import ast
from hashlib import sha256
import json
import math
import re

from tools.core.constraint_parser import parse_check
from tools.core.expression_index_parser import parse_expression_index
from tools.core.field_parser import Field
from tools.core.module_definition import CompositeIndex


def parse_partial_index(definition: str, columns: set[str]):
    try:
        root = ast.parse(definition, mode="eval").body
    except (SyntaxError, ValueError) as error:
        raise ValueError("Use partial_index(column,where=expression,unique=True).") from error
    if not (
        isinstance(root, ast.Call)
        and isinstance(root.func, ast.Name)
        and root.func.id == "partial_index"
        and root.args
        and all(isinstance(arg, ast.Name) for arg in root.args)
    ):
        raise ValueError("partial_index() requires one or more plain column names.")

    options = {}
    for option in root.keywords:
        if option.arg not in {"where", "unique"} or option.arg in options:
            raise ValueError("partial_index() accepts where and unique once each.")
        options[option.arg] = option.value
    if "where" not in options:
        raise ValueError("partial_index() requires where=expression.")
    unique = False
    if "unique" in options:
        value = options["unique"]
        if not isinstance(value, ast.Constant) or type(value.value) is not bool:
            raise ValueError("partial_index() unique must be True or False.")
        unique = value.value

    for node in ast.walk(options["where"]):
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and not math.isfinite(node.value):
            raise ValueError("partial_index() numeric literals must not overflow to infinity.")
    expression = ast.get_source_segment(definition, options["where"])
    try:
        where = parse_check(expression, columns)
    except ValueError as error:
        raise ValueError(str(error).replace("check()", "partial_index() where")) from error
    return [arg.id for arg in root.args], where, unique


def parse_indexes(
    table_name: str,
    definitions: list[str],
    fields: list[Field],
    soft_delete: bool = False,
) -> list[CompositeIndex]:
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
    if soft_delete:
        columns.add("deleted_at")
    if not any(field.primary_key for field in fields):
        columns.add("id")

    indexes = []
    seen_names = set()
    for definition in definitions:
        where, unique, expressions = None, False, None
        partial = definition == "partial_index" or definition.startswith("partial_index(")
        expression = definition == "expression_index" or definition.startswith("expression_index(")
        if expression:
            selected, expressions, where, unique = parse_expression_index(definition, fields, columns)
            label = "expression_index()"
        elif partial:
            selected, where, unique = parse_partial_index(definition, columns)
            label = "partial_index()"
        else:
            match = re.fullmatch(r"index\(([^()]*)\)", definition)
            if not match:
                raise ValueError("Composite indexes must use index(column1,column2).")
            selected = [column.strip() for column in match.group(1).split(",")]
            if len(selected) < 2 or not all(selected):
                raise ValueError("index() requires at least two non-empty column names.")
            label = "index()"
        if len(set(selected)) != len(selected):
            raise ValueError(f"{label} cannot repeat a column.")
        for column in selected:
            if column not in columns:
                raise ValueError(f"{label}: unknown or non-column field: {column}")

        name = f"ix_{table_name}_{'_'.join(selected)}"
        if expression:
            identity = json.dumps([expressions, where, unique], ensure_ascii=False)
            digest = sha256(identity.encode("utf-8")).hexdigest()[:10]
            name += f"_expr_{digest}"
        elif partial:
            identity = json.dumps([selected, where, unique], ensure_ascii=False)
            digest = sha256(identity.encode("utf-8")).hexdigest()[:10]
            name += f"_partial_{digest}"
        # Keep generated names within PostgreSQL's identifier byte limit.
        if len(name.encode("utf-8")) > 63:
            digest = sha256(name.encode("utf-8")).hexdigest()[:10]
            prefix = name.encode("utf-8")[:52].decode("utf-8", errors="ignore")
            name = f"{prefix}_{digest}"
        if name in seen_names:
            raise ValueError(f"Duplicate index name: {name}")
        seen_names.add(name)
        indexes.append(CompositeIndex(name=name, columns=selected, where=where, unique=unique, expressions=expressions))

    return indexes
