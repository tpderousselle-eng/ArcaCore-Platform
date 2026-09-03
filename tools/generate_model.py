from tools.core.audit_field_parser import validate_audit_fields
from tools.core.cascade_parser import validate_delete_cascades
from tools.core.computed_parser import validate_computed_fields
from tools.core.encrypted_field_parser import validate_encrypted_fields
from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.field_parser import ARRAY_ELEMENT_TYPES
from tools.core.hybrid_property_parser import validate_hybrid_properties
from tools.core.module_definition import ModuleDefinition
from tools.core.version_column_parser import validate_version_column
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer


def generate_model(module: ModuleDefinition):
    validate_audit_fields(module.audit_fields, module.fields)
    validate_version_column(module.version_column, module.fields)
    validate_encrypted_fields(module.fields)
    validate_computed_fields(module.fields)
    validate_hybrid_properties(module.fields)
    validate_delete_cascades(module.fields, module.table_name)
    output = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "models"
        / f"{module.module_name}.py"
    )

    rendered_fields = []
    associations = []
    hybrid_properties = []
    has_relationships = False
    has_one_to_one = False
    required_types = set()
    if module.audit_fields is not None:
        required_types.add(module.audit_fields.sqlalchemy_type)
    primary_keys = [field.name for field in module.fields if field.primary_key]
    many_targets = set()

    for field in module.fields:
        if field.hybrid_expression is not None:
            hybrid_properties.append({
                "name": field.name,
                "python": field.hybrid_python,
                "class_expression": field.hybrid_class,
            })
            continue
        if field.relationship_type == "many_to_many":
            if len(primary_keys) > 1:
                raise ValueError("many_to_many requires a single source primary key.")
            if field.relationship_class in many_targets:
                raise ValueError("Only one many_to_many relationship per target model is supported.")
            many_targets.add(field.relationship_class)
            source_key = primary_keys[0] if primary_keys else "id"
            associations.append({
                "name": field.association_table,
                "source_reference": f"{module.table_name}.{source_key}",
                "target_reference": f"{field.relationship_table}.{field.relationship_key}",
            })

        relationship_arguments = SQLAlchemyRenderer.render_relationship(field)
        if relationship_arguments:
            has_relationships = True
        if field.relationship_type == "one_to_one":
            has_one_to_one = True

        required_types.add(field.sqlalchemy_type)
        if field.sqlalchemy_type == "ARRAY":
            required_types.add(ARRAY_ELEMENT_TYPES[field.type_arguments[0]])

        rendered_fields.append(
            {
                "name": field.name,
                "arguments": SQLAlchemyRenderer.render(field, module.table_name),
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
        associations=associations,
        hybrid_properties=hybrid_properties,
        indexes=[SQLAlchemyRenderer.render_index(index) for index in module.indexes],
        has_partial_indexes=any(index.where is not None for index in module.indexes),
        has_expression_indexes=any(index.expressions is not None for index in module.indexes),
        unique_constraints=[SQLAlchemyRenderer.render_unique(item) for item in module.unique_constraints],
        check_constraints=[SQLAlchemyRenderer.render_check(item) for item in module.check_constraints],
        soft_delete=module.soft_delete,
        audit_fields=module.audit_fields,
        version_column=module.version_column,
        audit_type=(
            "UUID(as_uuid=True)"
            if module.audit_fields is not None and module.audit_fields.python_type == "uuid"
            else module.audit_fields.sqlalchemy_type if module.audit_fields is not None else None
        ),
        has_relationships=has_relationships,
        has_one_to_one=has_one_to_one,
        has_cascade_delete=any(field.cascade_delete for field in module.fields),
        has_primary_key=module.has_primary_key,
        has_uuid="UUID" in required_types,
        has_enum=module.has_enum,
        has_numeric="Numeric" in required_types,
        has_json="JSON" in required_types,
        has_array="ARRAY" in required_types,
        has_choice="Choice" in required_types,
        has_computed=any(field.computed_expression is not None for field in module.fields),
        has_encrypted=any(field.encrypted for field in module.fields),
        has_hybrid=bool(hybrid_properties),
        has_hybrid_decimal=any(
            field.hybrid_expression is not None and field.python_type == "decimal"
            for field in module.fields
        ),
        enums=module.enums,
    )
