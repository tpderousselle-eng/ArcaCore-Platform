import sys

from tools.core.audit_field_parser import parse_audit_fields
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition

from tools.generate_model import generate_model
from tools.generate_schema import generate_schema
from tools.generate_crud import generate_crud
from tools.generate_service import generate_service
from tools.generate_router import generate_router

from tools.registry.registry import Registry
from tools.validators.field_validator import FieldValidator


def generate_module(
    name: str,
    field_strings: list[str],
):
    field_definitions = []
    index_definitions = []
    constraint_definitions = []
    soft_delete = False
    audit_fields = None
    for definition in field_strings:
        if definition == "soft_delete":
            if soft_delete:
                raise ValueError("soft_delete can only be specified once.")
            soft_delete = True
        elif definition in {"index", "partial_index", "expression_index"} or definition.startswith(("index(", "partial_index(", "expression_index(")):
            index_definitions.append(definition)
        elif definition in {"unique_together", "check"} or definition.startswith(("unique_together(", "check(")):
            constraint_definitions.append(definition)
        elif definition == "audit_fields" or definition.startswith("audit_fields("):
            if audit_fields is not None:
                raise ValueError("audit_fields can only be specified once.")
            audit_fields = parse_audit_fields(definition)
        else:
            field_definitions.append(definition)

    fields = parse_fields(name, field_definitions)
    FieldValidator.validate(fields)
    table_name = f"{name.lower()}s"
    indexes = parse_indexes(
        table_name,
        index_definitions,
        fields,
        soft_delete=soft_delete,
        audit_fields=audit_fields is not None,
    )
    uniques, checks = parse_constraints(
        table_name,
        constraint_definitions,
        fields,
        soft_delete=soft_delete,
        audit_fields=audit_fields is not None,
    )

    module = ModuleDefinition(
        name=name,
        class_name=name.capitalize(),
        module_name=name.lower(),
        table_name=table_name,
        fields=fields,
        indexes=indexes,
        soft_delete=soft_delete,
        unique_constraints=uniques,
        check_constraints=checks,
        audit_fields=audit_fields,
    )

    print("=" * 60)
    print(f"Generating module: {module.class_name}")
    print("=" * 60)
    print()

    generate_model(module)
    generate_schema(module)
    generate_crud(module)
    generate_service(module)
    generate_router(module)

    Registry.register(module)

    print()
    print("=" * 60)
    print("Module generated successfully.")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("python -m tools.generate <ModuleName> field:type [additional fields or options]")
        sys.exit(1)

    generate_module(sys.argv[1], sys.argv[2:])
