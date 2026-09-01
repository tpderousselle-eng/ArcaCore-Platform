from dataclasses import dataclass

from tools.core.field_parser import Field


@dataclass
class ModuleDefinition:
    name: str
    class_name: str
    module_name: str
    table_name: str
    fields: list[Field]