"""Stabilization 25.8 determinism and reproducibility contracts."""

from contextlib import ExitStack, redirect_stdout
from hashlib import sha256
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import generate as pipeline
from tools.core.compose_parser import ComposeDefinition
from tools.core.dockerfile_parser import DockerfileDefinition
from tools.core.kubernetes_parser import KubernetesDefinition
from tools.golden_matrix import GOLDEN_APPLICATIONS
import tools.generate_compose as compose_generator
import tools.generate_crud as crud_generator
import tools.generate_dockerfile as dockerfile_generator
import tools.generate_kubernetes as kubernetes_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
import tools.registry.registry as registry_module


MODULE_GENERATORS = (
    model_generator, schema_generator, crud_generator, service_generator,
    router_generator,
)

COMPLEX_MODULES = (
    ("User", ("email:str:format=email:length=254:unique",)),
    ("Role", ("name:str:length=80:unique",)),
    ("Record", (
        "owner_id:int:fk=users.id:one_to_many(User,records):cascade_delete:passive_deletes",
        "roles:many_to_many(Role)",
        "name:str:min_length=1:length=160:validator=rules.normalize",
        "state:enum(Open,Closed):default='Open'",
        "choice_value:choice(A,B):default='A'",
        "tags:array(str):default=list",
        "amount:decimal(12,2):min=0",
        "total:decimal(12,2):computed=amount * 2",
        "label:str:hybrid=name + '-record'",
        "secret:text:encrypted=RECORD_KEYS",
        "audit_fields(users.id,int)", "version_column", "soft_delete",
        "index(owner_id,state)",
        "partial_index(owner_id,where=deleted_at is None,unique=True)",
        "expression_index(lower(name),where=deleted_at is None)",
        "unique_together(owner_id,name)", "check(amount >= 0)",
    )),
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() != "backend/requirements.txt"
    }


def canonical_hash(files: dict[str, bytes]) -> str:
    digest = sha256()
    for name in sorted(files):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(files[name]).to_bytes(8, "big"))
        digest.update(files[name])
    return digest.hexdigest()


class DeterminismAndReproducibilityTest(unittest.TestCase):
    def generate(self, root: Path, modules=COMPLEX_MODULES, deployment=True):
        registry = root / "tools" / "registry" / "models.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        (root / "backend").mkdir(parents=True, exist_ok=True)
        (root / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        with ExitStack() as stack:
            for generator in MODULE_GENERATORS:
                stack.enter_context(patch.object(generator, "PROJECT_ROOT", root))
            stack.enter_context(patch.object(registry_module, "REGISTRY_PATH", registry))
            stack.enter_context(patch.object(dockerfile_generator, "PROJECT_ROOT", root))
            stack.enter_context(patch.object(compose_generator, "PROJECT_ROOT", root))
            stack.enter_context(patch.object(kubernetes_generator, "PROJECT_ROOT", root))
            stack.enter_context(redirect_stdout(StringIO()))
            for name, definitions in modules:
                pipeline.generate_module(name, list(definitions))
            if deployment:
                dockerfile_generator.generate_dockerfile(DockerfileDefinition())
                compose_generator.generate_compose(ComposeDefinition())
                kubernetes_generator.generate_kubernetes(KubernetesDefinition())
        return snapshot(root)

    def test_independent_roots_have_identical_paths_bytes_and_sha256(self):
        with TemporaryDirectory(prefix="arcacore-a-") as first, TemporaryDirectory(prefix="arcacore-b-") as second:
            left, right = self.generate(Path(first)), self.generate(Path(second))
        self.assertEqual(set(left), set(right))
        self.assertEqual(left, right)
        self.assertEqual(canonical_hash(left), canonical_hash(right))

    def test_unchanged_regeneration_is_byte_identical(self):
        with TemporaryDirectory(prefix="arcacore-regen-") as directory:
            root = Path(directory)
            first = self.generate(root)
            second = self.generate(root)
        self.assertEqual(second, first)
        self.assertEqual(canonical_hash(second), canonical_hash(first))

    def test_module_generation_order_does_not_change_any_artifact(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            left = self.generate(Path(first), COMPLEX_MODULES)
            right = self.generate(Path(second), tuple(reversed(COMPLEX_MODULES)))
        self.assertEqual(left, right)

    def test_equivalent_modifier_order_is_canonical(self):
        first = (("Record", ("name:str:min_length=2:length=80:unique", "amount:decimal(8,2):min=0:max=100")),)
        second = (("Record", ("name:str:unique:length=80:min_length=2", "amount:decimal(8,2):max=100:min=0")),)
        with TemporaryDirectory() as left_dir, TemporaryDirectory() as right_dir:
            left = self.generate(Path(left_dir), first, deployment=False)
            right = self.generate(Path(right_dir), second, deployment=False)
        self.assertEqual(left, right)

    def test_environment_and_temporary_path_do_not_affect_output(self):
        variants = (
            {"USER": "alice", "USERNAME": "alice", "COMPUTERNAME": "HOST_A", "UNRELATED": "one"},
            {"USER": "bob", "USERNAME": "bob", "COMPUTERNAME": "HOST_B", "UNRELATED": "two"},
        )
        outputs = []
        for environment in variants:
            with TemporaryDirectory(prefix=environment["USERNAME"] + "-") as directory, patch.dict(os.environ, environment, clear=False):
                generated = self.generate(Path(directory))
                joined = b"\n".join(generated.values())
                self.assertNotIn(str(Path(directory)).encode("utf-8"), joined)
                self.assertNotIn(environment["COMPUTERNAME"].encode("utf-8"), joined)
                outputs.append(generated)
        self.assertEqual(outputs[0], outputs[1])

    def test_golden_application_matrix_has_stable_sha256(self):
        for application in GOLDEN_APPLICATIONS:
            modules = tuple((module.name, module.fields) for module in application.modules)
            with self.subTest(application=application.name), TemporaryDirectory() as first, TemporaryDirectory() as second:
                left = self.generate(Path(first), modules, deployment=False)
                right = self.generate(Path(second), modules, deployment=False)
                self.assertEqual(canonical_hash(left), canonical_hash(right))
                self.assertEqual(left, right)

    def test_failed_regeneration_preserves_prior_deterministic_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            before = self.generate(root, deployment=False)
            with patch.object(pipeline, "generate_service", side_effect=RuntimeError("injected")):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    self.generate(root, (("Record", ("name:str:length=200",)),), deployment=False)
            after = snapshot(root)
        self.assertEqual(after, before)
        self.assertEqual(canonical_hash(after), canonical_hash(before))


if __name__ == "__main__":
    unittest.main(verbosity=2)
