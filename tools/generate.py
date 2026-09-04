import sys

from tools.core.audit_field_parser import parse_audit_fields
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition
from tools.core.version_column_parser import parse_version_column
from tools.core.engine import write_bytes_atomic

from tools.generate_model import generate_model
from tools.generate_schema import generate_schema
from tools.generate_crud import generate_crud
from tools.generate_service import generate_service
from tools.generate_router import generate_router

from tools.registry.registry import Registry
import tools.registry.registry as registry_module
from tools.validators.field_validator import FieldValidator


_GENERATED_LAYERS = (
    (generate_model, "models"),
    (generate_schema, "schemas"),
    (generate_crud, "crud"),
    (generate_service, "services"),
    (generate_router, "api"),
)


def _transaction_paths(module: ModuleDefinition) -> tuple:
    outputs = tuple(
        generator.__globals__["PROJECT_ROOT"]
        / "backend"
        / "app"
        / layer
        / f"{module.module_name}.py"
        for generator, layer in _GENERATED_LAYERS
    )
    return (*outputs, registry_module.REGISTRY_PATH)


def _restore_generation(paths, snapshots, absent_directories):
    for path in paths:
        previous = snapshots[path]
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            write_bytes_atomic(path, previous)
    for directory in sorted(absent_directories, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def generate_module(
    name: str,
    field_strings: list[str],
):
    field_definitions = []
    index_definitions = []
    constraint_definitions = []
    soft_delete = False
    audit_fields = None
    version_column = False
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
        elif definition == "version_column" or definition.startswith("version_column("):
            if version_column:
                raise ValueError("version_column can only be specified once.")
            version_column = parse_version_column(definition)
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
        version_column=version_column,
    )
    uniques, checks = parse_constraints(
        table_name,
        constraint_definitions,
        fields,
        soft_delete=soft_delete,
        audit_fields=audit_fields is not None,
        version_column=version_column,
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
        version_column=version_column,
    )

    print("=" * 60)
    print(f"Generating module: {module.class_name}")
    print("=" * 60)
    print()

    transaction_paths = _transaction_paths(module)
    snapshots = {
        path: path.read_bytes() if path.is_file() else None
        for path in transaction_paths
    }
    absent_directories = set()
    for path in transaction_paths:
        directory = path.parent
        while not directory.exists():
            absent_directories.add(directory)
            directory = directory.parent

    try:
        generate_model(module)
        generate_schema(module)
        generate_crud(module)
        generate_service(module)
        generate_router(module)
        Registry.register(module)
    except BaseException:
        _restore_generation(transaction_paths, snapshots, absent_directories)
        raise

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
