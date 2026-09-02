import sys

from tools.core.field_parser import parse_fields
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
    fields = parse_fields(
        name,
        field_strings,
    )

    FieldValidator.validate(
        fields,
    )

    module = ModuleDefinition(
        name=name,
        class_name=name.capitalize(),
        module_name=name.lower(),
        table_name=f"{name.lower()}s",
        fields=fields,
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

    Registry.register(
        module,
    )

    print()
    print("=" * 60)
    print("Module generated successfully.")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "python -m tools.generate "
            "<ModuleName> field:type ..."
        )
        sys.exit(1)

    generate_module(
        sys.argv[1],
        sys.argv[2:],
    )