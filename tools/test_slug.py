"""Exercise generated slug schemas and database composition entirely in memory."""

import builtins
from contextlib import ExitStack
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.core.engine import env
from tools.core.field_parser import Field, parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.generate_schema import generate_schema
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, pipeline, run_generation
from tools.test_one_to_many import database, generate_models
from tools.test_validators import schemas
from tools.validators.field_validator import FieldValidator


class SlugSmokeTest(unittest.TestCase):
    def test_valid_slugs_preserve_values_in_all_schemas_and_json(self):
        ns, _, _ = schemas(["slug:str:format=slug"])
        for suffix in ("Create", "Update", "Response"):
            cls = ns["Record" + suffix]
            extra = {"id": 1} if suffix == "Response" else {}
            for raw in ("a", "0", "123", "product", "my-product-2", "a-0-b", "0-start", "a" * 300):
                with self.subTest(schema=suffix, value=raw):
                    value = cls(slug=raw, **extra)
                    self.assertIsInstance(value.slug, str)
                    self.assertEqual(value.slug, raw)
                    self.assertEqual(json.loads(value.model_dump_json())["slug"], raw)
                    self.assertEqual(cls.model_validate_json(value.model_dump_json()).slug, raw)

    def test_invalid_strings_and_coercible_inputs_are_rejected(self):
        ns, _, _ = schemas(["slug:str:format=slug"])
        invalid = (
            "", " ", "My-product", "PRODUCT", "-product", "product-", "my--product",
            "my_product", "my product", " product", "product ", "a.b", "a/b", "../a",
            "a?b", "a#b", "a%b", "a+b", "a:b", "café", "caf\u0065\u0301", "日本語",
            "a–b", "a—b", "аbc", "ａｂｃ", "１２３", "١٢٣", "a\u200bb", "a\xa0b",
            "a\nb", "a\n", "\na", "a\r\n", "a\tb", "a\x00b", "a" * 2000 + "!",
            123, 1.5, True, b"valid-slug", bytearray(b"valid-slug"), [], {}, None,
        )
        for suffix in ("Create", "Update", "Response"):
            for raw in invalid:
                with self.subTest(schema=suffix, value=raw), self.assertRaises(ValidationError):
                    ns["Record" + suffix](slug=raw, **({"id": 1} if suffix == "Response" else {}))

    def test_required_nullable_partial_updates_and_attribute_responses(self):
        ns, _, _ = schemas(["slug:str:format=slug", "backup:text:nullable:format=slug"])
        create, update, response = (ns["Record" + suffix] for suffix in ("Create", "Update", "Response"))
        with self.assertRaises(ValidationError):
            create()
        self.assertIsNone(create(slug="article").backup)
        self.assertEqual(update().model_dump(exclude_unset=True), {})
        self.assertEqual(update(backup=None).model_dump(exclude_unset=True), {"backup": None})
        self.assertEqual(update(slug="article-2").model_dump(exclude_unset=True), {"slug": "article-2"})
        with self.assertRaises(ValidationError):
            update(slug=None)
        with self.assertRaises(ValidationError):
            update(backup="Bad Slug")
        with self.assertRaises(ValidationError):
            response(id=1, slug="article")
        self.assertEqual(response.model_validate(SimpleNamespace(id=1, slug="article", backup=None)).slug, "article")
        with self.assertRaises(ValidationError):
            response.model_validate(SimpleNamespace(id=1, slug="Article", backup=None))

    def test_literal_defaults_and_nonexecuted_database_expressions(self):
        ns, _, _ = schemas(["slug:str:format=slug:default='first-article'"])
        self.assertEqual(ns["RecordCreate"]().slug, "first-article")
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        for default in ("'First Article'", "''", "'article-'", "123", "None"):
            with self.subTest(default=default):
                ns, _, _ = schemas([f"slug:str:format=slug:default={default}"])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"]()
        ns, _, _ = schemas(["slug:text:format=slug:nullable:default=None"])
        self.assertIsNone(ns["RecordCreate"]().slug)
        ns, _, _ = schemas(["slug:str:format=slug:default=list"])
        self.assertEqual(ns["RecordCreate"]().model_dump(exclude_unset=True), {})
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](slug="Bad")

    def test_length_regex_and_modifier_order_preserve_slug_rules(self):
        ns, _, _ = schemas([r"slug:str:format=slug:min_length=4:length=8:regex=^pro-"])
        for suffix in ("Create", "Update", "Response"):
            cls = ns["Record" + suffix]
            extra = {"id": 1} if suffix == "Response" else {}
            self.assertEqual(cls(slug="pro-a", **extra).slug, "pro-a")
            self.assertEqual(cls(slug="pro-abcd", **extra).slug, "pro-abcd")
            for raw in ("pro", "pro-", "pro--a", "pro-Ab", "pro-abcde", "alt-a"):
                with self.subTest(schema=suffix, value=raw), self.assertRaises(ValidationError):
                    cls(slug=raw, **extra)
        ns, _, _ = schemas(["slug:str:format=slug:regex=.*"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](slug="Bad Slug")
        ns, _, _ = schemas(["slug:str:format=slug:min_length=0"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](slug="")
        first = parse_fields("Record", ["slug:str:format=slug:nullable:length=80"])
        second = parse_fields("Record", ["slug:str:length=80:nullable:format=slug"])
        self.assertEqual(first, second)

    def test_cli_registry_json_schema_and_format_coexistence(self):
        ns, sources, registry = schemas([
            "slug:str:format=slug:min_length=2:length=80", "backup:text:nullable:format=slug",
            "email:str:format=email", "phone:str:format=phone", "name:str",
            "amount:int:min=0", "twice:int:computed=amount * 2",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertEqual([field.get("format") for field in metadata[:5]], ["slug", "slug", "email", "phone", None])
        self.assertEqual(metadata[0]["sqlalchemy_type"], "String")
        self.assertEqual(metadata[1]["sqlalchemy_type"], "Text")
        self.assertEqual(sources["schema.j2"].count("def _arca_validate_slug"), 1)
        for suffix in ("Create", "Update", "Response"):
            properties = ns["Record" + suffix].model_json_schema()["properties"]
            self.assertEqual(properties["slug"]["type"], "string")
            self.assertEqual(properties["slug"]["format"], "slug")
            self.assertEqual(properties["slug"]["minLength"], 2)
            self.assertEqual(properties["slug"]["maxLength"], 80)
            self.assertIn({"type": "string", "format": "slug"}, properties["backup"]["anyOf"])
            self.assertEqual(properties["email"]["format"], "email")
            self.assertEqual(properties["phone"]["format"], "phone")
        payload = {"slug": "my-article", "email": "Ty@EXAMPLE.COM", "phone": "+1 650-253-0000", "name": "Ty", "amount": 2}
        value = ns["RecordCreate"](**payload)
        self.assertEqual(value.slug, "my-article")
        self.assertEqual(value.email, "Ty@example.com")
        self.assertEqual(value.phone, "+16502530000")
        self.assertNotIn("twice", value.model_dump())
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](**payload, twice=4)
        self.assertTrue(ns["RecordResponse"].model_json_schema()["properties"]["twice"]["readOnly"])

    def test_invalid_dsl_fails_before_any_generation(self):
        invalid = [
            "slug:str:format=", "slug:str:format=Slug", "slug:str:format= slug",
            "slug:str:format=slug:format=slug", "slug:str:format=slug:format=email",
            "slug:str:format=phone:format=slug", "slug:str:format=slug(unicode)",
            "slug:str:format=slug:lowercase", "slug:str:slug", "slug:slug", "slug:array(slug)",
            "slug:str:format=slug:min=1", "slug:str:format=slug:length=0",
            "slug:str:format=slug:regex=[", "slug:str:format=slug:computed=1",
        ] + [f"slug:{kind}:format=slug" for kind in (
            "int", "float", "bool", "uuid", "date", "datetime", "decimal(8,2)",
            "json()", "array(str)", "choice(A,B)", "enum(A,B)", "many_to_many(Role)",
        )]
        for declaration in invalid:
            with self.subTest(declaration=declaration), ExitStack() as stack:
                generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
                register = stack.enter_context(patch.object(Registry, "register"))
                with self.assertRaises(ValueError):
                    pipeline.generate_module("Record", [declaration])
                for generator in generators:
                    generator.assert_not_called()
                register.assert_not_called()

    def test_programmatic_metadata_and_direct_schema_generation(self):
        for field in (
            Field("slug", "int", "Integer", format="slug"),
            Field("slug", "str", "ARRAY", format="slug"),
            Field("slug", "str", "String", format="unknown"),
            Field("slug", "str", "String", format="slug", relationship_type="many_to_many"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    FieldValidator.validate([field])
                module = ModuleDefinition("Record", "Record", "record", "records", [field])
                with patch("tools.generate_schema.render_template") as render:
                    with self.assertRaises(ValueError):
                        generate_schema(module)
                    render.assert_not_called()
        field = Field("slug", "text", "Text", format="slug")
        FieldValidator.validate([field])
        module = ModuleDefinition("Record", "Record", "record", "records", [field])
        captured = {}

        def capture(template_name, output_path, **context):
            captured["source"] = env.get_template(template_name).render(**context)

        with patch("tools.generate_schema.render_template", side_effect=capture):
            generate_schema(module)
        ns = {"__name__": "generated_direct_slug"}
        exec(compile(captured["source"], "<direct-slug-schema>", "exec"), ns)
        self.assertEqual(ns["RecordCreate"](slug="direct-slug").slug, "direct-slug")
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](slug="Direct Slug")

    def test_database_round_trip_uniqueness_and_update(self):
        definitions = ["slug:str:format=slug:unique:length=80", "backup:text:nullable:format=slug"]
        ns, _, _ = schemas(definitions)
        base, models, _, _ = generate_models({"Record": definitions})
        model = models["Record"]
        engine = database(base)
        try:
            self.assertIsInstance(model.slug.type, String)
            self.assertEqual(model.slug.type.length, 80)
            self.assertIsInstance(model.backup.type, Text)
            with Session(engine) as session:
                row = model(**ns["RecordCreate"](slug="first-post").model_dump(exclude_unset=True))
                session.add(row)
                session.commit()
                self.assertEqual(ns["RecordResponse"].model_validate(row).slug, "first-post")
                session.add(model(**ns["RecordCreate"](slug="first-post").model_dump(exclude_unset=True)))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                update = ns["RecordUpdate"](slug="second-post")
                for key, value in update.model_dump(exclude_unset=True).items():
                    setattr(row, key, value)
                session.commit()
                session.expire_all()
                self.assertEqual(row.slug, "second-post")
                self.assertEqual(session.query(model).count(), 1)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_slug_primary_and_foreign_keys_with_relationships(self):
        base, models, sources, registry = generate_models({
            "Category": ["slug:str:pk:format=slug"],
            "Post": ["category_id:str:format=slug:fk=categorys.slug:one_to_many(Category,posts):cascade_delete:passive_deletes"],
        })
        engine = database(base)
        try:
            namespaces = {}
            for name in ("Category", "Post"):
                ns = {"__name__": f"generated_slug_{name}"}
                exec(compile(sources[name]["schema.j2"], "<slug-key-schema>", "exec"), ns)
                namespaces[name] = ns
            self.assertNotIn("id", namespaces["Category"]["CategoryResponse"].model_fields)
            with self.assertRaises(ValidationError):
                namespaces["Category"]["CategoryCreate"]()
            with Session(engine) as session:
                category = models["Category"](**namespaces["Category"]["CategoryCreate"](slug="software-tools").model_dump())
                session.add(category)
                session.flush()
                post = models["Post"](**namespaces["Post"]["PostCreate"](category_id="software-tools").model_dump())
                session.add(post)
                session.commit()
                self.assertEqual(category.posts, [post])
                self.assertEqual(post.category.slug, "software-tools")
                self.assertEqual(registry["Post"]["fields"][0]["format"], "slug")
                session.delete(category)
                session.commit()
                self.assertEqual(session.query(models["Post"]).count(), 0)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_existing_outputs_indexes_constraints_and_field_names(self):
        definitions = ["slug:str:length=80", "amount:int", "twice:int:computed=amount * 2",
                       "soft_delete", "partial_index(slug,where=deleted_at is None,unique=True)",
                       "expression_index(lower(slug))", "check(amount >= 0)"]
        before, before_registry = run_generation(definitions)
        after, after_registry = run_generation(["slug:str:length=80:format=slug", *definitions[1:]])
        for kind in ("model", "crud", "service", "router"):
            self.assertEqual(before[f"{kind}.j2"], after[f"{kind}.j2"])
        self.assertEqual(after_registry["Record"]["fields"][0].pop("format"), "slug")
        self.assertEqual(before_registry, after_registry)
        self.assertNotIn("_arca_SlugString", before["schema.j2"])
        self.assertNotIn("from tools", after["schema.j2"])
        ns, _, _ = schemas(["slug:str", "SlugString:str:format=slug", "format:text:format=slug", "re:str:format=slug"])
        value = ns["RecordCreate"](slug="Plain Slug", SlugString="my-slug", format="other-slug", re="re")
        self.assertEqual(value.slug, "Plain Slug")
        self.assertEqual(value.SlugString, "my-slug")
        ns, _, _ = schemas([r"slug:str:regex=^format=slug:literal$"])
        self.assertEqual(ns["RecordCreate"](slug="format=slug:literal").slug, "format=slug:literal")

    def test_slug_schemas_have_no_optional_dependency_or_network_requirement(self):
        original_import = builtins.__import__

        def without_optional_dependencies(name, *args, **kwargs):
            if name.split(".")[0] in {"email_validator", "phonenumbers", "slugify", "pydantic_extra_types", "tools"}:
                raise ImportError("Optional dependency or generator import blocked")
            return original_import(name, *args, **kwargs)

        sources, _ = run_generation(["slug:str:format=slug"])
        ns = {"__name__": "standalone_slug_schema"}
        with patch("builtins.__import__", side_effect=without_optional_dependencies), patch(
            "socket.socket", side_effect=AssertionError("Network request")
        ):
            exec(compile(sources["schema.j2"], "<standalone-slug-schema>", "exec"), ns)
            self.assertEqual(ns["RecordCreate"](slug="standalone-slug").slug, "standalone-slug")


if __name__ == "__main__":
    unittest.main(verbosity=2)
