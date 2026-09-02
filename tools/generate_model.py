from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.field_parser import ARRAY_ELEMENT_TYPES
from tools.core.module_definition import ModuleDefinition
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer


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
    required_types = set()

    for field in module.fields:
        relationship_arguments = SQLAlchemyRenderer.render_relationship(field)
        if relationship_arguments:
            has_relationships = True

        required_types.add(field.sqlalchemy_type)
        if field.sqlalchemy_type == "ARRAY":
            required_types.add(ARRAY_ELEMENT_TYPES[field.type_arguments[0]])

        rendered_fields.append(
            {
                "name": field.name,
                "arguments": SQLAlchemyRenderer.render(field),
                "relationship_name": field.relationship_name,
                "relationship_arguments": relationship_arguments,
                "sqlalchemy_type": field.sqlalchemy_type,
                "primary_key": field.primary_key,
            }
        )

    render_template(
        template_name="model.j2",
        output_path=output,
        class_name=module.class_name,
        table_name=module.table_name,
        fields=rendered_fields,
        has_relationships=has_relationships,
        has_primary_key=module.has_primary_key,
        has_uuid="UUID" in required_types,
        has_enum=module.has_enum,
        has_numeric="Numeric" in required_types,
        has_json="JSON" in required_types,
        has_array="ARRAY" in required_types,
        enums=module.enums,
    )
