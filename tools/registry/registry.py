import json
from pathlib import Path

from tools.core.engine import PROJECT_ROOT
from tools.core.module_definition import ModuleDefinition


REGISTRY_PATH = (
    PROJECT_ROOT
    / "tools"
    / "registry"
    / "models.json"
)


class Registry:
    @staticmethod
    def load() -> dict:
        if not REGISTRY_PATH.exists():
            return {}
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save(data: dict):
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def register(module: ModuleDefinition):
        registry = Registry.load()
        registry[module.class_name] = {
            "table": module.table_name,
            "fields": [],
        }

        for field in module.fields:
            registry[module.class_name]["fields"].append(
                {
                    "name": field.name,
                    "python_type": field.python_type,
                    "sqlalchemy_type": field.sqlalchemy_type,
                    "nullable": field.nullable,
                    "unique": field.unique,
                    "index": field.index,
                    "default": field.default,
                    "foreign_key": field.foreign_key,
                    "relationship_name": field.relationship_name,
                    "relationship_class": field.relationship_class,
                    "relationship_type": field.relationship_type,
                    "back_populates": field.back_populates,
                    "backref": field.backref,
                    "association_table": field.association_table,
                    "relationship_table": field.relationship_table,
                    "relationship_key": field.relationship_key,
                }
            )

        Registry.save(registry)
