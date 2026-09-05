import unittest

from tools.core.audit_field_parser import AuditFieldDefinition
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition
from tools.schema_evolution import ChangeKind, SafetyClassification, plan_schema_evolution


def module(fields, *, indexes=(), constraints=(), audit=False, version=False):
    parsed = parse_fields("item", list(fields))
    unique, checks = parse_constraints("items", list(constraints), parsed, audit_fields=audit, version_column=version)
    composite = parse_indexes("items", list(indexes), parsed, audit_fields=audit, version_column=version)
    return ModuleDefinition(
        "item", "Item", "item", "items", parsed,
        indexes=composite, unique_constraints=unique, check_constraints=checks,
        audit_fields=AuditFieldDefinition("users.id", "int", "Integer") if audit else None,
        version_column=version,
    )


class SchemaEvolutionTest(unittest.TestCase):
    def test_identical_definitions_produce_empty_plan(self):
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str"]))
        self.assertTrue(plan.is_empty)
        self.assertEqual(plan.canonical_json(), '{"changes":[],"module":"item","schema_version":1}\n')

    def test_module_addition(self):
        change = plan_schema_evolution(None, module(["name:str"])).changes[0]
        self.assertEqual((change.kind, change.safety), (ChangeKind.MODULE_ADDED, SafetyClassification.SAFE_ADDITIVE))

    def test_nullable_column_addition_is_safe(self):
        change = plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"])).changes[0]
        self.assertEqual((change.kind, change.safety), (ChangeKind.FIELD_ADDED, SafetyClassification.SAFE_ADDITIVE))

    def test_required_column_addition_requires_data_migration(self):
        change = plan_schema_evolution(module(["name:str"]), module(["name:str", "code:str"])).changes[0]
        self.assertEqual(change.safety, SafetyClassification.REQUIRES_DATA_MIGRATION)

    def test_column_removal_is_destructive(self):
        change = plan_schema_evolution(module(["name:str", "note:text:nullable"]), module(["name:str"])).changes[0]
        self.assertEqual((change.kind, change.safety), (ChangeKind.FIELD_REMOVED, SafetyClassification.POTENTIALLY_DESTRUCTIVE))

    def test_scalar_type_change_is_destructive(self):
        change = plan_schema_evolution(module(["value:int"]), module(["value:str"])).changes[0]
        self.assertEqual((change.kind, change.safety), (ChangeKind.FIELD_TYPE_CHANGED, SafetyClassification.POTENTIALLY_DESTRUCTIVE))

    def test_decimal_precision_change_is_detected(self):
        change = plan_schema_evolution(module(["value:decimal(10,2)"]), module(["value:decimal(12,2)"])).changes[0]
        self.assertEqual(change.kind, ChangeKind.FIELD_TYPE_CHANGED)

    def test_append_only_enum_change_is_safe_additive(self):
        change = plan_schema_evolution(module(["state:enum(draft,live)"]), module(["state:enum(draft,live,archived)"])).changes[0]
        self.assertEqual((change.kind, change.safety), (ChangeKind.ENUM_CHANGED, SafetyClassification.SAFE_ADDITIVE))

    def test_enum_removal_is_destructive(self):
        change = plan_schema_evolution(module(["state:enum(draft,live)"]), module(["state:enum(draft)"])).changes[0]
        self.assertEqual(change.safety, SafetyClassification.POTENTIALLY_DESTRUCTIVE)

    def test_foreign_key_and_relationship_changes_are_detected(self):
        plan = plan_schema_evolution(module(["owner_id:int"]), module(["owner_id:int:fk=users.id"]))
        self.assertEqual({c.kind for c in plan.changes}, {ChangeKind.FOREIGN_KEY_ADDED, ChangeKind.RELATIONSHIP_CHANGED})

    def test_composite_index_changes_are_detected(self):
        plan = plan_schema_evolution(module(["a:str", "b:str"]), module(["a:str", "b:str"], indexes=["index(a,b)"]))
        self.assertEqual(plan.changes[0].kind, ChangeKind.INDEX_ADDED)

    def test_constraint_changes_are_detected(self):
        plan = plan_schema_evolution(module(["a:int", "b:int"]), module(["a:int", "b:int"], constraints=["check(a >= 0)", "unique_together(a,b)"]))
        self.assertEqual([c.kind for c in plan.changes], [ChangeKind.CONSTRAINT_ADDED, ChangeKind.CONSTRAINT_ADDED])

    def test_encrypted_field_changes_are_detected(self):
        plan = plan_schema_evolution(module(["secret:text"]), module(["secret:text:encrypted=ITEM_KEY"]))
        self.assertEqual(plan.changes[0].kind, ChangeKind.ENCRYPTED_METADATA_CHANGED)

    def test_audit_and_version_changes_are_detected(self):
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str"], audit=True, version=True))
        self.assertEqual({c.kind for c in plan.changes}, {ChangeKind.AUDIT_METADATA_CHANGED, ChangeKind.VERSION_METADATA_CHANGED})

    def test_deterministic_order_and_bytes_ignore_field_order(self):
        first = plan_schema_evolution(module(["base:str"]), module(["base:str", "zeta:text:nullable", "alpha:int:nullable"]))
        second = plan_schema_evolution(module(["base:str"]), module(["alpha:int:nullable", "base:str", "zeta:text:nullable"]))
        self.assertEqual(first.canonical_json().encode(), second.canonical_json().encode())
        self.assertEqual([c.target for c in first.changes], ["field:alpha", "field:zeta"])

    def test_hostile_programmatic_metadata_is_rejected_before_planning(self):
        hostile = module(["name:str"])
        hostile.name = "../escape"
        with self.assertRaisesRegex(ValueError, "public ASCII Python identifier"):
            plan_schema_evolution(module(["name:str"]), hostile)

    def test_programmatic_default_injection_is_rejected(self):
        hostile = module(["name:str"])
        hostile.fields[0].default = "__import__('os').system('whoami')"
        with self.assertRaisesRegex(ValueError, "default must be"):
            plan_schema_evolution(module(["name:str"]), hostile)


if __name__ == "__main__":
    unittest.main()
