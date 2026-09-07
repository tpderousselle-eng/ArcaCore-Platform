from tools.core.audit_field_parser import validate_audit_fields
from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.module_definition import ModuleDefinition, module_output_path


def generate_service(module: ModuleDefinition):
    validate_audit_fields(module.audit_fields, module.fields)
    output = module_output_path(PROJECT_ROOT, "services", module)

    render_template(
        template_name="service.j2",
        output_path=output,
        class_name=module.class_name,
        module=module.module_name,
        fields=module.fields,
        soft_delete=module.soft_delete,
        audit_fields=module.audit_fields is not None,
        tenant_contract=module.tenant_contract,
        policy_contract=module.policy_contract,
        policy_roles=(
            {role.name: tuple(role.permissions) for role in module.policy_contract.roles}
            if module.policy_contract else {}
        ),
        policy_denies=(tuple(module.policy_contract.denied_permissions) if module.policy_contract else ()),
    )
