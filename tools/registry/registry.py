import json
from pathlib import Path

from tools.core.audit_field_parser import validate_audit_fields
from tools.core.encrypted_field_parser import validate_encrypted_fields
from tools.core.engine import PROJECT_ROOT
from tools.core.module_definition import ModuleDefinition


REGISTRY_PATH = PROJECT_ROOT / "tools" / "registry" / "models.json"


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
        validate_audit_fields(module.audit_fields, module.fields)
        validate_encrypted_fields(module.fields)
        registry = Registry.load()
        registry[module.class_name] = {
            "table": module.table_name,
            "fields": [],
            "soft_delete": module.soft_delete,
            **(
                {
                    "audit_fields": {
                        "target": module.audit_fields.target,
                        "python_type": module.audit_fields.python_type,
                        "sqlalchemy_type": module.audit_fields.sqlalchemy_type,
                    }
                }
                if module.audit_fields is not None
                else {}
            ),
            "indexes": [
                {
                    "name": index.name,
                    "columns": index.columns,
                    **({"where": index.where, "unique": index.unique} if index.where is not None or index.expressions is not None else {}),
                    **({"expressions": index.expressions} if index.expressions is not None else {}),
                }
                for index in module.indexes
            ],
            "unique_constraints": [
                {"name": item.name, "columns": item.columns}
                for item in module.unique_constraints
            ],
            "check_constraints": [
                {"name": item.name, "expression": item.expression}
                for item in module.check_constraints
            ],
        }
        for field in module.fields:
            registry[module.class_name]["fields"].append({
                "name": field.name,
                "python_type": field.python_type,
                "sqlalchemy_type": field.sqlalchemy_type,
                "nullable": field.nullable,
                "unique": field.unique,
                "index": field.index,
                "default": field.default,
                "min": field.minimum,
                "max": field.maximum,
                "min_length": field.min_length,
                "max_length": field.max_length,
                "regex": field.pattern,
                **({"format": field.format} if field.format is not None else {}),
                **({"validators": list(field.validators)} if field.validators else {}),
                **(
                    {
                        "encrypted": True,
                        "encryption_key_env": field.encryption_key_env,
                    }
                    if field.encrypted
                    else {}
                ),
                "computed": field.computed_expression,
                "computed_sql": field.computed_sql,
                **(
                    {
                        "hybrid": field.hybrid_expression,
                        "hybrid_python": field.hybrid_python,
                        "hybrid_class": field.hybrid_class,
                        "hybrid_references": list(field.hybrid_references),
                    }
                    if field.hybrid_expression is not None
                    else {}
                ),
                "foreign_key": field.foreign_key,
                "relationship_name": field.relationship_name,
                "relationship_class": field.relationship_class,
                "relationship_type": field.relationship_type,
                "back_populates": field.back_populates,
                "backref": field.backref,
                "association_table": field.association_table,
                "relationship_table": field.relationship_table,
                "relationship_key": field.relationship_key,
                "cascade_delete": field.cascade_delete,
                "passive_deletes": field.passive_deletes,
            })
        Registry.save(registry)
