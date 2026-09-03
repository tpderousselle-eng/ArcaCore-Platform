from tools.core.audit_field_parser import validate_audit_fields
from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.module_definition import ModuleDefinition


def generate_service(module: ModuleDefinition):
    validate_audit_fields(module.audit_fields, module.fields)
    output = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "services"
        / f"{module.module_name}.py"
    )

    render_template(
        template_name="service.j2",
        output_path=output,
        class_name=module.class_name,
        module=module.module_name,
        fields=module.fields,
        soft_delete=module.soft_delete,
        audit_fields=module.audit_fields is not None,
    )
