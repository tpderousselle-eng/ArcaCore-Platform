from tools.core.engine import (
    PROJECT_ROOT,
    render_template,
)

from tools.core.module_definition import (
    ModuleDefinition,
    module_output_path,
)


def generate_router(module: ModuleDefinition):

    output = module_output_path(PROJECT_ROOT, "api", module)

    render_template(
        template_name="router.j2",
        output_path=output,
        class_name=module.class_name,
        module=module.module_name,
        fields=module.fields,
        soft_delete=module.soft_delete,
        audit_fields=module.audit_fields is not None,
        actor_type=(
            {"int": "int", "str": "str", "uuid": "UUID"}[
                module.audit_fields.python_type
            ]
            if module.audit_fields is not None
            else None
        ),
        primary_key_type=next(
            (
                {"int": "int", "str": "str", "uuid": "UUID"}.get(
                    field.python_type, "str"
                )
                for field in module.fields
                if field.primary_key
            ),
            "int",
        ),
    )
