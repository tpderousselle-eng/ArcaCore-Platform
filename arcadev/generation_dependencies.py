"""Canonical dependency planning reconstructed from public parser metadata."""
from dataclasses import dataclass

from .architecture_specification import Record


@dataclass(frozen=True)
class GenerationDependency(Record):
    source_module_request_id: str
    target_module_request_id: str
    source_entity_id: str
    target_entity_id: str
    source_field_name: str
    target_field_name: str
    relationship_type: str


@dataclass(frozen=True)
class GenerationDependencyPlan(Record):
    ordered_module_request_ids: tuple[str, ...]
    dependencies: tuple[GenerationDependency, ...]


def generation_dependency_plan(requests):
    from .arcacore_generation_request import module_definition
    definitions = {m.module_request_id: module_definition(m) for m in requests}
    if len(definitions) != len(requests):
        raise ValueError("Duplicate module request identities.")
    by_id = {m.module_request_id: m for m in requests}
    tables = {d.table_name: identity for identity, d in definitions.items()}
    if len(tables) != len(definitions):
        raise ValueError("Duplicate physical modules in dependency plan.")
    if any(len([f for f in d.fields if f.primary_key]) != 1 for d in definitions.values()):
        raise ValueError("Dependency planning requires explicit single module identities.")
    dependencies, prerequisites, reverse_names = [], {key: set() for key in definitions}, set()
    for identity, definition in definitions.items():
        for field in definition.fields:
            if not field.foreign_key and field.relationship_type != "many_to_many":
                continue
            table = field.relationship_table
            key = field.relationship_key or field.foreign_key.split(".")[1]
            target_id = tables.get(table)
            if target_id is None:
                raise ValueError("Missing exact module dependency: " + table)
            target = definitions[target_id]
            target_keys = [f for f in target.fields if f.primary_key]
            if len(target_keys) != 1 or target_keys[0].name != key or field.relationship_class != target.class_name:
                raise ValueError("Relationship must reference the exact generated class and single primary key.")
            if field.relationship_type != "many_to_many" and field.python_type != target_keys[0].python_type:
                raise ValueError("Foreign key and target identity types differ.")
            if not field.backref:
                raise ValueError("A bare foreign key lacks a certified complete reverse relationship.")
            reverse = (target_id, field.backref)
            if field.backref in {"metadata", "registry", "created_at", "updated_at"} or reverse in reverse_names or any(f.name == field.backref or f.relationship_name == field.backref for f in target.fields):
                raise ValueError("Reverse relationship names collide.")
            reverse_names.add(reverse)
            if identity == target_id:
                if field.relationship_type != "self_many_to_one":
                    raise ValueError("Uncertified self dependency.")
                # The public adjacency-list contract validates its own key and
                # remote_side. It does not create a module-order cycle.
            else:
                prerequisites[identity].add(target_id)
            dependencies.append(GenerationDependency(identity, target_id, by_id[identity].entity_id,
                by_id[target_id].entity_id, field.name, key, field.relationship_type))
    ordered = []
    pending = set(definitions)
    while pending:
        ready = sorted((key for key in pending if not (prerequisites[key] & pending)),
            key=lambda key: (definitions[key].module_name, key))
        if not ready:
            raise ValueError("Module dependency cycles are not certified.")
        ordered.extend(ready)
        pending.difference_update(ready)
    return GenerationDependencyPlan(tuple(ordered), tuple(sorted(dependencies, key=lambda d: d.canonical_json())))
