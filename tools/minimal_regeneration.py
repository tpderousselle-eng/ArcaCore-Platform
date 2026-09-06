"""Schema-aware, content-addressed minimal-diff regeneration."""

import base64
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Mapping

from tools.core.engine import write_bytes_atomic, write_text_atomic, write_text_atomic_exclusive
from tools.schema_lifecycle import _digest


def _json(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
def _sha(content): return sha256(content).hexdigest()


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or len(value) > 240:
        raise ValueError("Generated path must be a bounded POSIX relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("Generated path escapes the project root.")
    if path.as_posix() != value:
        raise ValueError("Generated path is not canonical.")
    return path.as_posix()


def _content(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    if isinstance(value, bytes):
        if len(value) > 10_000_000: raise ValueError("Generated file content exceeds the safety limit.")
        return value
    raise ValueError("Generated content must be text or bytes.")


class OwnershipClass(str, Enum):
    GENERATOR_OWNED = "GENERATOR_OWNED"
    USER_OWNED = "USER_OWNED"
    CONFLICTED = "CONFLICTED"
    STALE_GENERATED = "STALE_GENERATED"


class RegenerationAction(str, Enum):
    CREATE = "create"
    REPLACE = "replace"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    CANDIDATE_REMOVAL = "candidate_removal"


@dataclass(frozen=True)
class OwnedFile:
    path: str
    generator: str
    content_digest: str
    input_digest: str
    ownership: OwnershipClass = OwnershipClass.GENERATOR_OWNED

    def canonical_dict(self): return {"path": self.path, "generator": self.generator,
        "content_digest": self.content_digest, "input_digest": self.input_digest,
        "ownership": self.ownership.value}


@dataclass(frozen=True)
class GenerationManifest:
    files: tuple[OwnedFile, ...]
    manifest_identity: str
    version: int = 1

    @classmethod
    def create(cls, files):
        files = tuple(sorted(files, key=lambda item: item.path))
        if any(not isinstance(v, OwnedFile) for v in files) or len({v.path for v in files}) != len(files):
            raise ValueError("Ownership manifest files are invalid or duplicated.")
        for item in files:
            _relative(item.path)
            if item.ownership != OwnershipClass.GENERATOR_OWNED:
                raise ValueError("Accepted manifest may contain only generator-owned files.")
            if not isinstance(item.generator, str) or not item.generator or len(item.generator) > 80:
                raise ValueError("Generator identity is invalid.")
            if len(item.content_digest) != 64 or len(item.input_digest) != 64:
                raise ValueError("Ownership digest is invalid.")
        body = {"version": 1, "files": [v.canonical_dict() for v in files]}
        return cls(files, _digest("arcacore-generation-manifest/v1", body))

    def canonical_dict(self): return {"version": self.version,
        "files": [v.canonical_dict() for v in self.files], "manifest_identity": self.manifest_identity}
    def canonical_json(self): return _json(self.canonical_dict())

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"version", "files", "manifest_identity"} or value["version"] != 1 or not isinstance(value["files"], list):
            raise ValueError("Generation manifest has an invalid shape.")
        files = []
        for row in value["files"]:
            if not isinstance(row, dict) or set(row) != {"path", "generator", "content_digest", "input_digest", "ownership"}:
                raise ValueError("Generation manifest entry is invalid.")
            try: ownership = OwnershipClass(row["ownership"])
            except (ValueError, TypeError) as error: raise ValueError("Generation ownership is invalid.") from error
            files.append(OwnedFile(row["path"], row["generator"], row["content_digest"], row["input_digest"], ownership))
        result = cls.create(files)
        if result.manifest_identity != value["manifest_identity"]:
            raise ValueError("Generation manifest identity mismatch.")
        return result


@dataclass(frozen=True)
class RegenerationOperation:
    path: str
    action: RegenerationAction
    old_digest: str | None
    new_digest: str | None
    ownership: OwnershipClass

    def canonical_dict(self): return {"path": self.path, "action": self.action.value,
        "old_digest": self.old_digest, "new_digest": self.new_digest,
        "ownership": self.ownership.value}


@dataclass(frozen=True)
class RegenerationPlan:
    operations: tuple[RegenerationOperation, ...]
    input_digest: str
    plan_identity: str
    version: int = 1

    @classmethod
    def create(cls, operations, input_digest):
        operations = tuple(sorted(operations, key=lambda v: (v.path, v.action.value)))
        body = {"version": 1, "input_digest": input_digest,
                "operations": [v.canonical_dict() for v in operations]}
        return cls(operations, input_digest, _digest("arcacore-regeneration-plan/v1", body))
    def canonical_dict(self): return {"version": self.version, "input_digest": self.input_digest,
        "operations": [v.canonical_dict() for v in self.operations], "plan_identity": self.plan_identity}
    def canonical_json(self): return _json(self.canonical_dict())


class MinimalRegenerator:
    def __init__(self, root: Path):
        self.root = Path(root).resolve(); self.meta = self.root / ".arcacore" / "generation"
        self.manifest_path = self.meta / "manifest.json"; self.journal_path = self.meta / "apply-journal.json"

    def _target(self, relative):
        relative = _relative(relative); raw = self.root / relative
        current = self.root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Generated path contains a symbolic link.")
        target = raw.resolve()
        try: target.relative_to(self.root)
        except ValueError as error: raise ValueError("Generated path escapes the project root.") from error
        return target

    def load_manifest(self):
        try:
            if self.manifest_path.stat().st_size > 5_000_000: raise ValueError("Generation manifest exceeds the safety limit.")
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError("Cannot load generation manifest.") from error
        return GenerationManifest.from_dict(value)

    def bootstrap(self, generated: Mapping[str, str | bytes], *, generator, input_digest):
        if self.manifest_path.exists(): raise ValueError("Generation manifest already exists.")
        files = []
        for path, value in sorted(generated.items()):
            content = _content(value); target = self._target(path)
            if not target.is_file() or target.read_bytes() != content:
                raise ValueError("Bootstrap content does not match project files.")
            files.append(OwnedFile(_relative(path), generator, _sha(content), input_digest))
        manifest = GenerationManifest.create(files)
        write_text_atomic_exclusive(self.manifest_path, manifest.canonical_json()); return manifest

    def plan(self, proposed: Mapping[str, str | bytes], *, generator, input_digest,
             user_owned=()):
        if not isinstance(proposed, Mapping) or not isinstance(input_digest, str) or len(input_digest) != 64:
            raise ValueError("Regeneration inputs are invalid.")
        if len(proposed) > 10_000:
            raise ValueError("Regeneration file count exceeds the safety limit.")
        prior = self.load_manifest(); old = {v.path: v for v in prior.files}
        new = {_relative(k): _content(v) for k, v in proposed.items()}
        if sum(map(len, new.values())) > 100_000_000:
            raise ValueError("Regeneration content exceeds the safety limit.")
        users = {_relative(v) for v in user_owned}; operations = []
        for path in sorted(old.keys() | new.keys()):
            target = self._target(path); current_digest = _sha(target.read_bytes()) if target.is_file() else None
            old_entry = old.get(path); new_digest = _sha(new[path]) if path in new else None
            if old_entry is None:
                if path in users or target.exists():
                    operations.append(RegenerationOperation(path, RegenerationAction.CONFLICT, current_digest, new_digest, OwnershipClass.USER_OWNED))
                else: operations.append(RegenerationOperation(path, RegenerationAction.CREATE, None, new_digest, OwnershipClass.GENERATOR_OWNED))
            elif current_digest != old_entry.content_digest:
                operations.append(RegenerationOperation(path, RegenerationAction.CONFLICT, current_digest, new_digest, OwnershipClass.CONFLICTED))
            elif path not in new:
                operations.append(RegenerationOperation(path, RegenerationAction.CANDIDATE_REMOVAL, current_digest, None, OwnershipClass.STALE_GENERATED))
            elif current_digest == new_digest:
                operations.append(RegenerationOperation(path, RegenerationAction.UNCHANGED, current_digest, new_digest, OwnershipClass.GENERATOR_OWNED))
            else: operations.append(RegenerationOperation(path, RegenerationAction.REPLACE, current_digest, new_digest, OwnershipClass.GENERATOR_OWNED))
        return RegenerationPlan.create(operations, input_digest)

    def validate(self, plan, proposed):
        if not isinstance(plan, RegenerationPlan): raise ValueError("Invalid regeneration plan.")
        contents = {_relative(k): _content(v) for k, v in proposed.items()}
        for op in plan.operations:
            self._target(op.path)
            if op.new_digest is not None and (op.path not in contents or _sha(contents[op.path]) != op.new_digest):
                raise ValueError("Regeneration content digest mismatch.")
            if op.action == RegenerationAction.CONFLICT:
                raise ValueError(f"Regeneration conflict: {op.path}")
        expected = RegenerationPlan.create(plan.operations, plan.input_digest)
        if expected.plan_identity != plan.plan_identity: raise ValueError("Regeneration plan identity mismatch.")
        return contents

    def _journal(self, plan, backups):
        body = {"version": 1, "plan_identity": plan.plan_identity,
                "backups": [{"path": op.path,
                             "content": None if backups[op.path] is None else base64.b64encode(backups[op.path]).decode("ascii"),
                             "new_digest": op.new_digest}
                            for op in plan.operations if op.path in backups]}
        value = dict(body); value["journal_digest"] = _digest("arcacore-regeneration-journal/v1", body)
        write_text_atomic(self.journal_path, _json(value))

    def _restore(self, backups):
        for path, content in sorted(backups.items(), reverse=True):
            target = self._target(path)
            if content is None: target.unlink(missing_ok=True)
            else: write_bytes_atomic(target, content)

    def apply(self, plan, proposed, *, generator, interrupt_after=None):
        contents = self.validate(plan, proposed)
        if not isinstance(generator, str) or not generator or len(generator) > 80:
            raise ValueError("Generator identity is invalid.")
        if interrupt_after is not None and (type(interrupt_after) is not int or interrupt_after < 1):
            raise ValueError("Interruption point is invalid.")
        mutable = [op for op in plan.operations if op.action in (RegenerationAction.CREATE, RegenerationAction.REPLACE, RegenerationAction.CANDIDATE_REMOVAL)]
        for op in mutable:
            target = self._target(op.path)
            current = _sha(target.read_bytes()) if target.is_file() else None
            if op.action == RegenerationAction.CREATE and current is not None:
                raise ValueError("A planned generated file was created externally.")
            if op.action != RegenerationAction.CREATE and current != op.old_digest:
                raise ValueError("A generated file changed after planning.")
        backups = {op.path: (self._target(op.path).read_bytes() if self._target(op.path).is_file() else None) for op in mutable}
        self._journal(plan, backups)
        try:
            for number, op in enumerate(mutable, 1):
                target = self._target(op.path)
                if op.action == RegenerationAction.CANDIDATE_REMOVAL:
                    if not target.is_file() or _sha(target.read_bytes()) != op.old_digest:
                        raise ValueError("Stale generated file changed before deletion.")
                    target.unlink()
                else: write_bytes_atomic(target, contents[op.path])
                if interrupt_after == number: raise InterruptedError("Simulated interrupted regeneration.")
        except InterruptedError: raise
        except Exception:
            self._restore(backups); self.journal_path.unlink(missing_ok=True); raise
        try:
            files = [OwnedFile(op.path, generator, op.new_digest, plan.input_digest)
                     for op in plan.operations if op.new_digest is not None and op.action != RegenerationAction.CONFLICT]
            manifest = GenerationManifest.create(files)
            write_text_atomic(self.manifest_path, manifest.canonical_json())
        except Exception:
            self._restore(backups); self.journal_path.unlink(missing_ok=True); raise
        self.journal_path.unlink(missing_ok=True); return manifest

    def status(self): return "RECOVERY_REQUIRED" if self.journal_path.exists() else "CLEAN"

    def recover(self):
        try:
            if self.journal_path.stat().st_size > 150_000_000: raise ValueError("Regeneration journal exceeds the safety limit.")
            value = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError("Regeneration journal is invalid.") from error
        if not isinstance(value, dict) or set(value) != {"version", "plan_identity", "backups", "journal_digest"} or value["version"] != 1:
            raise ValueError("Regeneration journal is invalid.")
        body = dict(value); digest = body.pop("journal_digest")
        if digest != _digest("arcacore-regeneration-journal/v1", body): raise ValueError("Regeneration journal digest mismatch.")
        backups = {}; expected = {}
        for row in value["backups"]:
            if not isinstance(row, dict) or set(row) != {"path", "content", "new_digest"}: raise ValueError("Regeneration backup is invalid.")
            path = _relative(row["path"]); content = row["content"]
            if row["new_digest"] is not None and (not isinstance(row["new_digest"], str) or len(row["new_digest"]) != 64):
                raise ValueError("Regeneration backup digest is invalid.")
            try: backups[path] = None if content is None else base64.b64decode(content, validate=True)
            except (ValueError, TypeError) as error: raise ValueError("Regeneration backup encoding is invalid.") from error
            expected[path] = row["new_digest"]
        for path, old in backups.items():
            target = self._target(path); current = _sha(target.read_bytes()) if target.is_file() else None
            old_digest = None if old is None else _sha(old)
            if current not in (old_digest, expected[path]):
                raise ValueError("Regeneration recovery conflict; file changed after interruption.")
        self._restore(backups); self.journal_path.unlink(); return "RESTORED"
