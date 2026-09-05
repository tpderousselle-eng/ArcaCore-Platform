"""Smoke-test generated Pydantic schemas entirely in memory."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from tools.core.field_parser import parse_fields
from tools.test_composite_indexes import run_generation, pipeline
from tools.registry.registry import Registry
from tools.validators.field_validator import FieldValidator


def schemas(definitions, use_cli=False):
    sources, registry = run_generation(definitions, use_cli=use_cli)
    namespace = {"__name__": "generated_validator_schema"}
    exec(compile(sources["schema.j2"], "<generated-schema>", "exec"), namespace)
    return namespace, sources, registry


class ValidatorSmokeTest(unittest.TestCase):
    def test_numeric_boundaries_and_decimal_precision(self):
        ns, _, _ = schemas([
            "quantity:int:min=1:max=10", "score:float:min=-0.5:max=0.5",
            "price:decimal(24,18):min=0.100000000000000001:max=9.999999999999999999",
        ])
        create = ns["RecordCreate"]
        payload = {"quantity": 1, "score": -0.5, "price": "0.100000000000000001"}
        self.assertEqual(create(**payload).price, Decimal(payload["price"]))
        for key, value in (("quantity", 0), ("quantity", 11), ("score", -0.6), ("score", 0.6),
                           ("price", "0.100000000000000000"), ("price", "10")):
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                create(**{**payload, key: value})

    def test_string_length_regex_colons_and_escaping(self):
        ns, _, _ = schemas([r"code:str:min_length=4:length=12:regex=^(?:AB|CD):\d+$"])
        create = ns["RecordCreate"]
        self.assertEqual(create(code="AB:1").code, "AB:1")
        for value in ("A:1", "XY:12", "AB:12345678901", "AB:x"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                create(code=value)
        ns, _, _ = schemas(["code:str:regex=^O'Reilly$"])
        self.assertEqual(ns["RecordCreate"](code="O'Reilly").code, "O'Reilly")

    def test_update_omission_nullability_and_bounds(self):
        ns, _, _ = schemas(["age:int:min=18", "name:str:nullable:min_length=2", "metadata:json()"])
        update = ns["RecordUpdate"]
        self.assertEqual(update().model_dump(exclude_unset=True), {})
        self.assertEqual(update(name=None).model_dump(exclude_unset=True), {"name": None})
        self.assertEqual(update(age=20).model_dump(exclude_unset=True), {"age": 20})
        for payload in ({"age": None}, {"age": 17}, {"name": "a"}, {"metadata": None}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                update(**payload)
        with self.assertRaises(ValidationError):
            ns["RecordCreate"]()

    def test_defaults_are_validated_and_not_executed(self):
        ns, _, _ = schemas(["age:int:min=18:default=21", "name:str:length=4:default='Ty'"])
        self.assertEqual(ns["RecordCreate"]().age, 21)
        ns, _, _ = schemas(["age:int:min=18:default=10"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"]()
        ns, _, _ = schemas(["age:int:default=list"])
        self.assertEqual(ns["RecordCreate"]().model_dump(exclude_unset=True), {})
        ns, _, _ = schemas(["price:decimal(24,18):default=0.100000000000000001"])
        self.assertEqual(ns["RecordCreate"]().price, Decimal("0.100000000000000001"))

    def test_existing_types_and_relationships(self):
        ns, _, _ = schemas([
            "identifier:uuid:pk", "status:choice(Draft,Published)", "phase:enum(New,Done)",
            "tags:array(str)", "references:array(uuid)", "metadata:json()", "enabled:bool",
            "day:date", "when:datetime", "owner_id:int:fk=users.id:one_to_one",
            "roles:many_to_many(Role)",
        ])
        key = uuid4()
        payload = dict(status="Draft", phase="New", tags=["one"], references=[str(key)],
                       metadata={"x": [1]}, enabled=True, day="2026-09-02",
                       when="2026-09-02T12:00:00", owner_id=1)
        value = ns["RecordCreate"](**payload)
        self.assertEqual(value.references, [key])
        self.assertNotIn("roles", value.model_dump())
        self.assertNotIn("identifier", value.model_dump(exclude_unset=True))
        self.assertNotIn("id", ns["RecordResponse"].model_fields)
        for changes in ({"status": "Other"}, {"phase": "Other"}, {"tags": [object()]},
                        {"references": ["invalid"]}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ns["RecordCreate"](**{**payload, **changes})
        response = ns["RecordResponse"].model_validate(SimpleNamespace(identifier=key, **payload))
        self.assertEqual(response.identifier, key)

    def test_response_required_fields_and_implicit_key(self):
        ns, _, _ = schemas(["name:str:length=4", "age:int:min=18:default=21"])
        self.assertEqual(ns["RecordResponse"].model_validate(SimpleNamespace(id=1, name="Ty", age=22)).id, 1)
        with self.assertRaises(ValidationError):
            ns["RecordResponse"](id=1, name="Ty")
        with self.assertRaises(ValidationError):
            ns["RecordResponse"](id=1, name="Ty", age=17)

    def test_cli_registry_and_json_schema(self):
        ns, sources, registry = schemas([
            "name:str:min_length=2:length=30:regex=^[A-Z]", "age:int:min=18:max=120",
            "index(name,age)", "unique_together(name,age)", "soft_delete",
        ], use_cli=True)
        fields = registry["Record"]["fields"]
        self.assertEqual(fields[0]["regex"], "^[A-Z]")
        self.assertEqual(fields[0]["min_length"], 2)
        self.assertEqual(fields[1]["min"], "18")
        properties = ns["RecordCreate"].model_json_schema()["properties"]
        self.assertEqual(properties["age"]["minimum"], 18)
        self.assertEqual(properties["name"]["maxLength"], 30)
        self.assertIn("deleted_at", sources["model.j2"])
        self.assertIn("UniqueConstraint", sources["model.j2"])

    def test_regex_rejects_catastrophic_backtracking_constructs(self):
        unsafe = (
            "value:str:regex=(a+)+$",
            "value:str:regex=(a|aa)+$",
            r"value:str:regex=(a+)\1$",
            "value:str:regex=(?=(a+))a+$",
            "value:str:regex=a*a*a*b",
        )
        for declaration in unsafe:
            with self.subTest(declaration=declaration), self.assertRaisesRegex(
                ValueError, "unsafe regex"
            ):
                FieldValidator.validate(parse_fields("Record", [declaration]))

    def test_regex_linear_time_subset_remains_supported(self):
        fields = parse_fields(
            "Record",
            [r"code:str:regex=^(?:AB|CD):\d+$", r"slug:str:regex=^[a-z0-9-]+$"],
        )
        FieldValidator.validate(fields)
        self.assertEqual(len(fields), 2)

    def test_invalid_rules_fail_before_any_generation(self):
        definitions = (
            "age:int:min=nan", "age:float:max=inf", "age:int:min=1.2", "age:str:min=1",
            "age:int:min=5:max=1", "age:int:min=", "age:int:min=x", "age:float:min=1e999",
            "age:int:min=1:min=2", "name:str:length=0", "name:str:min_length=-1",
            "name:str:min_length=4:length=2", "age:int:min_length=1", "name:str:regex=[",
            "age:int:regex=x", "name:str:regex=", "name:str:min_length=a",
            "roles:many_to_many(Role):min=1",
        )
        for definition in definitions:
            with self.subTest(definition=definition):
                with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
                    with self.assertRaises(ValueError):
                        pipeline.generate_module("Record", [definition])
                    model.assert_not_called()
                    register.assert_not_called()

    def test_empty_schemas_and_type_named_fields(self):
        ns, _, _ = schemas([])
        self.assertEqual(ns["RecordCreate"]().model_dump(), {})
        self.assertEqual(ns["RecordUpdate"]().model_dump(), {})
        ns, _, _ = schemas(["date:date", "datetime:datetime", "uuid:uuid", "decimal:decimal(8,2)"])
        result = ns["RecordCreate"](date="2026-01-01", datetime="2026-01-01T00:00:00", uuid=uuid4(), decimal="1.20")
        self.assertEqual(result.decimal, Decimal("1.20"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
