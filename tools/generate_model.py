from tools.core.engine import (
    PROJECT_ROOT,
    render_template,
)

from tools.core.module_definition import (
    ModuleDefinition,
)

from tools.renderers.sqlalchemy_renderer import (
    SQLAlchemyRenderer,
)


def generate_model(module: ModuleDefinition):

    output = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "models"
        / f"{module.module_name}.py"
    )

    rendered_fields = []

    has_relationships = False

    for field in module.fields:

        relationship_arguments = (
            SQLAlchemyRenderer.render_relationship(
                field,
            )
        )

        if relationship_arguments:
            has_relationships = True

        rendered_fields.append(
            {
                "name": field.name,
                "arguments": SQLAlchemyRenderer.render(
                    field,
                ),
                "relationship_name": field.relationship_name,
                "relationship_arguments": relationship_arguments,
            }
        )

    render_template(
        template_name="model.j2",
        output_path=output,
        class_name=module.class_name,
        table_name=module.table_name,
        fields=rendered_fields,
        has_relationships=has_relationships,
    )