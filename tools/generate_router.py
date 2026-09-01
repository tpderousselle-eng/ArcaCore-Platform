from tools.core.engine import (
    PROJECT_ROOT,
    render_template,
)

from tools.core.module_definition import (
    ModuleDefinition,
)


def generate_router(module: ModuleDefinition):

    output = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "api"
        / f"{module.module_name}.py"
    )

    render_template(
        template_name="router.j2",
        output_path=output,
        class_name=module.class_name,
        module=module.module_name,
        fields=module.fields,
    )