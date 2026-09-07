"""Focused tenant relationship security and PostgreSQL regression coverage."""

from contextlib import ExitStack
import sys
import types
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition, validate_module_definition
from tools.generate_model import generate_model
from tools.generate_service import generate_service
from tools.multitenancy import TenantContract
from tools.postgresql_test_server import postgresql_test_server
from tools.schema_evolution import ChangeKind, SafetyClassification, plan_schema_evolution


def module(name, fields, tenant=TenantContract("tenant_id", "int")):
    return ModuleDefinition(name, name.capitalize(), name.lower(), f"{name.lower()}s",
                            parse_fields(name, fields), tenant_contract=tenant)


def render(generator, definition):
    captured = {}
    def capture(template_name, output_path, **context):
        source = env.get_template(template_name).render(**context)
        compile(source, str(output_path), "exec")
        captured[template_name] = source
    owner = sys.modules[generator.__module__]
    with patch.object(owner, "render_template", side_effect=capture): generator(definition)
    return next(iter(captured.values()))


class TenantRelationshipGenerationTest(unittest.TestCase):
    def test_all_scalar_relationship_shapes_are_tenant_qualified(self):
        definitions = (
            ["parent_id:int:fk=parents.id:one_to_many:tenant_target"],
            ["profile_id:int:fk=profiles.id:one_to_one:tenant_target"],
            ["parent_id:int:fk=records.id:self_relationship:tenant_target"],
        )
        for fields in definitions:
            with self.subTest(fields=fields):
                source = render(generate_model, module("Record", fields))
                self.assertIn("ForeignKeyConstraint", source)
                self.assertIn('["tenant_id", "', source)
                self.assertIn("uq_records_tenant_id_id", source)

    def test_many_to_many_association_has_two_tenant_qualified_foreign_keys(self):
        source = render(generate_model, module("Record", ["roles:many_to_many(Role):tenant_target"]))
        self.assertIn('Column("tenant_id", Integer, primary_key=True)', source)
        self.assertIn("fk_record_roles_records_tenant", source)
        self.assertIn("fk_record_roles_roles_tenant", source)
        self.assertIn("primaryjoin=", source); self.assertIn("secondaryjoin=", source)

    def test_service_checks_targets_without_existence_or_tenant_disclosure(self):
        source = render(generate_service, module("Record", [
            "parent_id:int:fk=parents.id:one_to_many:tenant_target",
            "roles:many_to_many(Role):tenant_target",
        ]))
        self.assertIn("_validate_tenant_relationships", source)
        self.assertIn("Parent.tenant_id == tenant_id", source)
        self.assertIn('getattr(target, "tenant_id", None) != tenant_id', source)
        self.assertNotIn("target exists", source.lower())
        self.assertGreaterEqual(source.count("Relationship target is inaccessible."), 5)

    def test_global_target_is_explicit_and_global_to_tenant_is_rejected(self):
        scoped = module("Record", ["country_id:int:fk=countries.id:global_target"])
        source = render(generate_model, scoped)
        self.assertNotIn("fk_records_country_id_tenant", source)
        with self.assertRaises(ValueError):
            module("GlobalRecord", ["owner_id:int:fk=owners.id:tenant_target"], tenant=None)

    def test_missing_context_spoofing_rbac_and_metadata_mutation_fail_closed(self):
        definition = module("Record", ["parent_id:int:fk=parents.id:tenant_target"])
        definition.fields[0].relationship_scope = "disabled"
        with self.assertRaises(ValueError): validate_module_definition(definition)
        source = render(generate_service, module("Record", ["parent_id:int:fk=parents.id:tenant_target"]))
        self.assertIn("if tenant_id is None:", source)
        self.assertNotIn('values["tenant_id"]', source)

    def test_custom_uuid_and_string_keys_render_deterministically(self):
        for key, kind in (("identifier", "uuid"), ("code", "str")):
            fields = [f"{key}:{kind}:pk", f"parent_{key}:{kind}:fk=parents.{key}:tenant_target"]
            first = render(generate_model, module("Record", fields))
            second = render(generate_model, module("Record", fields))
            self.assertEqual(first, second)
            self.assertIn(f'"parents.tenant_id", "parents.{key}"', first)

    def test_schema_evolution_records_scope_and_fails_legacy_enable_closed(self):
        previous = module("Record", ["parent_id:int:fk=parents.id"], tenant=None)
        proposed = module("Record", ["parent_id:int:fk=parents.id:tenant_target"])
        plan = plan_schema_evolution(previous, proposed)
        kinds = {change.kind for change in plan.changes}
        self.assertIn(ChangeKind.TENANT_METADATA_CHANGED, kinds)
        self.assertTrue(any(change.safety == SafetyClassification.REQUIRES_DATA_MIGRATION for change in plan.changes))
        self.assertIn('"relationship_scope":"tenant"', plan.canonical_json())


class TenantRelationshipPostgreSQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_context = postgresql_test_server(); cls.server = cls.server_context.__enter__()
        cls.engine = create_engine(cls.server.url)
        cls.base = declarative_base()
        base_module = types.ModuleType("backend.app.db.base"); base_module.Base = cls.base
        cls.module_patch = patch.dict(sys.modules, {"backend.app.db.base": base_module})
        cls.module_patch.start()
        cls.parent = cls._load(module("Parent", ["name:str"]))["Parent"]
        cls.role = cls._load(module("Role", ["name:str"]))["Role"]
        values = cls._load(module("Record", [
            "parent_id:int:fk=parents.id:one_to_many:tenant_target",
            "roles:many_to_many(Role):tenant_target",
        ]))
        cls.record = values["Record"]; cls.association = values["record_roles"]
        cls.node = cls._load(module("Node", [
            "parent_id:int:nullable:fk=nodes.id:self_relationship:tenant_target",
            "name:str",
        ]))["Node"]
        cls.base.metadata.create_all(cls.engine)

    @classmethod
    def _load(cls, definition):
        namespace = {}; exec(render(generate_model, definition), namespace); return namespace

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose(); cls.module_patch.stop(); cls.server_context.__exit__(None, None, None)

    def setUp(self):
        with self.engine.begin() as connection:
            for table in reversed(self.base.metadata.sorted_tables): connection.execute(table.delete())
            connection.execute(insert(self.parent), [
                {"id": 1, "tenant_id": 1, "name": "a"}, {"id": 2, "tenant_id": 2, "name": "b"}])
            connection.execute(insert(self.role), [
                {"id": 1, "tenant_id": 1, "name": "a"}, {"id": 2, "tenant_id": 2, "name": "b"}])

    def test_raw_postgresql_scalar_fk_allows_same_and_denies_cross_tenant(self):
        with self.engine.begin() as connection:
            connection.execute(insert(self.record).values(id=1, tenant_id=1, parent_id=1))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(insert(self.record).values(id=2, tenant_id=1, parent_id=2))

    def test_raw_postgresql_association_allows_same_and_denies_cross_tenant(self):
        with self.engine.begin() as connection:
            connection.execute(insert(self.record).values(id=1, tenant_id=1, parent_id=1))
            connection.execute(insert(self.association).values(tenant_id=1, source_id=1, target_id=1))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(insert(self.association).values(tenant_id=1, source_id=1, target_id=2))

    def test_orm_many_to_many_populates_tenant_and_denies_cross_tenant(self):
        with Session(self.engine) as session:
            role = session.get(self.role, 1)
            record = self.record(id=1, tenant_id=1, parent_id=1, roles=[role])
            session.add(record); session.commit()
        with self.engine.connect() as connection:
            row = connection.execute(self.association.select()).one()
            self.assertEqual(row.tenant_id, 1)
        with Session(self.engine) as session:
            role = session.get(self.role, 2)
            record = self.record(id=2, tenant_id=1, parent_id=1, roles=[role])
            session.add(record)
            with self.assertRaises(IntegrityError): session.commit()

    def test_raw_postgresql_self_relationship_allows_same_and_denies_cross_tenant(self):
        with self.engine.begin() as connection:
            connection.execute(insert(self.node), [
                {"id": 1, "tenant_id": 1, "parent_id": None, "name": "a"},
                {"id": 2, "tenant_id": 2, "parent_id": None, "name": "b"},
                {"id": 3, "tenant_id": 1, "parent_id": 1, "name": "child"},
            ])
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(insert(self.node).values(id=4, tenant_id=1, parent_id=2, name="bad"))


if __name__ == "__main__": unittest.main()
