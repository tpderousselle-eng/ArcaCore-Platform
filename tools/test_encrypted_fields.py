"""Exercise encrypted fields without writing generated application files."""

import base64
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from tools.core.encrypted_field_parser import DEFAULT_ENCRYPTION_KEY_ENV
from tools.core.field_parser import Field, parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.generate_model import generate_model
from tools.generate_schema import generate_schema
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, load_model, pipeline, run_generation
from tools.test_custom_validators import rules
from tools.test_validators import schemas


def encryption_key():
    return base64.urlsafe_b64encode(
        AESGCM.generate_key(bit_length=256)
    ).decode("ascii")


class EncryptedFieldSmokeTest(unittest.TestCase):
    def prepare(self, definitions, env_name=DEFAULT_ENCRYPTION_KEY_ENV, key=None):
        key = key or encryption_key()
        environment = patch.dict(os.environ, {env_name: key}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        sources, registry = run_generation(definitions)
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        return model, engine, sources, registry

    def assert_invalid(self, definitions):
        generators = []
        with patch.object(Registry, "register") as register:
            patches = [patch.object(pipeline, f"generate_{kind}") for kind in GENERATORS]
            try:
                generators = [item.start() for item in patches]
                with self.assertRaises(ValueError):
                    pipeline.generate_module("Record", definitions)
            finally:
                for item in reversed(patches):
                    item.stop()
        for generator in generators:
            generator.assert_not_called()
        register.assert_not_called()

    def test_database_round_trip_randomized_insert_and_update(self):
        model, engine, _, _ = self.prepare(["secret:str:encrypted"])
        with Session(engine) as session:
            row = model(secret="classified")
            comparison = model(secret="classified")
            session.add_all([row, comparison])
            session.commit()
            identifier = row.id
        with engine.connect() as connection:
            first, independently_encrypted = connection.exec_driver_sql(
                "SELECT secret FROM records ORDER BY id"
            ).scalars().all()
        self.assertTrue(first.startswith("v1."))
        self.assertNotIn("classified", first)
        self.assertNotEqual(first, independently_encrypted)
        with Session(engine) as session:
            row = session.get(model, identifier)
            self.assertEqual(row.secret, "classified")
            row.secret = "classified again"
            session.commit()
        with engine.connect() as connection:
            second = connection.exec_driver_sql(
                "SELECT secret FROM records WHERE id = ?", (identifier,)
            ).scalar_one()
        self.assertNotEqual(first, second)
        self.assertNotIn("classified again", second)

    def test_unicode_long_text_and_nullable_values(self):
        model, engine, _, _ = self.prepare([
            "note:text:nullable:encrypted",
            "label:str:length=120:encrypted",
        ])
        message = "ArcaCore — 🔐\n" + "confidential " * 500
        with Session(engine) as session:
            session.add_all([model(note=message, label="private"), model(note=None, label="empty")])
            session.commit()
        with Session(engine) as session:
            rows = session.scalars(select(model).order_by(model.id)).all()
            self.assertEqual(rows[0].note, message)
            self.assertIsNone(rows[1].note)
        with engine.connect() as connection:
            raw = connection.exec_driver_sql(
                "SELECT note, label FROM records ORDER BY id"
            ).all()
        self.assertNotIn("confidential", raw[0][0])
        self.assertIsNone(raw[1][0])
        self.assertTrue(raw[0][1].startswith("v1."))

    def test_schema_constraints_custom_validators_and_metadata(self):
        calls = []

        def normalize(value):
            calls.append(value)
            return value.strip()

        with rules(normalize=normalize):
            namespace, _, _ = schemas([
                r"secret:str:min_length=4:length=20:encrypted:validator=application_rules.normalize:regex=^[a-z ]+$"
            ])
        for suffix in ("Create", "Update", "Response"):
            schema = namespace["Record" + suffix]
            arguments = {"id": 1} if suffix == "Response" else {}
            value = schema(secret="  private  ", **arguments)
            self.assertEqual(value.secret, "private")
            properties = schema.model_json_schema()["properties"]
            self.assertTrue(properties["secret"]["x-arca-encrypted"])
        with self.assertRaises(ValidationError):
            namespace["RecordCreate"](secret="NO")
        self.assertEqual(calls, ["  private  "] * 3)

    def test_cli_registry_custom_environment_and_no_key_material(self):
        key = encryption_key()
        with patch.dict(os.environ, {"RECORD_KEYRING": key}, clear=False):
            namespace, sources, registry = schemas(
                ["secret:text:encrypted=RECORD_KEYRING"], use_cli=True
            )
        metadata = json.loads(json.dumps(registry))["Record"]["fields"][0]
        self.assertTrue(metadata["encrypted"])
        self.assertEqual(metadata["encryption_key_env"], "RECORD_KEYRING")
        self.assertNotIn(key, json.dumps(registry))
        self.assertNotIn(key, sources["model.j2"])
        self.assertIn("EncryptedString('RECORD_KEYRING', 'records.secret')", sources["model.j2"])
        self.assertTrue(
            namespace["RecordCreate"].model_json_schema()["properties"]["secret"]["x-arca-encrypted"]
        )

    def test_missing_empty_and_malformed_keys_fail_at_bind(self):
        sources, _ = run_generation(["secret:str:encrypted=TEST_MISSING_KEY"])
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        for configured in (None, "", "not-base64", base64.urlsafe_b64encode(b"short").decode("ascii")):
            replacement = {} if configured is None else {"TEST_MISSING_KEY": configured}
            with self.subTest(configured=configured), patch.dict(os.environ, replacement, clear=True):
                with Session(engine) as session:
                    session.add(model(secret="value"))
                    with self.assertRaises(StatementError) as error:
                        session.commit()
                    self.assertIn("TEST_MISSING_KEY", str(error.exception))

    def test_tampering_wrong_key_and_column_swaps_are_rejected(self):
        key = encryption_key()
        model, engine, _, _ = self.prepare(
            ["first:str:encrypted", "second:str:encrypted"], key=key
        )
        with Session(engine) as session:
            session.add(model(first="alpha", second="bravo"))
            session.commit()
        with engine.begin() as connection:
            first, second = connection.exec_driver_sql(
                "SELECT first, second FROM records WHERE id = 1"
            ).one()
            altered = first[:-2] + ("A" if first[-2] != "A" else "B") + first[-1]
            connection.exec_driver_sql(
                "UPDATE records SET first = ? WHERE id = 1", (altered,)
            )
        with Session(engine) as session, self.assertRaises(InvalidTag):
            session.get(model, 1)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE records SET first = ?, second = ? WHERE id = 1",
                (second, first),
            )
        with Session(engine) as session, self.assertRaises(InvalidTag):
            session.get(model, 1)
        with patch.dict(os.environ, {DEFAULT_ENCRYPTION_KEY_ENV: encryption_key()}, clear=False):
            with Session(engine) as session, self.assertRaises(InvalidTag):
                session.get(model, 1)

    def test_key_rotation_reads_old_and_writes_with_active_key(self):
        old_key, new_key = encryption_key(), encryption_key()
        model, engine, _, _ = self.prepare(["secret:str:encrypted"], key=old_key)
        with Session(engine) as session:
            session.add(model(secret="old value"))
            session.commit()
        with patch.dict(
            os.environ,
            {DEFAULT_ENCRYPTION_KEY_ENV: f"{new_key},{old_key}"},
            clear=False,
        ):
            with Session(engine) as session:
                row = session.get(model, 1)
                self.assertEqual(row.secret, "old value")
                row.secret = "new value"
                session.commit()
        with patch.dict(os.environ, {DEFAULT_ENCRYPTION_KEY_ENV: new_key}, clear=False):
            with Session(engine) as session:
                self.assertEqual(session.get(model, 1).secret, "new value")
        with patch.dict(os.environ, {DEFAULT_ENCRYPTION_KEY_ENV: old_key}, clear=False):
            with Session(engine) as session, self.assertRaises(InvalidTag):
                session.get(model, 1)

    def test_sql_comparisons_are_rejected_and_ddl_uses_text(self):
        model, _, sources, _ = self.prepare(["secret:str:length=40:encrypted"])
        with self.assertRaisesRegex(TypeError, "cannot be used in SQL expressions"):
            model.secret == "value"
        with self.assertRaisesRegex(TypeError, "cannot be used in SQL expressions"):
            "value" == model.secret
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("secret TEXT", ddl)
        self.assertNotIn("value", ddl)
        self.assertIn("process_bind_param", sources["model.j2"])

    def test_invalid_types_modifiers_duplicates_and_environment_names(self):
        invalid = (
            ["value:int:encrypted"],
            ["value:json():encrypted"],
            ["value:str:pk:encrypted"],
            ["value:str:unique:encrypted"],
            ["value:str:index:encrypted"],
            ["value:str:default='secret':encrypted"],
            ["value:str:encrypted:encrypted"],
            ["value:str:encrypted="],
            ["value:str:encrypted=lowercase"],
            ["value:str:encrypted=1KEY"],
            ["value:str:encrypted=KEY-NAME"],
            ["id:str:encrypted"],
            ["created_at:text:encrypted"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def test_indexes_constraints_and_predicates_cannot_use_encrypted_fields(self):
        cases = (
            ["secret:str:encrypted", "other:str", "index(secret,other)"],
            ["secret:str:encrypted", "partial_index(secret,where=id > 0)"],
            ["secret:str:encrypted", "partial_index(id,where=secret == 'x')"],
            ["secret:str:encrypted", "expression_index(lower(secret))"],
            ["secret:str:encrypted", "other:str", "unique_together(secret,other)"],
            ["secret:str:encrypted", "check(secret == 'x')"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def test_computed_and_hybrid_fields_cannot_read_encrypted_values(self):
        for definitions in (
            ["secret:str:encrypted", "copy:str:computed=secret"],
            ["secret:str:encrypted", "copy:str:hybrid=secret + 'x'"],
            ["source:str", "secret:str:encrypted:computed=source"],
            ["source:str", "secret:str:encrypted:hybrid=source"],
        ):
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def test_programmatic_metadata_is_validated_before_direct_generation(self):
        field = Field(
            name="secret",
            python_type="int",
            sqlalchemy_type="Integer",
            encrypted=True,
        )
        module = ModuleDefinition("Record", "Record", "record", "records", [field])
        with patch("tools.generate_model.render_template") as render:
            with self.assertRaises(ValueError):
                generate_model(module)
            render.assert_not_called()
        with patch("tools.generate_schema.render_template") as render:
            with self.assertRaises(ValueError):
                generate_schema(module)
            render.assert_not_called()
        with self.assertRaises(ValueError):
            Registry.register(module)

    def test_soft_delete_plain_fields_and_generated_layers_compose(self):
        model, engine, sources, registry = self.prepare([
            "identifier:str:pk",
            "name:str",
            "secret:text:nullable:encrypted=COMPOSE_KEY",
            "soft_delete",
        ], env_name="COMPOSE_KEY")
        with Session(engine) as session:
            session.add(model(identifier="one", name="visible", secret="hidden"))
            session.commit()
            row = session.get(model, "one")
            self.assertEqual((row.name, row.secret), ("visible", "hidden"))
        self.assertTrue(registry["Record"]["soft_delete"])
        self.assertIn("deleted_at", sources["model.j2"])
        for kind in ("crud.j2", "service.j2", "router.j2"):
            self.assertTrue(sources[kind].strip())

    def test_plain_models_and_schema_behavior_remain_unchanged(self):
        namespace, sources, registry = schemas(["name:str:length=30", "count:int:min=0"])
        self.assertNotIn("EncryptedString", sources["model.j2"])
        self.assertNotIn("cryptography", sources["model.j2"])
        self.assertNotIn("x-arca-encrypted", json.dumps(registry))
        value = namespace["RecordCreate"](name="Arca", count=2)
        self.assertEqual(value.model_dump(), {"name": "Arca", "count": 2})
        response = namespace["RecordResponse"].model_validate(
            SimpleNamespace(id=1, name="Arca", count=2)
        )
        self.assertEqual(response.id, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
