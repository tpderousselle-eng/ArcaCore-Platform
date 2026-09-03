"""Smoke-test generated HTTP(S) URL schemas and quoted DSL defaults in memory."""

import ast
import builtins
from contextlib import ExitStack
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import AnyHttpUrl, ValidationError
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


class UrlSmokeTest(unittest.TestCase):
    def test_absolute_urls_normalize_to_plain_strings_without_network(self):
        ns, _, _ = schemas(["website:str:format=url"])
        cases = {
            "HTTPS://EXAMPLE.COM": "https://example.com/",
            "http://EXAMPLE.COM:80": "http://example.com/",
            "https://example.com:443/a/../b?q=One%20Two#Part": "https://example.com/b?q=One%20Two#Part",
            "https://bücher.de/über": "https://xn--bcher-kva.de/%C3%BCber",
            "http://localhost:8000/path": "http://localhost:8000/path",
            "http://127.0.0.1:8000/": "http://127.0.0.1:8000/",
            "http://[::1]:8080/a": "http://[::1]:8080/a",
            "https://example.com/?contact=a@example.com&next=https%3A%2F%2Fexample.org": "https://example.com/?contact=a@example.com&next=https%3A%2F%2Fexample.org",
            "https://example.com/" + "a" * 2200: "https://example.com/" + "a" * 2200,
        }
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS lookup")), patch(
            "socket.socket", side_effect=AssertionError("Network request")
        ):
            for suffix in ("Create", "Update", "Response"):
                cls = ns["Record" + suffix]
                extra = {"id": 1} if suffix == "Response" else {}
                for raw, normalized in cases.items():
                    with self.subTest(schema=suffix, raw=raw):
                        result = cls(website=raw, **extra)
                        self.assertIs(type(result.website), str)
                        self.assertEqual(result.website, normalized)
                        self.assertEqual(result.model_dump()["website"], normalized)
                        self.assertEqual(json.loads(result.model_dump_json())["website"], normalized)
                        self.assertEqual(cls.model_validate_json(result.model_dump_json()).website, normalized)

    def test_invalid_urls_schemes_credentials_and_lossy_inputs(self):
        ns, _, _ = schemas(["website:str:format=url"])
        invalid = (
            "", " ", "example.com", "/relative", "//example.com", "https:example.com",
            "https:/example.com", "https:///example.com", "https://", "https://?x=1",
            "https://#part", "ftp://example.com", "file:///etc/hosts", "mailto:a@example.com",
            "javascript:alert(1)", "data:text/plain,hello", "ws://example.com",
            "https://user@example.com", "https://user:password@example.com", "https://@example.com",
            " https://example.com", "https://example.com ", "https://example.com/a b",
            "https://example.com\n", "https://exa\tmple.com", "https://example.com/\x00",
            "https://example.com/\x7f", "https://example.com/\xa0", "https://example.com\\other",
            "https://example.com/%", "https://example.com/%2", "https://example.com/%GG",
            "https://example.com:99999", "https://example.com:abc", "https://[::1", "https://[bad]/",
            123, True, b"https://example.com", bytearray(b"https://example.com"), [], {}, None,
            AnyHttpUrl("https://example.com"),
        )
        for suffix in ("Create", "Update", "Response"):
            for raw in invalid:
                with self.subTest(schema=suffix, raw=raw), self.assertRaises(ValidationError):
                    ns["Record" + suffix](website=raw, **({"id": 1} if suffix == "Response" else {}))

    def test_required_nullable_updates_and_attribute_responses(self):
        ns, _, _ = schemas(["website:str:format=url", "backup:text:nullable:format=url"])
        create, update, response = (ns["Record" + suffix] for suffix in ("Create", "Update", "Response"))
        with self.assertRaises(ValidationError):
            create()
        self.assertIsNone(create(website="https://example.com").backup)
        self.assertEqual(update().model_dump(exclude_unset=True), {})
        self.assertEqual(update(backup=None).model_dump(exclude_unset=True), {"backup": None})
        self.assertEqual(update(website="HTTPS://EXAMPLE.COM").model_dump(exclude_unset=True), {"website": "https://example.com/"})
        with self.assertRaises(ValidationError):
            update(website=None)
        with self.assertRaises(ValidationError):
            update(backup="bad")
        with self.assertRaises(ValidationError):
            response(id=1, website="https://example.com")
        result = response.model_validate(SimpleNamespace(id=1, website="HTTPS://EXAMPLE.COM", backup=None))
        self.assertEqual(result.website, "https://example.com/")
        with self.assertRaises(ValidationError):
            response.model_validate(SimpleNamespace(id=1, website="/relative", backup=None))

    def test_url_literal_defaults_validate_and_expressions_do_not_execute(self):
        ns, sources, registry = schemas(["website:str:format=url:default='HTTPS://EXAMPLE.COM:443/a:regex=b':length=100"], use_cli=True)
        self.assertEqual(ns["RecordCreate"]().website, "https://example.com/a:regex=b")
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertEqual(registry["Record"]["fields"][0]["default"], "'HTTPS://EXAMPLE.COM:443/a:regex=b'")
        self.assertIn("HTTPS://EXAMPLE.COM:443/a:regex=b", sources["model.j2"])
        for default in ("'bad'", "'ftp://example.com'", "'https://user:pass@example.com'", "123", "None"):
            with self.subTest(default=default):
                ns, _, _ = schemas([f"website:str:format=url:default={default}"])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"]()
        ns, _, _ = schemas(["website:text:format=url:nullable:default=None"])
        self.assertIsNone(ns["RecordCreate"]().website)
        ns, _, _ = schemas(["website:str:format=url:default=raise_if_executed()"])
        self.assertEqual(ns["RecordCreate"]().model_dump(exclude_unset=True), {})
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](website="invalid")

    def test_quoted_defaults_escaping_colons_and_regex_boundaries(self):
        definitions = [
            'website:str:default="https://example.com:8443/a:b":format=url',
            r"website:str:format=url:default='https://example.com/it\'s:here'",
            r'website:str:format=url:default="https://example.com/a\"b:c"',
        ]
        expected = ["https://example.com:8443/a:b", "https://example.com/it's:here", "https://example.com/a%22b:c"]
        for definition, value in zip(definitions, expected):
            with self.subTest(definition=definition):
                ns, _, _ = schemas([definition])
                self.assertEqual(ns["RecordCreate"]().website, value)
        ns, _, _ = schemas([r"website:str:default='https://example.com/a:regex=b':format=url:regex=^https://example\.com/a:regex=b$"])
        self.assertEqual(ns["RecordCreate"]().website, "https://example.com/a:regex=b")
        ns, _, _ = schemas([r"text:str:default='a\'b:regex=c':regex=^a'b:regex=c$"])
        self.assertEqual(ns["RecordCreate"]().text, "a'b:regex=c")
        for literal in (r"'a\\:b'", '"a:b"', "''"):
            field = parse_fields("Record", [f"text:str:default={literal}:nullable"])[0]
            self.assertEqual(ast.literal_eval(field.default), ast.literal_eval(literal))
            self.assertTrue(field.nullable)
        fields = parse_fields("Record", ["text:str:default='plain'", "age:int:default=18", "text2:str:regex=^a:b'c$"])
        self.assertEqual([field.default for field in fields], ["'plain'", "18", None])
        self.assertEqual(fields[2].pattern, "^a:b'c$")

    def test_malformed_quoted_defaults_fail_before_writing(self):
        invalid = (
            "website:str:format=url:default='https://example.com",
            'website:str:format=url:default="https://example.com',
            "website:str:format=url:default='https://example.com'garbage",
            "website:str:format=url:default='https://example.com'+raise_if_executed()",
            "website:str:format=url:default=https://example.com",
            "website:str:format=url:default='https://example.com':bogus",
        )
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                self.assert_preflight_rejection(declaration)

    def test_length_regex_and_modifier_order_use_normalized_strings(self):
        ns, _, _ = schemas([r"website:str:format=url:min_length=21:length=21:regex=^https://example\.com/a$"])
        for suffix in ("Create", "Update", "Response"):
            cls = ns["Record" + suffix]
            extra = {"id": 1} if suffix == "Response" else {}
            self.assertEqual(cls(website="HTTPS://EXAMPLE.COM:443/a", **extra).website, "https://example.com/a")
            for raw in ("https://example.com", "https://example.com/ab", "https://example.org/a"):
                with self.subTest(raw=raw, schema=suffix), self.assertRaises(ValidationError):
                    cls(website=raw, **extra)
        ns, _, _ = schemas(["website:str:format=url:length=18"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](website="https://example.com")
        ns, _, _ = schemas(["website:str:format=url:length=25"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](website="https://bücher.de/über")
        first = parse_fields("Record", ["website:str:format=url:nullable:length=200"])
        second = parse_fields("Record", ["website:str:length=200:nullable:format=url"])
        self.assertEqual(first, second)

    def test_cli_registry_json_schema_and_format_coexistence(self):
        ns, sources, registry = schemas([
            "website:str:format=url:length=200", "backup:text:nullable:format=url",
            "slug:str:format=slug", "email:str:format=email", "phone:str:format=phone",
            "name:str", "amount:int:min=0", "twice:int:computed=amount * 2",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertEqual([field.get("format") for field in metadata[:6]], ["url", "url", "slug", "email", "phone", None])
        self.assertEqual(metadata[0]["sqlalchemy_type"], "String")
        self.assertEqual(metadata[1]["sqlalchemy_type"], "Text")
        self.assertEqual(sources["schema.j2"].count("def _arca_normalize_url"), 1)
        for suffix in ("Create", "Update", "Response"):
            properties = ns["Record" + suffix].model_json_schema()["properties"]
            self.assertEqual(properties["website"]["type"], "string")
            self.assertEqual(properties["website"]["format"], "uri")
            self.assertEqual(properties["website"]["maxLength"], 200)
            self.assertIn({"type": "string", "format": "uri"}, properties["backup"]["anyOf"])
            self.assertEqual(properties["slug"]["format"], "slug")
            self.assertEqual(properties["email"]["format"], "email")
            self.assertEqual(properties["phone"]["format"], "phone")
        payload = {"website": "HTTPS://EXAMPLE.COM", "slug": "my-article", "email": "Ty@EXAMPLE.COM", "phone": "+1 650-253-0000", "name": "Ty", "amount": 2}
        value = ns["RecordCreate"](**payload)
        self.assertEqual(value.website, "https://example.com/")
        self.assertEqual(value.slug, "my-article")
        self.assertEqual(value.email, "Ty@example.com")
        self.assertEqual(value.phone, "+16502530000")
        self.assertNotIn("twice", value.model_dump())
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](**payload, twice=4)
        self.assertTrue(ns["RecordResponse"].model_json_schema()["properties"]["twice"]["readOnly"])

    def assert_preflight_rejection(self, declaration):
        with ExitStack() as stack:
            generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
            register = stack.enter_context(patch.object(Registry, "register"))
            with self.assertRaises(ValueError):
                pipeline.generate_module("Record", [declaration])
            for generator in generators:
                generator.assert_not_called()
            register.assert_not_called()

    def test_invalid_dsl_fails_before_any_generation(self):
        invalid = [
            "website:str:format=", "website:str:format=URL", "website:str:format= url",
            "website:str:format=url:format=url", "website:str:format=url:format=email",
            "website:str:format=phone:format=url", "website:str:format=url(https)",
            "website:str:format=url:scheme=https", "website:str:url", "website:url", "website:array(url)",
            "website:str:format=url:min=1", "website:str:format=url:length=0",
            "website:str:format=url:regex=[", "website:str:format=url:computed=1",
        ] + [f"website:{kind}:format=url" for kind in (
            "int", "float", "bool", "uuid", "date", "datetime", "decimal(8,2)",
            "json()", "array(str)", "choice(A,B)", "enum(A,B)", "many_to_many(Role)",
        )]
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                self.assert_preflight_rejection(declaration)

    def test_programmatic_metadata_and_direct_schema_generation(self):
        for field in (
            Field("website", "int", "Integer", format="url"),
            Field("website", "str", "ARRAY", format="url"),
            Field("website", "str", "String", format="uri"),
            Field("website", "str", "String", format="url", relationship_type="many_to_many"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    FieldValidator.validate([field])
                module = ModuleDefinition("Record", "Record", "record", "records", [field])
                with patch("tools.generate_schema.render_template") as render:
                    with self.assertRaises(ValueError):
                        generate_schema(module)
                    render.assert_not_called()
        field = Field("website", "text", "Text", format="url", default="'https://EXAMPLE.COM:443'")
        FieldValidator.validate([field])
        module = ModuleDefinition("Record", "Record", "record", "records", [field])
        captured = {}

        def capture(template_name, output_path, **context):
            captured["source"] = env.get_template(template_name).render(**context)

        with patch("tools.generate_schema.render_template", side_effect=capture):
            generate_schema(module)
        ns = {"__name__": "generated_direct_url"}
        exec(compile(captured["source"], "<direct-url-schema>", "exec"), ns)
        self.assertEqual(ns["RecordCreate"]().website, "https://example.com/")
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](website="example.com")

    def test_database_round_trip_normalized_uniqueness_and_update(self):
        definitions = ["website:str:format=url:unique:length=200", "backup:text:nullable:format=url"]
        ns, _, _ = schemas(definitions)
        base, models, _, _ = generate_models({"Record": definitions})
        model = models["Record"]
        engine = database(base)
        try:
            self.assertIsInstance(model.website.type, String)
            self.assertEqual(model.website.type.length, 200)
            self.assertIsInstance(model.backup.type, Text)
            with Session(engine) as session:
                row = model(**ns["RecordCreate"](website="HTTPS://EXAMPLE.COM:443").model_dump(exclude_unset=True))
                session.add(row)
                session.commit()
                self.assertEqual(ns["RecordResponse"].model_validate(row).website, "https://example.com/")
                session.add(model(**ns["RecordCreate"](website="https://example.com/").model_dump(exclude_unset=True)))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                update = ns["RecordUpdate"](website="https://example.org/page")
                for key, value in update.model_dump(exclude_unset=True).items():
                    setattr(row, key, value)
                session.commit()
                session.expire_all()
                self.assertEqual(row.website, "https://example.org/page")
                self.assertEqual(session.query(model).count(), 1)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_url_primary_and_foreign_keys_with_relationships(self):
        base, models, sources, registry = generate_models({
            "Site": ["address:str:pk:format=url"],
            "Page": ["site_id:str:format=url:fk=sites.address:one_to_many(Site,pages):cascade_delete:passive_deletes"],
        })
        engine = database(base)
        try:
            namespaces = {}
            for name in ("Site", "Page"):
                ns = {"__name__": f"generated_url_{name}"}
                exec(compile(sources[name]["schema.j2"], "<url-key-schema>", "exec"), ns)
                namespaces[name] = ns
            self.assertNotIn("id", namespaces["Site"]["SiteResponse"].model_fields)
            with self.assertRaises(ValidationError):
                namespaces["Site"]["SiteCreate"]()
            with Session(engine) as session:
                site = models["Site"](**namespaces["Site"]["SiteCreate"](address="HTTPS://EXAMPLE.COM").model_dump())
                session.add(site)
                session.flush()
                page = models["Page"](**namespaces["Page"]["PageCreate"](site_id="https://example.com:443/").model_dump())
                session.add(page)
                session.commit()
                self.assertEqual(site.pages, [page])
                self.assertEqual(page.site.address, "https://example.com/")
                self.assertEqual(registry["Page"]["fields"][0]["format"], "url")
                session.delete(site)
                session.commit()
                self.assertEqual(session.query(models["Page"]).count(), 0)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_existing_outputs_indexes_constraints_and_field_names(self):
        definitions = ["website:str:length=200", "amount:int", "twice:int:computed=amount * 2",
                       "soft_delete", "partial_index(website,where=deleted_at is None,unique=True)",
                       "expression_index(lower(website))", "check(amount >= 0)"]
        before, before_registry = run_generation(definitions)
        after, after_registry = run_generation(["website:str:length=200:format=url", *definitions[1:]])
        for kind in ("model", "crud", "service", "router"):
            self.assertEqual(before[f"{kind}.j2"], after[f"{kind}.j2"])
        self.assertEqual(after_registry["Record"]["fields"][0].pop("format"), "url")
        self.assertEqual(before_registry, after_registry)
        self.assertNotIn("_arca_UrlString", before["schema.j2"])
        self.assertNotIn("from tools", after["schema.j2"])
        ns, _, _ = schemas(["url:str", "AnyHttpUrl:str:format=url", "format:text:format=url", "re:str:format=url"])
        value = ns["RecordCreate"](url="plain", AnyHttpUrl="HTTPS://EXAMPLE.COM", format="https://example.org", re="http://localhost")
        self.assertEqual(value.url, "plain")
        self.assertEqual(value.AnyHttpUrl, "https://example.com/")
        ns, _, _ = schemas([r"website:str:regex=^format=url:literal$"])
        self.assertEqual(ns["RecordCreate"](website="format=url:literal").website, "format=url:literal")

    def test_generated_url_schemas_need_no_optional_package_or_generator(self):
        original_import = builtins.__import__

        def without_optional_dependencies(name, *args, **kwargs):
            if name.split(".")[0] in {"email_validator", "phonenumbers", "pydantic_extra_types", "tools"}:
                raise ImportError("Optional dependency or generator import blocked")
            return original_import(name, *args, **kwargs)

        sources, _ = run_generation(["website:str:format=url"])
        ns = {"__name__": "standalone_url_schema"}
        with patch("builtins.__import__", side_effect=without_optional_dependencies):
            exec(compile(sources["schema.j2"], "<standalone-url-schema>", "exec"), ns)
            self.assertEqual(ns["RecordCreate"](website="https://EXAMPLE.COM").website, "https://example.com/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
