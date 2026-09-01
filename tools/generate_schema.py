from tools.core.engine import (
    PROJECT_ROOT,
    render_template,
)

from tools.core.module_definition import (
    ModuleDefinition,
)


def generate_schema(module: ModuleDefinition):

    output = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "schemas"
        / f"{module.module_name}.py"
    )

    render_template(
        template_name="schema.j2",
        output_path=output,
        class_name=module.class_name,
        fields=module.fields,
    )