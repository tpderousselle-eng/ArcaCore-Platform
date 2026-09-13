"""31.2: public relationships, exact constraints/access and dependency planning."""
from dataclasses import replace
from contextlib import ExitStack, redirect_stdout
from io import StringIO
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arcadev import ArcaCoreGenerationRequest
from arcadev.arcacore_generation_request import ModuleGenerationRequest, module_definition, _standard_capability, standard_module_capability
from arcadev.generation_dependencies import generation_dependency_plan
from arcadev.state_constraints import constraint_declarations, certify_access, relationship_blocker
from arcadev.backend_generation import generate_backend, GenerationDisposition
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.fixture_arcadev_module_backend import minimal_approved_backend
from tools.test_arcadev_arcacore_generation_request import gaming_request
from tools.test_arcadev_state_fields import field


def public_module(name, declarations, constraints=()):
    """Public-contract TEST input; this is not an approved application request."""
    return ModuleGenerationRequest("module_" + name, "entity_" + name, name, tuple(declarations), (),
        tuple(d.split(":")[0] for d in declarations), (), "test_naming", tuple(constraints))


def relation_modules(modifier="one_to_many(Parent,children)"):
    return (public_module("child", ("id:str:pk", "parent_id:str:fk=parents.id:" + modifier)),
        public_module("parent", ("id:str:pk",)))


class StateRelationsTest(unittest.TestCase):
    def test_many_to_one_and_reverse_one_to_many_contract(self):
        child, parent = relation_modules()
        f = module_definition(child).fields[1]
        self.assertEqual((f.relationship_type, f.relationship_class, f.backref, f.foreign_key),
            ("many_to_one", "Parent", "children", "parents.id"))
        self.assertEqual(generation_dependency_plan((child, parent)).ordered_module_request_ids, (parent.module_request_id, child.module_request_id))

    def test_one_to_one_public_contract(self):
        child, parent = relation_modules("one_to_one")
        f = module_definition(child).fields[1]
        self.assertTrue(f.unique)
        self.assertEqual((f.relationship_type, f.backref), ("one_to_one", "child"))
        self.assertEqual(len(generation_dependency_plan((child, parent)).dependencies), 1)

    def test_many_to_many_public_contract_and_dependency(self):
        tag = public_module("tag", ("id:str:pk",))
        post = public_module("post", ("id:str:pk", "tags:many_to_many(Tag,tags.id)"))
        plan = generation_dependency_plan((post, tag))
        self.assertEqual(plan.ordered_module_request_ids, (tag.module_request_id, post.module_request_id))
        self.assertEqual(plan.dependencies[0].relationship_type, "many_to_many")

    def test_certified_public_self_relationship_is_not_a_module_order_cycle(self):
        node = public_module("node", ("id:str:pk", "parent_id:str:nullable:fk=nodes.id:self_relationship(children)"))
        plan = generation_dependency_plan((node,))
        self.assertEqual(plan.ordered_module_request_ids, (node.module_request_id,))
        self.assertEqual(plan.dependencies[0].source_module_request_id, plan.dependencies[0].target_module_request_id)
        self.assertIn("remote_side=[id]", SQLAlchemyRenderer.render_relationship(module_definition(node).fields[1]))

    def test_cascade_and_passive_delete_metadata_are_preserved(self):
        child, parent = relation_modules("one_to_many(Parent,children):cascade_delete:passive_deletes")
        field = module_definition(child).fields[1]
        self.assertIn('ForeignKey("parents.id", ondelete="CASCADE")', SQLAlchemyRenderer.render(field))
        self.assertIn('cascade="save-update, merge, delete", passive_deletes=True', " ".join(SQLAlchemyRenderer.render_relationship(field)))
        self.assertEqual(len(generation_dependency_plan((child, parent)).dependencies), 1)

    def test_all_logical_cardinalities_and_deletion_rules_stay_blocked_without_binding(self):
        for source, target in (("many", "one"), ("one", "many"), ("one", "zero_or_one"), ("many", "many")):
            for deletion in (None, "retain", "restrict", "detach", "delete_dependent"):
                edge = SimpleNamespace(relationship_id="edge", source_cardinality=source, target_cardinality=target,
                    ownership="source_owns_target", deletion_behavior=deletion)
                reason = relationship_blocker(edge)
                self.assertIn("no approved FK-field binding", reason)
                self.assertIn("deletion=" + str(deletion), reason)
        with self.assertRaises(ValueError):
            module_definition(relation_modules("one_to_many:passive_deletes")[0])

    def test_missing_dependency_wrong_key_and_type_rejected(self):
        child, parent = relation_modules()
        with self.assertRaisesRegex(ValueError, "Missing"):
            generation_dependency_plan((child,))
        for declarations in (("other:str:pk",), ("id:int:pk",)):
            with self.assertRaises(ValueError):
                generation_dependency_plan((child, replace(parent, field_declarations=declarations)))

    def test_cycle_rejected(self):
        first = public_module("first", ("id:str:pk", "second_id:str:fk=seconds.id:one_to_many(Second,firsts)"))
        second = public_module("second", ("id:str:pk", "first_id:str:fk=firsts.id:one_to_many(First,seconds)"))
        with self.assertRaisesRegex(ValueError, "cycles"):
            generation_dependency_plan((first, second))

    def test_reverse_collision_and_incomplete_legacy_fk_rejected(self):
        child, parent = relation_modules()
        with self.assertRaisesRegex(ValueError, "collide"):
            generation_dependency_plan((child, replace(parent, field_declarations=("id:str:pk", "children:str"))))
        with self.assertRaisesRegex(ValueError, "bare foreign key"):
            generation_dependency_plan((replace(child, field_declarations=("id:str:pk", "parent_id:str:fk=parents.id")), parent))

    def test_plan_is_canonical_and_retains_referential_provenance(self):
        child, parent = relation_modules()
        one = generation_dependency_plan((child, parent))
        self.assertEqual(one.canonical_json(), generation_dependency_plan((parent, child)).canonical_json())
        edge = one.dependencies[0]
        self.assertEqual((edge.source_entity_id, edge.target_entity_id, edge.source_field_name, edge.target_field_name),
            (child.entity_id, parent.entity_id, "parent_id", "id"))

    def test_public_relationship_fixture_generates_and_compiles_in_temporary_workspace(self):
        from tools.generate import generate_module
        import tools.registry.registry as registry
        child, parent = relation_modules("one_to_many(Parent,children):cascade_delete:passive_deletes")
        modules = {m.module_request_id: m for m in (child, parent)}
        with TemporaryDirectory(prefix="arcadev-relations-") as directory:
            root = Path(directory)
            registry_path = root / "tools/registry/models.json"
            registry_path.parent.mkdir(parents=True)
            with ExitStack() as stack:
                for layer in ("model", "schema", "crud", "service", "router"):
                    stack.enter_context(patch.object(importlib.import_module("tools.generate_" + layer), "PROJECT_ROOT", root))
                stack.enter_context(patch.object(registry, "REGISTRY_PATH", registry_path))
                stack.enter_context(redirect_stdout(StringIO()))
                for identity in generation_dependency_plan((child, parent)).ordered_module_request_ids:
                    module = modules[identity]
                    generate_module(module.module_name, list(module.field_declarations))
            for path in root.rglob("*.py"):
                compile(path.read_bytes(), path.name, "exec")
            source = (root / "backend/app/models/child.py").read_text()
            self.assertIn('ForeignKey("parents.id", ondelete="CASCADE")', source)
            self.assertIn('passive_deletes=True', source)
        self.assertFalse(root.exists())

    def test_composite_uniqueness_and_bounded_check_translation(self):
        fields = tuple(replace(field("integer" if name == "quantity" else "string"), field_id=name, name=name) for name in ("a", "b", "quantity"))
        entity = SimpleNamespace(approved_fields=fields, identity_field_ids=("id",))
        constraints = (SimpleNamespace(kind="composite_unique", field_ids=("b", "a"), value_json="true"),
            SimpleNamespace(kind="min_value", field_ids=("quantity",), value_json="0"),
            SimpleNamespace(kind="max_value", field_ids=("quantity",), value_json="10"))
        declarations = constraint_declarations(entity, constraints, {f.name: f.name for f in fields}, parse_fields("sample", ["a:str", "b:str", "quantity:int"]))
        self.assertEqual(declarations, ("check(quantity <= 10)", "check(quantity >= 0)", "unique_together(a,b)"))
        definition = module_definition(public_module("sample", ("id:str:pk", "a:str", "b:str", "quantity:int"), declarations))
        self.assertEqual(definition.unique_constraints[0].columns, ["a", "b"])
        self.assertEqual(len(definition.check_constraints), 2)

    def test_prose_expressions_and_unrepresented_constraints_rejected(self):
        entity = SimpleNamespace(approved_fields=(replace(field("integer"), field_id="quantity"),), identity_field_ids=("id",))
        for kind, value in (("pattern", '".*"'), ("lifecycle_invariant", '"immutable_after_terminal"'), ("min_value", '"__import__(1)"'), ("min_value", "2147483648")):
            with self.assertRaises(ValueError):
                constraint_declarations(entity, (SimpleNamespace(kind=kind, field_ids=("quantity",), value_json=value),), {"quantity": "quantity"}, parse_fields("sample", ["quantity:int"]))
        with self.assertRaises(ValueError):
            module_definition(public_module("sample", ("id:str:pk",), ("check(__import__('os'))",)))

    def test_lookup_is_not_automatically_an_index(self):
        entity = SimpleNamespace(identity_field_ids=("id",))
        certify_access(entity, (SimpleNamespace(field_ids=("id",), unique=True),))
        with self.assertRaisesRegex(ValueError, "not a database index"):
            certify_access(entity, (SimpleNamespace(field_ids=("title",), unique=True),))
        with self.assertRaises(ValueError):
            certify_access(entity, (SimpleNamespace(field_ids=("id",), unique=False),))
        # Existing physical index grammar is audited separately; a logical
        # lookup record does not authorize selecting it.
        indexes = parse_indexes("samples", ["index(a,b)"], parse_fields("sample", ["a:str", "b:str"]))
        self.assertEqual(indexes[0].columns, ["a", "b"])

    def test_scoped_standard_crud_requires_exact_explicit_authority(self):
        self.assertTrue(_standard_capability(standard_module_capability("first")))
        for suffix in (" and publish", " (first) and publish", " (../first)"):
            self.assertFalse(_standard_capability("Manage records with standard ArcaCore CRUD" + suffix))

    def test_nullable_and_json_uniqueness_are_not_over_certified(self):
        from arcadev.state_translation import field_declaration
        for candidate in (field(required=False, unique=True), field("json", unique=True)):
            with self.assertRaisesRegex(ValueError, "equality semantics"):
                field_declaration(candidate, "value")


class ApprovedStateRelationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approved = minimal_approved_backend(constraints=True, module_count=2, domains=True)
        cls.request = ArcaCoreGenerationRequest.create(cls.approved)

    def test_complete_approved_constraint_access_fixture_roundtrip(self):
        request = self.request
        self.assertTrue(request.eligible_for_generation, request.blocking_findings)
        self.assertEqual(len(request.module_requests), 2)
        self.assertEqual(request, ArcaCoreGenerationRequest.from_json(request.canonical_json()))
        module = next(m for m in request.module_requests if m.constraint_declarations)
        self.assertEqual(len(module.source_constraint_ids), 2)
        self.assertEqual(len(module.source_access_ids), 1)
        self.assertEqual(len(module_definition(module).indexes), 0)
        self.assertEqual(self.approved.canonical_json(), request.approved_backend.canonical_json())

    def test_deterministic_declarations_no_generator_during_construction(self):
        with patch("tools.generate.generate_module") as generate:
            again = ArcaCoreGenerationRequest.create(self.approved)
        generate.assert_not_called()
        self.assertEqual(again.canonical_json(), self.request.canonical_json())
        self.assertEqual(tuple(m.module_request_id for m in again.module_requests), again.dependency_plan.ordered_module_request_ids)

    def test_approved_temporary_fixture_compiles_and_cleans(self):
        result = generate_backend(self.request)
        self.assertEqual(result.disposition, GenerationDisposition.GENERATED, result.diagnostics)
        self.assertEqual(result.invocation_count, 2)
        self.assertTrue(result.workspace_cleaned)
        self.assertTrue(result.source_tree_unchanged)
        self.assertEqual(len(result.artifact_manifest.artifacts), 11)

    def test_actual_gaming_studio_remains_blocked(self):
        request = gaming_request()
        self.assertEqual((len(request.blocking_findings), len(request.unsupported_mappings), len(request.required_certification_mappings)), (57, 6, 51))
        self.assertFalse(request.eligible_for_generation)
        self.assertEqual(request.module_requests, ())


if __name__ == "__main__":
    unittest.main()
