"""Smoke-test generated phone schemas and database composition in memory."""

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
from tools.test_composite_indexes import GENERATORS, pipeline, run_generation
from tools.test_one_to_many import database, generate_models
from tools.test_validators import schemas
from tools.validators.field_validator import FieldValidator


class PhoneSmokeTest(unittest.TestCase):
    def test_international_numbers_normalize_without_network(self):
        ns, _, _ = schemas(["phone:str:format=phone"])
        cases = {
            "+1 (650) 253-0000": "+16502530000",
            "  +1 650.253.0000  ": "+16502530000",
            "+44 20 8366 1177": "+442083661177",
            "+39 02 3661 8300": "+390236618300",
            "+800 1234 5678": "+80012345678",
        }
        with patch("socket.getaddrinfo", side_effect=AssertionError("Network request")), patch(
            "socket.socket", side_effect=AssertionError("Network request")
        ):
            for raw, normalized in cases.items():
                with self.subTest(raw=raw):
                    value = ns["RecordCreate"](phone=raw)
                    self.assertIsInstance(value.phone, str)
                    self.assertEqual(value.phone, normalized)
                    self.assertEqual(json.loads(value.model_dump_json()), {"phone": normalized})
                    self.assertEqual(ns["RecordCreate"](phone=value.phone).phone, normalized)

    def test_invalid_numbers_and_lossy_inputs_rejected_in_all_schemas(self):
        ns, _, _ = schemas(["phone:str:format=phone"])
        invalid = (
            "", " ", "6502530000", "0016502530000", "911", "+1", "+0 6502530000",
            "+999123456789", "+1 200 123 0101", "+165025300000000000",
            "+16502530000 ext 123", "+16502530000x123", "+16502530000#123",
            "tel:+16502530000;ext=123", "+1-800-FLOWERS", "Call +16502530000",
            "+16502530000 / +442083661177", "+16502530000,123", "+16502530000;123",
            "++16502530000", "+１６５０２５３００００", "+1\t6502530000",
            "+16502530000\n", "\r+16502530000", "+1650253\x000000",
            "+16502530000" + " " * 128, 16502530000, True, b"+16502530000", [], {}, None,
        )
        for suffix in ("Create", "Update", "Response"):
            for value in invalid:
                with self.subTest(schema=suffix, value=value), self.assertRaises(ValidationError):
                    ns["Record" + suffix](phone=value, **({"id": 1} if suffix == "Response" else {}))

    def test_nullable_required_and_update_omission(self):
        ns, _, _ = schemas(["phone:str:format=phone", "backup:text:nullable:format=phone"])
        create, update, response = (ns["Record" + suffix] for suffix in ("Create", "Update", "Response"))
        with self.assertRaises(ValidationError):
            create()
        self.assertIsNone(create(phone="+16502530000").backup)
        self.assertEqual(update().model_dump(exclude_unset=True), {})
        self.assertEqual(update(backup=None).model_dump(exclude_unset=True), {"backup": None})
        self.assertEqual(update(phone="+1 650-253-0000").model_dump(exclude_unset=True), {"phone": "+16502530000"})
        with self.assertRaises(ValidationError):
            update(phone=None)
        with self.assertRaises(ValidationError):
            update(backup="invalid")
        with self.assertRaises(ValidationError):
            response(id=1, phone="+16502530000")
        value = response.model_validate(SimpleNamespace(id=1, phone="+1 650-253-0000", backup=None))
        self.assertEqual(value.phone, "+16502530000")
        self.assertIsNone(value.backup)

    def test_defaults_are_validated_and_database_expressions_not_executed(self):
        ns, _, _ = schemas(["phone:str:format=phone:default='+1 650-253-0000'"])
        self.assertEqual(ns["RecordCreate"]().phone, "+16502530000")
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        for default in ("'6502530000'", "'bad'", "123", "None"):
            with self.subTest(default=default):
                ns, _, _ = schemas([f"phone:str:format=phone:default={default}"])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"]()
        ns, _, _ = schemas(["phone:text:format=phone:nullable:default=None"])
        self.assertIsNone(ns["RecordCreate"]().phone)
        ns, _, _ = schemas(["phone:str:format=phone:default=raise_if_executed()"])
        self.assertEqual(ns["RecordCreate"]().model_dump(exclude_unset=True), {})
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](phone="invalid")

    def test_length_and_regex_use_normalized_number(self):
        ns, _, _ = schemas([r"phone:str:format=phone:min_length=12:length=12:regex=^\+1"])
        for suffix in ("Create", "Update", "Response"):
            cls = ns["Record" + suffix]
            extra = {"id": 1} if suffix == "Response" else {}
            self.assertEqual(cls(phone="  +1 (650) 253-0000  ", **extra).phone, "+16502530000")
            with self.assertRaises(ValidationError):
                cls(phone="+44 20 8366 1177", **extra)
        for bound in ("min_length=13", "length=11"):
            ns, _, _ = schemas([f"phone:str:format=phone:{bound}"])
            with self.assertRaises(ValidationError):
                ns["RecordCreate"](phone="+16502530000")
        ns, _, _ = schemas([r"phone:str:format=phone:regex=^\+44"])
        self.assertEqual(ns["RecordCreate"](phone="+44 20 8366 1177").phone, "+442083661177")
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](phone="+16502530000")
        first = parse_fields("Record", ["phone:str:format=phone:nullable:length=16"])
        second = parse_fields("Record", ["phone:str:length=16:nullable:format=phone"])
        self.assertEqual(first, second)

    def test_cli_registry_json_schema_and_email_coexistence(self):
        ns, sources, registry = schemas([
            "phone:str:format=phone:length=16", "backup:text:nullable:format=phone",
            "email:str:format=email", "name:str", "amount:int:min=1", "twice:int:computed=amount * 2",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertEqual(metadata[0]["format"], "phone")
        self.assertEqual(metadata[0]["sqlalchemy_type"], "String")
        self.assertEqual(metadata[1]["format"], "phone")
        self.assertEqual(metadata[2]["format"], "email")
        self.assertNotIn("format", metadata[3])
        self.assertEqual(sources["schema.j2"].count("def _arca_normalize_phone"), 1)
        for suffix in ("Create", "Update", "Response"):
            properties = ns["Record" + suffix].model_json_schema()["properties"]
            self.assertEqual(properties["phone"]["type"], "string")
            self.assertEqual(properties["phone"]["format"], "phone")
            self.assertEqual(properties["phone"]["maxLength"], 16)
            self.assertIn({"type": "string", "format": "phone"}, properties["backup"]["anyOf"])
            self.assertEqual(properties["email"]["format"], "email")
        payload = {"phone": "+1 650-253-0000", "email": "Ty@EXAMPLE.COM", "name": "Ty", "amount": 1}
        value = ns["RecordCreate"](**payload)
        self.assertEqual(value.phone, "+16502530000")
        self.assertEqual(value.email, "Ty@example.com")
        self.assertNotIn("twice", value.model_dump())
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](**payload, twice=2)
        self.assertTrue(ns["RecordResponse"].model_json_schema()["properties"]["twice"]["readOnly"])

    def test_invalid_dsl_fails_before_any_generation(self):
        invalid = [
            "phone:str:format=", "phone:str:format=Phone", "phone:str:format= phone",
            "phone:str:format=phone:format=phone", "phone:str:format=phone:format=email",
            "phone:str:format=email:format=phone", "phone:str:format=phone(US)",
            "phone:str:format=phone:region=US", "phone:str:phone", "phone:phone", "phone:array(phone)",
            "phone:str:format=phone:min=1", "phone:str:format=phone:length=0",
            "phone:str:format=phone:regex=[", "phone:str:format=phone:computed=1",
        ] + [f"phone:{kind}:format=phone" for kind in (
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
            Field("phone", "int", "Integer", format="phone"),
            Field("phone", "str", "ARRAY", format="phone"),
            Field("phone", "str", "String", format="fax"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    FieldValidator.validate([field])
                module = ModuleDefinition("Record", "Record", "record", "records", [field])
                with patch("tools.generate_schema.render_template") as render:
                    with self.assertRaises(ValueError):
                        generate_schema(module)
                    render.assert_not_called()
        field = Field("phone", "text", "Text", format="phone")
        FieldValidator.validate([field])
        self.assertEqual(field.format, "phone")

    def test_database_round_trip_normalized_uniqueness_and_update(self):
        definitions = ["phone:str:format=phone:unique:length=16", "backup:text:nullable:format=phone"]
        ns, _, _ = schemas(definitions)
        base, models, _, _ = generate_models({"Record": definitions})
        model = models["Record"]
        engine = database(base)
        try:
            self.assertIsInstance(model.phone.type, String)
            self.assertEqual(model.phone.type.length, 16)
            self.assertIsInstance(model.backup.type, Text)
            with Session(engine) as session:
                value = ns["RecordCreate"](phone="+1 (650) 253-0000")
                row = model(**value.model_dump(exclude_unset=True))
                session.add(row)
                session.commit()
                self.assertEqual(ns["RecordResponse"].model_validate(row).phone, "+16502530000")
                duplicate = ns["RecordCreate"](phone="+1 650.253.0000")
                session.add(model(**duplicate.model_dump(exclude_unset=True)))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                update = ns["RecordUpdate"](phone="+44 20 8366 1177")
                for key, value in update.model_dump(exclude_unset=True).items():
                    setattr(row, key, value)
                session.commit()
                self.assertEqual(row.phone, "+442083661177")
                self.assertEqual(session.query(model).count(), 1)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_custom_phone_keys_and_relationships(self):
        base, models, sources, registry = generate_models({
            "User": ["phone:str:pk:format=phone"],
            "Post": ["owner_id:str:format=phone:fk=users.phone:one_to_many(User,posts):cascade_delete:passive_deletes"],
        })
        engine = database(base)
        try:
            namespaces = {}
            for name in ("User", "Post"):
                ns = {"__name__": f"generated_phone_{name}"}
                exec(compile(sources[name]["schema.j2"], "<phone-key-schema>", "exec"), ns)
                namespaces[name] = ns
            self.assertNotIn("id", namespaces["User"]["UserResponse"].model_fields)
            with self.assertRaises(ValidationError):
                namespaces["User"]["UserCreate"]()
            with Session(engine) as session:
                owner = models["User"](**namespaces["User"]["UserCreate"](phone="+1 650-253-0000").model_dump())
                session.add(owner)
                session.flush()
                article = models["Post"](**namespaces["Post"]["PostCreate"](owner_id="+1 (650) 253-0000").model_dump())
                session.add(article)
                session.commit()
                self.assertEqual(owner.posts, [article])
                self.assertEqual(article.owner.phone, "+16502530000")
                self.assertEqual(registry["Post"]["fields"][0]["format"], "phone")
                session.delete(owner)
                session.commit()
                self.assertEqual(session.query(models["Post"]).count(), 0)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_existing_outputs_and_field_names_remain_compatible(self):
        definitions = ["phone:str:length=16", "amount:int", "twice:int:computed=amount * 2",
                       "soft_delete", "partial_index(phone,where=deleted_at is None,unique=True)",
                       "expression_index(lower(phone))", "check(amount >= 0)"]
        before, before_registry = run_generation(definitions)
        after, after_registry = run_generation(["phone:str:length=16:format=phone", *definitions[1:]])
        for kind in ("model", "crud", "service", "router"):
            self.assertEqual(before[f"{kind}.j2"], after[f"{kind}.j2"])
        self.assertEqual(after_registry["Record"]["fields"][0].pop("format"), "phone")
        self.assertEqual(before_registry, after_registry)
        self.assertNotIn("phonenumbers", before["schema.j2"])
        self.assertNotIn("from tools", after["schema.j2"])
        ns, _, _ = schemas(["phone:str", "phonenumbers:str:format=phone", "format:text:format=phone"])
        value = ns["RecordCreate"](phone="plain", phonenumbers="+16502530000", format="+442083661177")
        self.assertEqual(value.phone, "plain")
        self.assertEqual(value.phonenumbers, "+16502530000")
        ns, _, _ = schemas([r"phone:str:regex=^format=phone:literal$"])
        self.assertEqual(ns["RecordCreate"](phone="format=phone:literal").phone, "format=phone:literal")

    def test_missing_dependency_only_affects_phone_schemas(self):
        original_import = builtins.__import__

        def without_phonenumbers(name, *args, **kwargs):
            if name == "phonenumbers":
                raise ImportError("phonenumbers blocked for smoke test")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_phonenumbers):
            ns, _, _ = schemas(["phone:str", "email:str:format=email"])
            self.assertEqual(ns["RecordCreate"](phone="plain", email="Ty@EXAMPLE.COM").email, "Ty@example.com")
            sources, _ = run_generation(["phone:str:format=phone"])
            with self.assertRaisesRegex(ImportError, "python -m pip install"):
                exec(compile(sources["schema.j2"], "<missing-phone-dependency>", "exec"), {"__name__": "missing_phone"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
