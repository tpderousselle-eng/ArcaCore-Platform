"""Exercise generated custom validators without writing application files."""

import builtins
from contextlib import contextmanager, ExitStack
from datetime import date
from decimal import Decimal
import json
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import ValidationError
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


@contextmanager
def modules(replacements):
    # Restore only our test modules; keep unrelated lazy dependency imports alive.
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in replacements}
    sys.modules.update(replacements)
    try:
        yield
    finally:
        for name, original in previous.items():
            if original is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@contextmanager
def rules(**functions):
    module = ModuleType("application_rules")
    module.__dict__.update(functions)
    with modules({"application_rules": module}):
        yield module


def identity(value):
    return value


class CustomValidatorSmokeTest(unittest.TestCase):
    def test_typed_values_rejections_and_all_schema_classes(self):
        calls = []

        def even(value):
            calls.append(value)
            self.assertIs(type(value), int)
            if value % 2:
                raise ValueError("Quantity must be even.")
            return value

        with rules(even=even):
            ns, _, _ = schemas(["quantity:int:min=0:validator=application_rules.even"])
        self.assertEqual(calls, [])
        for suffix in ("Create", "Update", "Response"):
            extra = {"id": 1} if suffix == "Response" else {}
            result = ns["Record" + suffix](quantity="4", **extra)
            self.assertEqual(result.quantity, 4)
            with self.assertRaises(ValidationError) as error:
                ns["Record" + suffix](quantity=3, **extra)
            self.assertEqual(error.exception.errors()[0]["loc"], ("quantity",))
            self.assertIn("Quantity must be even", str(error.exception))
        self.assertEqual(calls, [4, 3, 4, 3, 4, 3])
        calls.clear()
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](quantity=-2)
        self.assertEqual(calls, [])

    def test_ordered_transformations_are_revalidated_between_calls(self):
        calls = []

        def double(value):
            calls.append(("double", value))
            return str(value * 2)

        def add(value):
            calls.append(("add", value))
            self.assertIs(type(value), int)
            return value + 1

        with rules(double=double, add=add):
            ns, _, _ = schemas(["count:int:validator=application_rules.double:validator=application_rules.add"])
        self.assertEqual(ns["RecordCreate"](count="3").count, 7)
        self.assertEqual(calls, [("double", 3), ("add", 6)])
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertEqual(len(calls), 2)

    def test_return_values_cannot_bypass_type_bounds_regex_or_nullability(self):
        cases = (
            ("int:min=1:max=10", 2, 11), ("int:min=1", 2, "bad"),
            ("int", 2, None), ("str:length=4", "ok", "too-long"),
            ("str", "ok", 7), ("str:regex=^ok$", "ok", "wrong"),
        )
        for specification, value, returned in cases:
            with self.subTest(specification=specification):
                def change(value):
                    return returned
                # Regex is last, so put the custom reference before it.
                declaration = "value:" + specification
                before, separator, pattern = declaration.partition(":regex=")
                declaration = before + ":validator=application_rules.change" + (":regex=" + pattern if separator else "")
                with rules(change=change):
                    ns, _, _ = schemas([declaration])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"](value=value)
        called = []
        with rules(change=lambda value: -1, later=lambda value: called.append(value) or value):
            ns, _, _ = schemas(["value:int:min=0:validator=application_rules.change:validator=application_rules.later"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](value=1)
        self.assertEqual(called, [])

    def test_named_formats_normalize_before_rules_and_recheck_returns(self):
        cases = (
            ("email", "Ty@EXAMPLE.COM", "Ty@example.com", "bad"),
            ("phone", "+1 650-253-0000", "+16502530000", "123"),
            ("slug", "my-slug", "my-slug", "Bad Slug"),
            ("url", "HTTPS://EXAMPLE.COM", "https://example.com/", "javascript:bad"),
        )
        for format_name, raw, normalized, bad in cases:
            with self.subTest(format=format_name):
                seen = []
                with rules(check=lambda value: seen.append(value) or value):
                    ns, _, _ = schemas([f"value:str:format={format_name}:validator=application_rules.check"])
                self.assertEqual(ns["RecordCreate"](value=raw).value, normalized)
                self.assertEqual(seen, [normalized])
                with rules(check=lambda value: bad):
                    ns, _, _ = schemas([f"value:str:format={format_name}:validator=application_rules.check"])
                with self.assertRaises(ValidationError):
                    ns["RecordCreate"](value=raw)

    def test_nullability_omission_and_literal_defaults(self):
        calls = []

        def even(value):
            calls.append(value)
            if value % 2:
                raise ValueError("Must be even.")
            return value

        with rules(even=even):
            ns, _, _ = schemas(["value:int:nullable:default=4:validator=application_rules.even"])
            bad, _, _ = schemas(["value:int:default=3:validator=application_rules.even"])
            expression, _, _ = schemas(["value:int:default=raise_if_executed():validator=application_rules.even"])
        self.assertEqual(ns["RecordCreate"]().value, 4)
        self.assertEqual(calls, [4])
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertIsNone(ns["RecordUpdate"](value=None).value)
        self.assertIsNone(ns["RecordResponse"](id=1, value=None).value)
        self.assertEqual(calls, [4])
        with self.assertRaises(ValidationError):
            bad["RecordCreate"]()
        self.assertEqual(expression["RecordCreate"]().model_dump(exclude_unset=True), {})
        self.assertEqual(calls, [4, 3])
        with self.assertRaises(ValidationError):
            ns["RecordResponse"](id=1)
        with rules(none=lambda value: None, later=lambda value: self.fail("None must skip remaining rules")):
            ns, _, _ = schemas(["value:int:nullable:validator=application_rules.none:validator=application_rules.later"])
        self.assertIsNone(ns["RecordCreate"](value=1).value)

    def test_missing_or_incompatible_callables_fail_on_schema_import(self):
        async def asynchronous(value):
            return value

        def generator(value):
            yield value

        async def async_generator(value):
            yield value

        class AsyncCallable:
            async def __call__(self, value):
                return value

        for function in (7, asynchronous, generator, async_generator, AsyncCallable(), lambda: 1, lambda value, required: value):
            with self.subTest(function=function), rules(check=function):
                with self.assertRaisesRegex(TypeError, "application_rules.check"):
                    schemas(["value:int:validator=application_rules.check"])
        with rules():
            with self.assertRaises(ImportError):
                schemas(["value:int:validator=application_rules.missing"])
        with modules({"missing_application_rules": None}):
            with self.assertRaises(ImportError):
                schemas(["value:int:validator=missing_application_rules.check"])

    def test_runtime_awaitables_and_programming_errors_are_not_silenced(self):
        async def asynchronous(value):
            return value

        def generator(value):
            yield value

        for function in (lambda value: asynchronous(value), lambda value: generator(value)):
            with rules(check=function):
                ns, _, _ = schemas(["value:json():validator=application_rules.check"])
            with self.assertRaisesRegex(TypeError, "awaitable or generator"):
                ns["RecordCreate"](value={"ok": True})
        def broken(value):
            raise RuntimeError("Rule implementation failed")
        with rules(check=broken):
            ns, _, _ = schemas(["value:int:validator=application_rules.check"])
        with self.assertRaisesRegex(RuntimeError, "Rule implementation failed"):
            ns["RecordCreate"](value=1)

    def test_invalid_references_fail_before_generation_or_import(self):
        invalid = ["", "check", ".rules.check", "rules..check", "rules.check.", "rules.check()",
                   "rules.check(1)", "rules.check;import os", "rules['check']", "rules/check",
                   "rules.class", "rules._private", "__import__.check", "rules.café", " rules.check"]
        declarations = [f"value:int:validator={reference}" for reference in invalid]
        declarations += ["value:int:validator=rules.check:validator=rules.check", "roles:many_to_many(Role):validator=rules.check"]
        for declaration in declarations:
            with self.subTest(declaration=declaration), ExitStack() as stack:
                generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
                register = stack.enter_context(patch.object(Registry, "register"))
                with self.assertRaises(ValueError):
                    pipeline.generate_module("Record", [declaration])
                for generator in generators:
                    generator.assert_not_called()
                register.assert_not_called()
        fields = parse_fields("Record", ["a:int", "b:int"])
        fields[0].validators.append("rules.check")
        self.assertEqual(fields[1].validators, [])

    def test_programmatic_metadata_and_direct_generation(self):
        for references in (None, "rules.check", [7], ["rules.check", "rules.check"], ["rules.check()"]):
            field = Field("value", "int", "Integer", validators=references)
            with self.subTest(references=references):
                with self.assertRaises(ValueError):
                    FieldValidator.validate([field])
                with patch("tools.generate_schema.render_template") as render:
                    with self.assertRaises(ValueError):
                        generate_schema(ModuleDefinition("Record", "Record", "record", "records", [field]))
                    render.assert_not_called()
        field = Field("roles", "many_to_many", "Relationship", relationship_type="many_to_many", validators=["rules.check"])
        with self.assertRaises(ValueError):
            FieldValidator.validate([field])
        with patch("tools.generate_schema.render_template") as render:
            with self.assertRaises(ValueError):
                generate_schema(ModuleDefinition("Record", "Record", "record", "records", [field]))
            render.assert_not_called()
        field = Field("value", "int", "Integer", validators=["application_rules.check"])
        module = ModuleDefinition("Record", "Record", "record", "records", [field])
        with patch("tools.generate_schema.render_template") as render:
            generate_schema(module)
        context = render.call_args.kwargs.copy()
        source = env.get_template(context.pop("template_name")).render(**context)
        namespace = {"__name__": "generated_direct_custom"}
        with rules(check=identity):
            exec(compile(source, "<custom-schema>", "exec"), namespace)
        self.assertEqual(namespace["RecordCreate"](value="2").value, 2)

    def test_cli_registry_json_schema_order_and_import_deduplication(self):
        definitions = ["slug:str:format=slug:validator=application_rules.first:validator=application_rules.second",
                       "other:str:validator=application_rules.first", "plain:str"]
        with rules(first=identity, second=identity):
            ns, sources, registry = schemas(definitions, use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertEqual(metadata[0]["validators"], ["application_rules.first", "application_rules.second"])
        self.assertEqual(metadata[1]["validators"], ["application_rules.first"])
        self.assertNotIn("validators", metadata[2])
        self.assertEqual(sources["schema.j2"].count("from application_rules import first as"), 1)
        for suffix in ("Create", "Update", "Response"):
            prop = ns["Record" + suffix].model_json_schema()["properties"]["slug"]
            self.assertEqual(prop["format"], "slug")
            self.assertEqual(prop["x-arca-validators"], metadata[0]["validators"])
        first = parse_fields("Record", ["value:int:min=0:validator=rules.first:validator=rules.second"])
        second = parse_fields("Record", ["value:int:validator=rules.first:min=0:validator=rules.second"])
        self.assertEqual(first, second)

    def test_computed_fields_run_rules_only_on_response(self):
        called = []
        with rules(check=lambda value: called.append(value) or value):
            ns, _, _ = schemas(["amount:int", "twice:int:computed=amount * 2:validator=application_rules.check"])
        self.assertEqual(ns["RecordCreate"](amount=2).amount, 2)
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertEqual(called, [])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](amount=2, twice=4)
        value = ns["RecordResponse"].model_validate(SimpleNamespace(id=1, amount=2, twice=4))
        self.assertEqual(value.twice, 4)
        self.assertEqual(called, [4])
        prop = ns["RecordResponse"].model_json_schema()["properties"]["twice"]
        self.assertTrue(prop["readOnly"])
        self.assertEqual(prop["x-arca-validators"], ["application_rules.check"])

    def test_array_json_choice_and_scalar_types(self):
        received = []
        def check(value):
            received.append(value)
            return value
        with rules(check=check):
            ns, _, _ = schemas([
                "tags:array(int):validator=application_rules.check", "metadata:json():validator=application_rules.check",
                "status:choice(Draft,Published):validator=application_rules.check",
                "phase:enum(New,Done):validator=application_rules.check", "price:decimal(10,2):validator=application_rules.check",
                "when:date:validator=application_rules.check", "key:uuid:validator=application_rules.check",
            ])
        key = uuid4()
        value = ns["RecordCreate"](tags=["1", "2"], metadata={"a": 1}, status="Draft", phase="New", price="1.25", when="2026-09-03", key=str(key))
        self.assertEqual(received, [[1, 2], {"a": 1}, "Draft", "New", Decimal("1.25"), date(2026, 9, 3), key])
        self.assertIsInstance(value.key, UUID)
        with rules(check=lambda value: ["bad"]):
            ns, _, _ = schemas(["tags:array(int):validator=application_rules.check"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](tags=[1])
        with rules(check=lambda value: "Other"):
            ns, _, _ = schemas(["status:choice(Draft,Published):validator=application_rules.check"])
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](status="Draft")

    def test_database_uniqueness_and_custom_foreign_keys(self):
        def canonical(value):
            return value.lower()
        definitions = {"User": ["handle:str:pk:validator=application_rules.canonical"],
                       "Post": ["owner_id:str:fk=users.handle:one_to_many(User,posts):cascade_delete:passive_deletes:validator=application_rules.canonical"]}
        base, models, sources, _ = generate_models(definitions)
        engine = database(base)
        try:
            namespaces = {}
            with rules(canonical=canonical):
                for name in ("User", "Post"):
                    namespace = {"__name__": "custom_" + name}
                    exec(compile(sources[name]["schema.j2"], "<custom-key-schema>", "exec"), namespace)
                    namespaces[name] = namespace
            with Session(engine) as session:
                user = models["User"](**namespaces["User"]["UserCreate"](handle="TYLER").model_dump())
                session.add(user)
                session.flush()
                post = models["Post"](**namespaces["Post"]["PostCreate"](owner_id="Tyler").model_dump())
                session.add(post)
                session.commit()
                self.assertEqual(user.posts, [post])
                self.assertEqual(namespaces["User"]["UserResponse"].model_validate(user).handle, "tyler")
                duplicate = namespaces["User"]["UserCreate"](handle="Tyler")
                with Session(engine) as other:
                    other.add(models["User"](**duplicate.model_dump()))
                    with self.assertRaises(IntegrityError):
                        other.commit()
                    other.rollback()
                session.delete(user)
                session.commit()
                self.assertEqual(session.query(models["Post"]).count(), 0)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_existing_outputs_defaults_regex_and_field_names(self):
        definitions = ["name:str", "amount:int", "twice:int:computed=amount * 2", "soft_delete",
                       "partial_index(name,where=deleted_at is None,unique=True)", "expression_index(lower(name))", "check(amount >= 0)"]
        before, before_registry = run_generation(definitions)
        after, after_registry = run_generation(["name:str:validator=application_rules.check", *definitions[1:]])
        for kind in ("model", "crud", "service", "router"):
            self.assertEqual(before[f"{kind}.j2"], after[f"{kind}.j2"])
        self.assertEqual(after_registry["Record"]["fields"][0].pop("validators"), ["application_rules.check"])
        self.assertEqual(before_registry, after_registry)
        self.assertNotIn("_arca_custom_validators", before["schema.j2"])
        with rules(check=identity):
            ns, _, _ = schemas(["validators:str:validator=application_rules.check", "inspect:str:validator=application_rules.check"])
            self.assertEqual(ns["RecordCreate"](validators="ok", inspect="ok").validators, "ok")
            ns, _, _ = schemas([r"value:str:default='a:validator=literal':validator=application_rules.check:regex=^a:validator=literal$"])
            self.assertEqual(ns["RecordCreate"]().value, "a:validator=literal")

    def test_generation_never_imports_or_executes_custom_rules(self):
        original_import = builtins.__import__
        def forbid_rules(name, *args, **kwargs):
            if name.startswith("application_rules"):
                raise AssertionError("Application code imported during generation")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=forbid_rules):
            sources, _ = run_generation(["value:int:validator=application_rules.check"], use_cli=True)
        def forbid_tools(name, *args, **kwargs):
            if name.split(".")[0] in {"tools", "email_validator", "phonenumbers"}:
                raise AssertionError("Generator or optional dependency imported")
            return original_import(name, *args, **kwargs)
        with rules(check=identity), patch("builtins.__import__", side_effect=forbid_tools):
            ns = {"__name__": "standalone_custom_schema"}
            exec(compile(sources["schema.j2"], "<standalone-custom-schema>", "exec"), ns)
            self.assertEqual(ns["RecordCreate"](value=4).value, 4)

    def test_complete_example_and_qualified_modules(self):
        from tools.examples import validation_rules
        with modules({"validation_rules": validation_rules}):
            ns, _, _ = schemas(["quantity:int:validator=validation_rules.require_even", "slug:str:format=slug:validator=validation_rules.reject_reserved_slug"])
        self.assertEqual(ns["RecordCreate"](quantity=4, slug="my-shop").quantity, 4)
        for values in ({"quantity": 3, "slug": "my-shop"}, {"quantity": 4, "slug": "admin"}):
            with self.assertRaises(ValidationError):
                ns["RecordCreate"](**values)
        package = ModuleType("app_rules")
        package.__path__ = []
        module = ModuleType("app_rules.numbers")
        module.check = identity
        with modules({"app_rules": package, "app_rules.numbers": module}):
            ns, _, _ = schemas(["quantity:int:validator=app_rules.numbers.check"])
        self.assertEqual(ns["RecordCreate"](quantity="4").quantity, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
