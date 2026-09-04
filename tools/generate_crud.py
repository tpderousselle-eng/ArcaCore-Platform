from tools.core.audit_field_parser import validate_audit_fields
from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.module_definition import ModuleDefinition, module_output_path


def generate_crud(module: ModuleDefinition):
    validate_audit_fields(module.audit_fields, module.fields)
    output = module_output_path(PROJECT_ROOT, "crud", module)

    render_template(
        template_name="crud.j2",
        output_path=output,
        class_name=module.class_name,
        module=module.module_name,
        fields=module.fields,
        soft_delete=module.soft_delete,
        audit_fields=module.audit_fields is not None,
        primary_key_name=module.primary_key_name,
    )
