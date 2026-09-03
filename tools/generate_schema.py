import ast
from decimal import Decimal

from tools.core.computed_parser import validate_computed_fields
from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.field_parser import validate_format
from tools.core.module_definition import ModuleDefinition


SCHEMA_TYPES = {
    "str": "str", "text": "str", "int": "int", "float": "float", "bool": "bool",
    "uuid": "_uuid.UUID", "decimal": "_decimal.Decimal", "json": "_typing.Any",
    "date": "_datetime.date", "datetime": "_datetime.datetime",
}


def schema_type(field):
    validate_format(field)
    if field.format == "email":
        return "_pydantic.EmailStr"
    if field.format == "phone":
        return "_arca_PhoneString"
    if field.format == "slug":
        return "_arca_SlugString"
    if field.python_type == "array":
        return f"list[{SCHEMA_TYPES[field.type_arguments[0]]}]"
    if field.python_type in {"choice", "enum"}:
        if not field.type_arguments:
            return "str"
        return "_typing.Literal[" + ", ".join(repr(value) for value in field.type_arguments) + "]"
    return SCHEMA_TYPES[field.python_type]


def schema_fields(module):
    result = []
    for field in module.fields:
        validate_format(field)
        if field.relationship_type == "many_to_many":
            continue
        annotation = schema_type(field)
        if field.nullable:
            annotation += " | None"
        constraints = []
        for keyword, raw in (("ge", field.minimum), ("le", field.maximum)):
            if raw is not None:
                value = Decimal(raw)
                if field.python_type == "int":
                    rendered = repr(int(value))
                elif field.python_type == "float":
                    rendered = repr(float(value))
                else:
                    rendered = f"_decimal.Decimal({str(value)!r})"
                constraints.append(f"{keyword}={rendered}")
        if field.min_length is not None:
            constraints.append(f"min_length={field.min_length}")
        if field.max_length is not None:
            constraints.append(f"max_length={field.max_length}")
        if field.pattern is not None:
            constraints.append(f"pattern=_re.compile({field.pattern!r})")
        default = []
        if field.default is not None:
            try:
                literal = ast.literal_eval(field.default)
            except (ValueError, SyntaxError):
                # Database expressions stay on the model, never execute in a schema.
                default = ["default=None", "validate_default=False"]
            else:
                if field.python_type == "decimal" and isinstance(literal, (int, float)):
                    default = [f"default=_decimal.Decimal({field.default!r})", "validate_default=True"]
                else:
                    default = [f"default={literal!r}", "validate_default=True"]
        elif field.primary_key and field.python_type in {"int", "uuid"}:
            default = ["default=None", "validate_default=False"]
        elif field.nullable:
            default = ["default=None"]
        response = list(constraints)
        if field.computed_expression is not None:
            response.append("json_schema_extra={'readOnly': True}")
        result.append({
            "name": field.name,
            "annotation": annotation,
            "create": ", ".join(default + constraints),
            "update": ", ".join(["default=None", "validate_default=False"] + constraints),
            "response": ", ".join(response),
            "nullable": field.nullable,
            "computed": field.computed_expression is not None,
        })
    return result


def generate_schema(module: ModuleDefinition):
    validate_computed_fields(module.fields)
    fields = schema_fields(module)
    readonly = tuple(field["name"] for field in fields if field["computed"])
    output = PROJECT_ROOT / "backend" / "app" / "schemas" / f"{module.module_name}.py"
    render_template(
        template_name="schema.j2", output_path=output, class_name=module.class_name,
        fields=fields, writable_fields=[field for field in fields if not field["computed"]],
        has_computed=bool(readonly), readonly=repr(readonly),
        has_phone=any(field.format == "phone" for field in module.fields),
        has_slug=any(field.format == "slug" for field in module.fields),
        implicit_id=not module.has_primary_key,
        nonnullable=repr(tuple(field["name"] for field in fields if not field["nullable"])),
    )
