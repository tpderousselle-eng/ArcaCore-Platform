"""31.1: exact public field contracts and unchanged frozen Gaming Studio authority."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arcadev import ArcaCoreGenerationRequest
from arcadev.domain_model_specification import ModelField, LogicalType, DataClassification
from arcadev.state_translation import field_declaration, validate_field_declaration, SCALAR_TYPES
from arcadev.arcacore_generation_request import module_definition, _translate_entity
from tools.core.field_parser import parse_fields
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.generate_schema import schema_fields
from tools.fixture_arcadev_module_backend import minimal_approved_backend
from tools.test_arcadev_arcacore_generation_request import gaming_request, eligible_request


def field(kind="string", **changes):
    return replace(ModelField("field", "value", LogicalType(kind), True, False, True, False,
        DataClassification.INTERNAL, None), **changes)


class StateFieldsTest(unittest.TestCase):
    def test_exact_scalars(self):
        for logical, physical in SCALAR_TYPES.items():
            with self.subTest(logical=logical):
                self.assertEqual(field_declaration(field(logical), "value"), "value:" + physical)

    def test_required_nullable_unique(self):
        for required in (True, False):
            declaration = field_declaration(field(required=required, unique=required), "value")
            parsed = parse_fields("record", [declaration])[0]
            self.assertEqual(parsed.nullable, not required)
            self.assertIn("nullable=" + str(not required), SQLAlchemyRenderer.render(parsed))
            self.assertEqual("unique=True" in SQLAlchemyRenderer.render(parsed), required)

    def test_required_database_column_rejects_null_without_schema(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError
        from tools.test_array import render_model
        _, model, _ = render_model([field_declaration(field(), "value")])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                with self.assertRaises(IntegrityError):
                    connection.execute(text("INSERT INTO samples (value) VALUES (NULL)"))
        finally:
            engine.dispose()

    def test_value_domain_preserves_case_spaces_and_every_value(self):
        values = ("draft", "Published", "in progress", "échec")
        domain = SimpleNamespace(domain_id="domain", values=values)
        declaration = field_declaration(field("enum", value_domain_id="domain"), "state", domains=(domain,))
        parsed = parse_fields("record", [declaration])[0]
        self.assertEqual(tuple(parsed.type_arguments), values)
        rendered = SQLAlchemyRenderer.render(parsed)
        self.assertIn("name='state_choice'", rendered[0])
        self.assertIn("native_enum=False", rendered[0])
        for value in values:
            self.assertIn(repr(value), rendered[0])

    def test_unsupported_domain_never_normalized_or_truncated(self):
        for values in ((" draft", "published"), ("a,b",), ("a(b)",), ("a", "a"), ("",), ("a\nb",)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                field_declaration(field("enum", value_domain_id="domain"), "state",
                    domains=(SimpleNamespace(domain_id="domain", values=values),))
        with self.assertRaises(ValueError):
            field_declaration(field("enum", value_domain_id="missing"), "state")
        with self.assertRaises(ValueError):
            field_declaration(field("enum", value_domain_id="domain", default_json='"extra"'), "state",
                domains=(SimpleNamespace(domain_id="domain", values=("draft", "published")),))

    def test_literal_defaults(self):
        for kind, value in (("string", "a:'quoted'"), ("text", "description"), ("integer", 7), ("boolean", False)):
            declaration = field_declaration(field(kind, default_json=json.dumps(value)), "value")
            parsed = parse_fields("record", [declaration])[0]
            self.assertIn("default=" + repr(value), SQLAlchemyRenderer.render(parsed))

    def test_expressions_are_never_callable_defaults(self):
        for value in ("uuid.uuid4", "func.now", "__import__('os').system('x')"):
            with self.assertRaises(ValueError):
                validate_field_declaration("id:uuid:default=" + value)
            # A string default is still just a string, never an expression.
            self.assertIn("default=" + repr(value), field_declaration(field(default_json=json.dumps(value)), "value"))

    def test_default_types_and_null_distinction(self):
        for kind, value in (("integer", True), ("boolean", 1), ("date", "2026-01-01"), ("json", None), ("uuid", "uuid.uuid4"), ("integer", 2**40)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                field_declaration(field(kind, default_json=json.dumps(value)), "value")
        self.assertEqual(field_declaration(field(required=False, default_json="null"), "value"), "value:str:nullable:default=None")

    def test_identity_defaults_and_mutability(self):
        self.assertEqual(field_declaration(field(mutable=False), "id", primary=True), "id:str:pk")
        self.assertEqual(field_declaration(field("integer", mutable=False, default_json="7"), "id", primary=True), "id:int:pk:default=7")
        for kind in ("integer", "uuid"):
            with self.assertRaises(ValueError):
                field_declaration(field(kind, mutable=False), "id", primary=True)
        with self.assertRaises(ValueError):
            field_declaration(field(mutable=True), "id", primary=True)
        with self.assertRaises(ValueError):
            field_declaration(field(mutable=False), "value")

    def test_arrays_decimal_and_untyped_references_remain_blocked(self):
        for kind in SCALAR_TYPES:
            with self.assertRaisesRegex(ValueError, "ordering and duplication"):
                field_declaration(field(kind, collection=True), "value")
        for kind in ("decimal", "external_reference", "binary_reference"):
            with self.assertRaises(ValueError):
                field_declaration(field(kind), "value")
        self.assertEqual(field_declaration(field(classification=DataClassification.EXTERNAL_IDENTIFIER), "external_id"), "external_id:str")

    def test_literal_request_roundtrip_no_execution_or_authority_loss(self):
        approved = minimal_approved_backend(literal_default=True)
        before = approved.canonical_json()
        with patch("tools.generate.generate_module") as generator:
            request = ArcaCoreGenerationRequest.create(approved)
            self.assertEqual(request, ArcaCoreGenerationRequest.from_json(request.canonical_json()))
        generator.assert_not_called()
        self.assertTrue(request.eligible_for_generation, request.blocking_findings)
        self.assertEqual(before, request.approved_backend.canonical_json())
        self.assertIn("title:str:default='Untitled: record'", request.module_requests[0].field_declarations)
        definition = module_definition(request.module_requests[0])
        self.assertIn("default='Untitled: record'", next(f["create"] for f in schema_fields(definition) if f["name"] == "title"))

    def test_lifecycle_binding_and_no_invented_fields(self):
        request = eligible_request()
        approved = request.approved_backend
        entity = approved.package.original_backend.resolved_model.entities[0]
        module, _ = _translate_entity(approved, replace(entity, lifecycle_domain_ids=("unbound",)), True)
        self.assertIsNone(module)
        module, _ = _translate_entity(approved, entity, True)
        self.assertEqual(set(module.source_field_ids), {f.field_id for f in entity.approved_fields})
        self.assertEqual(module.field_declarations, tuple(sorted(module.field_declarations)))

    def test_bound_lifecycle_domain_translates_without_dropping_provenance(self):
        approved = eligible_request().approved_backend
        spec = approved.package.original_backend
        entity = spec.resolved_model.entities[0]
        title = next(f for f in entity.approved_fields if f.name == "title")
        from arcadev.domain_model_specification import ModelValueDomain
        domain = ModelValueDomain("domain", "Lifecycle", ("draft", "published"), title.evidence)
        title = replace(title, logical_type=LogicalType.ENUM, value_domain_id="domain")
        entity = replace(entity, approved_fields=tuple(title if f.field_id == title.field_id else f for f in entity.approved_fields), lifecycle_domain_ids=("domain",))
        model = replace(spec.resolved_model, entities=(entity,), value_domains=(domain,))
        # Unit-test the internal translator with explicit records; the public
        # request boundary still rejects any unapproved/forged frozen chain.
        candidate = replace(approved, package=replace(approved.package, original_backend=replace(spec, resolved_model=model)))
        module, reason = _translate_entity(candidate, entity, True)
        self.assertIsNotNone(module, reason)
        self.assertIn("title:choice(draft,published)", module.field_declarations)
        self.assertTrue(set(domain.evidence.source_requirements) <= set(module.source_decision_ids))
        with self.assertRaises(ValueError):
            ArcaCoreGenerationRequest.create(candidate)

    def test_actual_gaming_studio_delta(self):
        request = gaming_request()
        self.assertEqual((len(request.blocking_findings), len(request.unsupported_mappings), len(request.required_certification_mappings)), (57, 6, 51))
        self.assertEqual(request.module_requests, ())
        self.assertEqual(len(request.approved_backend.package.original_backend.resolved_model.entities), 5)
        self.assertTrue(all(not e.approved_fields for e in request.approved_backend.package.original_backend.resolved_model.entities))


if __name__ == "__main__":
    unittest.main()
