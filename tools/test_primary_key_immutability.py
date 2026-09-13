"""Public module-generator identity contract required by approved ArcaDev models."""
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from tools.generate import generate_module
import tools.generate_model as model_generator
import tools.generate_schema as schema_generator
import tools.generate_crud as crud_generator
import tools.generate_service as service_generator
import tools.generate_router as router_generator
import tools.registry.registry as registry_module


class PrimaryKeyImmutabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix="arcacore-primary-key-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.schemas, cls.cruds = {}, {}
        cases = {
            "Explicit": ["identifier:str:pk", "title:str"],
            "Implicit": ["title:str"],
            "Composite": ["first:str:pk", "second:str:pk", "title:str"],
        }
        with ExitStack() as stack:
            for generator in (model_generator, schema_generator, crud_generator, service_generator, router_generator):
                stack.enter_context(patch.object(generator, "PROJECT_ROOT", cls.root))
            stack.enter_context(patch.object(registry_module, "REGISTRY_PATH", cls.root / "tools/registry/models.json"))
            stack.enter_context(redirect_stdout(StringIO()))
            for name, declarations in cases.items():
                generate_module(name, declarations)
        for name in cases:
            schema = types.ModuleType("generated_schema_" + name)
            exec(compile((cls.root / ("backend/app/schemas/" + name.lower() + ".py")).read_bytes(), "schema.py", "exec"), schema.__dict__)
            cls.schemas[name] = schema
            model = types.ModuleType("backend.app.models." + name.lower())
            setattr(model, name, Mock())
            crud = types.ModuleType("generated_crud_" + name)
            with patch.dict("sys.modules", {model.__name__: model}):
                exec(compile((cls.root / ("backend/app/crud/" + name.lower() + ".py")).read_bytes(), "crud.py", "exec"), crud.__dict__)
            cls.cruds[name] = crud

    def test_explicit_primary_key_rejected_by_schema(self):
        with self.assertRaises(ValidationError): self.schemas["Explicit"].ExplicitUpdate(identifier="new")

    def test_implicit_primary_key_rejected_by_schema(self):
        with self.assertRaises(ValidationError): self.schemas["Implicit"].ImplicitUpdate(id=2)

    def test_every_composite_primary_key_rejected_by_schema(self):
        for key in ("first", "second"):
            with self.assertRaises(ValidationError): self.schemas["Composite"].CompositeUpdate(**{key: "new"})

    def test_crud_rejects_primary_key_before_any_database_call(self):
        for name, keys in (("Explicit", ("identifier",)), ("Implicit", ("id",)), ("Composite", ("first", "second"))):
            db = Mock()
            crud = getattr(self.cruds[name], name + "CRUD")(db)
            for key in keys:
                with self.assertRaisesRegex(ValueError, "Primary key"):
                    crud.update("old", {key: "new"})
            self.assertFalse(db.mock_calls)

    def test_creation_retains_explicit_identity_and_normal_updates(self):
        self.assertEqual(self.schemas["Explicit"].ExplicitCreate(identifier="stable", title="old").identifier, "stable")
        self.assertEqual(self.schemas["Explicit"].ExplicitUpdate(title="new").model_dump(exclude_unset=True), {"title": "new"})
        db = Mock()
        crud = self.cruds["Explicit"].ExplicitCRUD(db)
        item = types.SimpleNamespace(identifier="stable", title="old")
        crud.get = Mock(return_value=item)
        self.assertIs(crud.update("stable", {"title": "new"}), item)
        self.assertEqual((item.identifier, item.title), ("stable", "new"))
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
