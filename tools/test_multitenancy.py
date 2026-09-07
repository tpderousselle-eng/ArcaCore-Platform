import unittest

from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition, validate_module_definition
from tools.multitenancy import (TenantContext, TenantContract, reject_tenant_spoofing,
                               tenant_unique_columns, trusted_tenant_id)
from tools.test_composite_indexes import run_generation


class MultitenancyTest(unittest.TestCase):
    def test_contract_is_deterministic_and_revalidated(self):
        value = TenantContract("organization_id", "uuid")
        self.assertEqual(value.digest, TenantContract.from_dict(value.canonical_dict()).digest)
        with self.assertRaises(ValueError): TenantContract.from_dict({"key": "tenant_id", "python_type": "str", "evil": 1})

    def test_context_fails_closed(self):
        with self.assertRaises(PermissionError): trusted_tenant_id(None)
        with self.assertRaises(PermissionError): TenantContext(None)
        self.assertEqual(trusted_tenant_id(TenantContext("a")), "a")

    def test_payload_cannot_spoof_tenant(self):
        with self.assertRaises(ValueError): reject_tenant_spoofing({"tenant_id": "other"})
        self.assertEqual(reject_tenant_spoofing({"name": "x"}), {"name": "x"})

    def test_uniqueness_is_tenant_scoped_unless_global(self):
        contract = TenantContract()
        self.assertEqual(tenant_unique_columns(("slug",), contract), ("tenant_id", "slug"))
        self.assertEqual(tenant_unique_columns(("slug",), contract, global_scope=True), ("slug",))

    def test_module_metadata_cannot_be_mutated_or_duplicate_owned_key(self):
        module = ModuleDefinition("Record", "Record", "record", "records", parse_fields("Record", ["name:str"]), tenant_contract=TenantContract())
        validate_module_definition(module)
        module.tenant_contract = {"key": "tenant_id"}
        with self.assertRaises(ValueError): validate_module_definition(module)
        with self.assertRaises(ValueError):
            ModuleDefinition("Record", "Record", "record", "records", parse_fields("Record", ["tenant_id:str"]), tenant_contract=TenantContract())

    def test_bad_metadata_rejected(self):
        for key in ("../x", "_private", "x-y", "a" * 64):
            with self.subTest(key=key), self.assertRaises(ValueError): TenantContract(key)

    def test_generated_stack_filters_every_operation_and_rejects_spoofing(self):
        sources, registry = run_generation(["name:str", "soft_delete", "version_column", "tenant_scope"])
        model = sources["model.j2"]
        schema = sources["schema.j2"]
        crud = sources["crud.j2"]
        service = sources["service.j2"]
        router = sources["router.j2"]
        self.assertIn("tenant_id = Column", model)
        self.assertIn("_reject_tenant_input", schema)
        self.assertGreaterEqual(crud.count("Record.tenant_id == tenant_id"), 2)
        self.assertIn('if tenant_id is None:', crud)
        self.assertIn('if "tenant_id" in data:', crud)
        self.assertIn("arcacore_tenant_id", router)
        self.assertIn("tenant_id=tenant_id", service)
        self.assertEqual(registry["Record"]["tenant"], {"key": "tenant_id", "python_type": "str"})


if __name__ == "__main__":
    unittest.main()
