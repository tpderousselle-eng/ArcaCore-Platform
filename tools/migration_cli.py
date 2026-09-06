"""Review-first CLI for validated schema evolution and migration rendering."""

import argparse
import json
from pathlib import Path
import sys

from tools.alembic_migration import (
    MigrationPolicy, UnsafeMigrationError, generate_alembic_migration,
    migration_policy_from_dict, write_alembic_migration,
)
from tools.core.audit_field_parser import parse_audit_fields
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition, valid_public_identifier
from tools.core.version_column_parser import parse_version_column
from tools.schema_evolution import SafetyClassification, plan_schema_evolution


MAX_JSON_BYTES = 1_000_000


def _load_json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Input must be an existing bounded JSON file.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Input must contain valid UTF-8 JSON.") from error


def load_definition(path):
    value = _load_json(path)
    allowed = {"module", "fields", "indexes", "constraints", "soft_delete", "audit_fields", "version_column"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Schema JSON contains unsupported keys.")
    name = value.get("module")
    fields_raw = value.get("fields")
    indexes_raw = value.get("indexes", [])
    constraints_raw = value.get("constraints", [])
    if not valid_public_identifier(name):
        raise ValueError("Schema module must be a public ASCII identifier.")
    if not isinstance(fields_raw, list) or any(not isinstance(v, str) for v in fields_raw):
        raise ValueError("Schema fields must be a JSON string list.")
    if not isinstance(indexes_raw, list) or any(not isinstance(v, str) for v in indexes_raw):
        raise ValueError("Schema indexes must be a JSON string list.")
    if not isinstance(constraints_raw, list) or any(not isinstance(v, str) for v in constraints_raw):
        raise ValueError("Schema constraints must be a JSON string list.")
    soft_delete = value.get("soft_delete", False)
    version_value = value.get("version_column", False)
    audit_value = value.get("audit_fields", False)
    if type(soft_delete) is not bool or type(version_value) is not bool or type(audit_value) not in {bool, str}:
        raise ValueError("Schema feature flags have invalid types.")
    audit = None if audit_value is False else parse_audit_fields("audit_fields" if audit_value is True else audit_value)
    version = False if version_value is False else parse_version_column("version_column")
    fields = parse_fields(name, fields_raw)
    table = f"{name.lower()}s"
    indexes = parse_indexes(table, indexes_raw, fields, soft_delete, audit is not None, version)
    unique, checks = parse_constraints(table, constraints_raw, fields, soft_delete, audit is not None, version)
    return ModuleDefinition(
        name, name.capitalize(), name.lower(), table, fields,
        indexes=indexes, soft_delete=soft_delete, unique_constraints=unique,
        check_constraints=checks, audit_fields=audit, version_column=version,
    )


def load_policy(path):
    return MigrationPolicy() if path is None else migration_policy_from_dict(_load_json(path))


def _plan(args):
    return plan_schema_evolution(load_definition(args.old), load_definition(args.new))


def _human(plan, policy):
    lines = [f"Module: {plan.module}"]
    if plan.is_empty:
        return "\n".join((*lines, "No schema changes.", "Executable migration: no migration required")) + "\n"
    for change in plan.changes:
        policy_needed = change.safety != SafetyClassification.SAFE_ADDITIVE
        lines.extend((
            f"Change: {change.kind.value}",
            f"  target: {change.target}",
            f"  before: {json.dumps(change.before, sort_keys=True, separators=(',', ':'))}",
            f"  after: {json.dumps(change.after, sort_keys=True, separators=(',', ':'))}",
            f"  safety: {change.safety.value}",
            f"  policy required: {'yes' if policy_needed else 'no'}",
        ))
    try:
        generate_alembic_migration(plan, policy=policy)
    except (ValueError, UnsafeMigrationError) as error:
        lines.append(f"Executable migration: no ({error})")
    else:
        lines.append("Executable migration: yes")
    return "\n".join(lines) + "\n"


def _contained_directory(root_value, directory_value):
    root = Path(root_value).resolve()
    directory = Path(directory_value).resolve()
    try:
        directory.relative_to(root)
    except ValueError as error:
        raise ValueError("Output directory escapes the explicitly allowed root.") from error
    return directory


def build_parser():
    parser = argparse.ArgumentParser(prog="arcacore-migration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "plan", "validate", "render"):
        child = subparsers.add_parser(command)
        child.add_argument("--old", required=True)
        child.add_argument("--new", required=True)
        child.add_argument("--policy")
        if command == "render":
            child.add_argument("--output-root")
            child.add_argument("--output-dir")
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        plan = _plan(args)
        policy = load_policy(args.policy)
        if args.command == "inspect":
            sys.stdout.write(_human(plan, policy))
        elif args.command == "plan":
            sys.stdout.write(plan.canonical_json())
        elif args.command == "validate":
            if plan.is_empty:
                sys.stdout.write("No migration required.\n")
            else:
                migration = generate_alembic_migration(plan, policy=policy)
                sys.stdout.write(f"Migration valid: {migration.revision}\n")
        else:
            migration = generate_alembic_migration(plan, policy=policy)
            if (args.output_root is None) != (args.output_dir is None):
                raise ValueError("Both --output-root and --output-dir are required for file output.")
            if args.output_root is None:
                sys.stdout.write(migration.content)
            else:
                directory = _contained_directory(args.output_root, args.output_dir)
                output = directory / migration.filename
                if output.exists():
                    raise FileExistsError("Refusing to overwrite an existing migration file.")
                written = write_alembic_migration(directory, plan, policy=policy, overwrite=False)
                sys.stdout.write(str(written) + "\n")
        return 0
    except (ValueError, UnsafeMigrationError, OSError) as error:
        sys.stderr.write(f"Migration command failed: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
