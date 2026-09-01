import sys

from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition

from generate_model import generate_model
from generate_schema import generate_schema
from generate_crud import generate_crud
from generate_service import generate_service
from generate_router import generate_router


def generate_module(
    name: str,
    field_strings: list[str],
):
    module = ModuleDefinition(
        name=name,
        class_name=name.capitalize(),
        module_name=name.lower(),
        table_name=f"{name.lower()}s",
        fields=parse_fields(field_strings),
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

    print()
    print("=" * 60)
    print("Module generated successfully.")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "python tools/generate_module.py "
            "<ModuleName> field:type ..."
        )
        sys.exit(1)

    generate_module(
        sys.argv[1],
        sys.argv[2:],
    )