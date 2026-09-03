"""Exercise generated email schemas and models entirely in memory."""

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

from tools.core.field_parser import Field, parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.generate_schema import generate_schema
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, load_model, pipeline, run_generation
from tools.test_one_to_many import database, generate_models
from tools.test_validators import schemas
from tools.validators.field_validator import FieldValidator


class EmailSmokeTest(unittest.TestCase):
    def test_valid_addresses_normalize_without_network(self):
        ns, _, _ = schemas(["email:str:format=email"])
        cases = {
            "Person+tag@EXAMPLE.COM": "Person+tag@example.com",
            " Person@example.com ": "Person@example.com",
            "Tyler <Person@example.com>": "Person@example.com",
            "o'reilly@example.com": "o'reilly@example.com",
            "u\u0308ser@xn--bcher-kva.de": "üser@bücher.de",
        }
        with patch("socket.getaddrinfo", side_effect=AssertionError("Network lookup")), patch(
            "dns.resolver.Resolver.resolve", side_effect=AssertionError("DNS lookup")
        ):
            for raw, normalized in cases.items():
                with self.subTest(raw=raw):
                    result = ns["RecordCreate"](email=raw)
                    self.assertIsInstance(result.email, str)
                    self.assertEqual(result.email, normalized)
                    self.assertEqual(json.loads(result.model_dump_json()), {"email": normalized})

    def test_invalid_addresses_rejected_in_all_schemas(self):
        ns, _, _ = schemas(["email:str:format=email"])
        invalid = (
            "", " ", "person", "@example.com", "person@", "a@@example.com",
            "a b@example.com", "a..b@example.com", "a@localhost", "a@[127.0.0.1]",
            "a@example..com", "a@example.com\r\nBcc: other@example.com",
            "a\x00b@example.com", "a" * 3000 + "@example.com", 123, True, [], {}, None,
        )
        for name in ("RecordCreate", "RecordUpdate", "RecordResponse"):
            for value in invalid:
                with self.subTest(schema=name, value=value), self.assertRaises(ValidationError):
                    ns[name](email=value, **({"id": 1} if name == "RecordResponse" else {}))

    def test_required_nullable_and_partial_updates(self):
        ns, _, _ = schemas(["email:str:format=email", "backup:text:nullable:format=email"])
        create, update, response = (ns["Record" + suffix] for suffix in ("Create", "Update", "Response"))
        with self.assertRaises(ValidationError):
            create()
        self.assertIsNone(create(email="a@example.com").backup)
        self.assertEqual(update().model_dump(exclude_unset=True), {})
        self.assertEqual(update(backup=None).model_dump(exclude_unset=True), {"backup": None})
        self.assertEqual(update(email="A@EXAMPLE.COM").model_dump(exclude_unset=True), {"email": "A@example.com"})
        with self.assertRaises(ValidationError):
            update(email=None)
        with self.assertRaises(ValidationError):
            update(backup="bad")
        with self.assertRaises(ValidationError):
            response(id=1, email="a@example.com")
        result = response.model_validate(SimpleNamespace(id=1, email="A@EXAMPLE.COM", backup=None))
        self.assertEqual(result.email, "A@example.com")
        self.assertIsNone(result.backup)

    def test_literal_defaults_validate_and_expression_defaults_do_not_execute(self):
        ns, _, _ = schemas(["email:str:format=email:default='Person@EXAMPLE.COM'"])
        self.assertEqual(ns["RecordCreate"]().email, "Person@example.com")
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        for default in ("'bad'", "123", "None"):
            with self.subTest(default=default):
                ns, _, _ = schemas([f"email:str:format=email:default={default}"])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"]()
        ns, _, _ = schemas(["email:str:format=email:nullable:default=None"])
        self.assertIsNone(ns["RecordCreate"]().email)
        ns, _, _ = schemas(["email:str:format=email:default=raise_if_executed()"])
        self.assertEqual(ns["RecordCreate"]().model_dump(exclude_unset=True), {})
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](email="invalid")

    def test_length_and_regex_apply_after_normalization(self):
        ns, _, _ = schemas([r"email:str:format=email:min_length=13:length=20:regex=@example\.com$"])
        create = ns["RecordCreate"]
        self.assertEqual(create(email="Long Display Name <a@EXAMPLE.COM>").email, "a@example.com")
        for value in ("a@b.co", "abcdefghi@example.com", "a@example.net"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                create(email=value)
        first = parse_fields("Record", ["email:str:format=email:nullable:length=30"])
        second = parse_fields("Record", ["email:str:length=30:nullable:format=email"])
        self.assertEqual(first, second)
        plain, _, _ = schemas([r"code:str:regex=^format=email:ok$"])
        self.assertEqual(plain["RecordCreate"](code="format=email:ok").code, "format=email:ok")

    def test_cli_registry_and_json_schema(self):
        ns, _, registry = schemas([
            "email:str:format=email:length=254:min_length=6", "backup:text:format=email:nullable",
            "name:str", "amount:int:min=0", "twice:int:computed=amount * 2",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertEqual(metadata[0]["format"], "email")
        self.assertEqual(metadata[0]["sqlalchemy_type"], "String")
        self.assertEqual(metadata[1]["format"], "email")
        self.assertNotIn("format", metadata[2])
        for suffix in ("Create", "Update", "Response"):
            properties = ns["Record" + suffix].model_json_schema()["properties"]
            self.assertEqual(properties["email"]["format"], "email")
            self.assertEqual(properties["email"]["type"], "string")
            self.assertEqual(properties["email"]["minLength"], 6)
            self.assertEqual(properties["email"]["maxLength"], 254)
            self.assertIn({"format": "email", "type": "string"}, properties["backup"]["anyOf"])
        self.assertNotIn("twice", ns["RecordCreate"].model_fields)
        self.assertTrue(ns["RecordResponse"].model_json_schema()["properties"]["twice"]["readOnly"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](email="a@example.com", name="Ty", amount=1, twice=2)

    def test_invalid_modifiers_fail_before_any_generation(self):
        invalid = [
            "email:str:format=", "email:str:format=Email", "email:str:format= email",
            "email:str:format=url", "email:str:format=fax", "email:str:format=slug",
            "email:str:format=email:format=email", "email:str:format=email:format=url",
            "email:str:format", "email:str:email", "email:email", "email:array(email)",
            "email:str:format=email:min=1", "email:str:format=email:regex=[",
            "email:str:format=email:length=0", "email:str:format=email:computed=1",
        ] + [f"email:{kind}:format=email" for kind in (
            "int", "float", "bool", "uuid", "decimal(10,2)", "json()", "array(str)",
            "date", "datetime", "choice(A,B)", "enum(A,B)", "many_to_many(Role)",
        )]
        for definition in invalid:
            with self.subTest(definition=definition), ExitStack() as stack:
                generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
                register = stack.enter_context(patch.object(Registry, "register"))
                with self.assertRaises(ValueError):
                    pipeline.generate_module("Record", [definition])
                for generator in generators:
                    generator.assert_not_called()
                register.assert_not_called()

    def test_programmatic_metadata_rejects_unsupported_formats(self):
        for field in (
            Field("email", "str", "String", format="unknown"),
            Field("email", "int", "Integer", format="email"),
            Field("email", "str", "JSON", format="email"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    FieldValidator.validate([field])
                module = ModuleDefinition("Record", "Record", "record", "records", [field])
                with patch("tools.generate_schema.render_template") as render:
                    with self.assertRaises(ValueError):
                        generate_schema(module)
                    render.assert_not_called()

    def test_models_and_other_outputs_preserved(self):
        plain_definitions = ["email:str:length=254:unique:index", "backup:text:nullable"]
        plain_sources, plain_registry = run_generation(plain_definitions)
        email_definitions = [item + ":format=email" for item in plain_definitions]
        ns, sources, registry = schemas(email_definitions)
        for template in ("model.j2", "crud.j2", "service.j2", "router.j2"):
            self.assertEqual(sources[template], plain_sources[template])
        for field in registry["Record"]["fields"]:
            self.assertEqual(field.pop("format"), "email")
        self.assertEqual(registry, plain_registry)
        model = load_model(sources["model.j2"])
        try:
            self.assertIsInstance(model.email.type, String)
            self.assertEqual(model.email.type.length, 254)
            self.assertTrue(model.email.unique)
            self.assertTrue(model.email.index)
            self.assertIsInstance(model.backup.type, Text)
            self.assertTrue(model.backup.nullable)
        finally:
            model.registry.dispose()
        plain_ns, _, _ = schemas(plain_definitions)
        self.assertEqual(plain_ns["RecordCreate"](email="not an email").email, "not an email")
        self.assertNotIn("format", plain_ns["RecordCreate"].model_json_schema()["properties"]["email"])

    def test_database_round_trip_expression_uniqueness_and_update(self):
        definitions = [
            "email:str:format=email", "amount:int:min=1", "twice:int:computed=amount * 2",
            "expression_index(lower(email),where=deleted_at is None,unique=True)", "soft_delete",
        ]
        ns, _, _ = schemas(definitions)
        base, models, _, _ = generate_models({"Record": definitions})
        model = models["Record"]
        engine = database(base)
        try:
            with Session(engine) as session:
                value = ns["RecordCreate"](email="Person@EXAMPLE.COM", amount=2)
                row = model(**value.model_dump(exclude_unset=True))
                session.add(row)
                session.commit()
                session.refresh(row)
                self.assertEqual(row.email, "Person@example.com")
                self.assertEqual(ns["RecordResponse"].model_validate(row).twice, 4)
                update = ns["RecordUpdate"](email="Other@EXAMPLE.COM")
                for key, value in update.model_dump(exclude_unset=True).items():
                    setattr(row, key, value)
                session.commit()
                self.assertEqual(row.email, "Other@example.com")
                duplicate = ns["RecordCreate"](email="other@example.com", amount=1)
                session.add(model(**duplicate.model_dump(exclude_unset=True)))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                self.assertEqual(session.query(model).count(), 1)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_email_keys_relationships_and_field_names(self):
        base, models, sources, registry = generate_models({
            "User": ["email:str:pk:format=email"],
            "Post": ["owner_id:str:format=email:fk=users.email:one_to_many(User,posts):cascade_delete:passive_deletes"],
        })
        engine = database(base)
        try:
            namespaces = {}
            for name in ("User", "Post"):
                ns = {"__name__": f"generated_email_{name}"}
                exec(compile(sources[name]["schema.j2"], "<email-relationship-schema>", "exec"), ns)
                namespaces[name] = ns
            self.assertNotIn("id", namespaces["User"]["UserResponse"].model_fields)
            with self.assertRaises(ValidationError):
                namespaces["User"]["UserCreate"]()
            with Session(engine) as session:
                owner = models["User"](**namespaces["User"]["UserCreate"](email="Ty@EXAMPLE.COM").model_dump())
                session.add(owner)
                session.flush()
                article = models["Post"](**namespaces["Post"]["PostCreate"](owner_id="Ty@EXAMPLE.COM").model_dump())
                session.add(article)
                session.commit()
                self.assertEqual(owner.posts, [article])
                self.assertEqual(article.owner.email, "Ty@example.com")
                self.assertEqual(registry["Post"]["fields"][0]["format"], "email")
                session.delete(owner)
                session.commit()
                self.assertEqual(session.query(models["Post"]).count(), 0)
        finally:
            engine.dispose()
            base.registry.dispose()
        ns, _, _ = schemas(["EmailStr:str:format=email", "format:str:format=email", "email:str"])
        value = ns["RecordCreate"](EmailStr="a@example.com", format="b@example.com", email="plain")
        self.assertEqual(value.EmailStr, "a@example.com")
        self.assertEqual(value.email, "plain")

    def test_dependency_is_optional_for_plain_schemas_and_missing_email_dependency_is_clear(self):
        original_import = builtins.__import__

        def without_email_validator(name, *args, **kwargs):
            if name == "email_validator":
                raise ImportError("email_validator blocked for smoke test")
            return original_import(name, *args, **kwargs)

        plain_sources, _ = run_generation(["email:str"])
        email_sources, _ = run_generation(["email:str:format=email"])
        with patch("builtins.__import__", side_effect=without_email_validator):
            namespace = {"__name__": "generated_without_email_dependency"}
            exec(compile(plain_sources["schema.j2"], "<plain-schema>", "exec"), namespace)
            self.assertEqual(namespace["RecordCreate"](email="plain").email, "plain")
            with self.assertRaisesRegex(ImportError, "email-validator"):
                exec(compile(email_sources["schema.j2"], "<email-schema>", "exec"), namespace)


if __name__ == "__main__":
    unittest.main(verbosity=2)
