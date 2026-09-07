"""Canonical environment configuration and secret-reference lifecycle."""

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit


_ENVIRONMENT = re.compile(r"[a-z][a-z0-9_-]{0,62}\Z")
_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}\Z")


class ConfigurationType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    URL = "url"


def _match(pattern, value, label):
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value:
        raise ValueError(f"{label} is invalid.")
    return value


@dataclass(frozen=True)
class SecretReference:
    name: str
    provider_reference: str
    version: str | None = None

    def __post_init__(self):
        _match(_NAME, self.name, "Secret name")
        _match(_REFERENCE, self.provider_reference, "Secret provider reference")
        if self.version is not None: _match(_REFERENCE, self.version, "Secret version")

    def canonical_dict(self):
        return {"name": self.name, "provider_reference": self.provider_reference,
                "version": self.version}


@dataclass(frozen=True)
class ConfigurationField:
    name: str
    category: ConfigurationType
    required: bool = True
    secret: SecretReference | None = None
    enum_values: tuple[str, ...] = ()

    def __post_init__(self):
        _match(_NAME, self.name, "Configuration name")
        if not isinstance(self.category, ConfigurationType) or type(self.required) is not bool:
            raise ValueError("Configuration metadata is invalid.")
        if self.secret is not None and not isinstance(self.secret, SecretReference):
            raise ValueError("Secret metadata must be a reference, never a value.")
        if (not isinstance(self.enum_values, tuple)
                or tuple(sorted(set(self.enum_values))) != self.enum_values
                or any(not isinstance(v, str) or not v or len(v) > 128 for v in self.enum_values)):
            raise ValueError("Configuration enum is invalid.")

    def canonical_dict(self):
        return {"category": self.category.value, "enum_values": list(self.enum_values),
                "name": self.name, "required": self.required,
                "secret_reference": self.secret.canonical_dict() if self.secret else None}


@dataclass(frozen=True)
class EnvironmentContract:
    name: str
    fields: tuple[ConfigurationField, ...]

    def __post_init__(self):
        _match(_ENVIRONMENT, self.name, "Environment name")
        if (not isinstance(self.fields, tuple)
                or tuple(sorted(self.fields, key=lambda field: field.name)) != self.fields
                or len({field.name for field in self.fields}) != len(self.fields)
                or any(not isinstance(field, ConfigurationField) for field in self.fields)):
            raise ValueError("Configuration fields must be unique, sorted, and validated.")

    @classmethod
    def create(cls, name, fields):
        return cls(name, tuple(sorted(fields, key=lambda field: field.name)))

    def canonical_dict(self):
        return {"fields": [field.canonical_dict() for field in self.fields], "name": self.name}

    @property
    def digest(self):
        raw = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()


class SecretValue:
    """Ephemeral resolved value whose representation is always redacted."""
    __slots__ = ("_value",)

    def __init__(self, value):
        if not isinstance(value, str) or not value: raise ValueError("Resolved secret is unavailable.")
        self._value = value

    def reveal(self): return self._value
    def __repr__(self): return "SecretValue('[REDACTED]')"
    def __str__(self): return "[REDACTED]"


def _convert(field, value):
    if field.secret is not None: return SecretValue(value)
    if field.category == ConfigurationType.STRING:
        result = value if isinstance(value, str) else None
    elif field.category == ConfigurationType.INTEGER:
        try: result = int(value)
        except (TypeError, ValueError): result = None
        if isinstance(value, bool): result = None
    elif field.category == ConfigurationType.BOOLEAN:
        result = {"true": True, "false": False}.get(value.lower()) if isinstance(value, str) else None
    else:
        result = value if isinstance(value, str) else None
        try:
            parsed = urlsplit(result or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username is not None:
                result = None
        except ValueError: result = None
    if result is None or (field.enum_values and result not in field.enum_values):
        raise ValueError(f"Configuration {field.name} has an invalid value.")
    return result


def resolve_environment(contract: EnvironmentContract, values: dict):
    """Resolve exactly one explicit environment; no fallback or durable output."""
    if not isinstance(contract, EnvironmentContract) or not isinstance(values, dict):
        raise ValueError("Environment resolution input is invalid.")
    result = {}
    for field in contract.fields:
        if field.name not in values:
            if field.required: raise ValueError(f"Required configuration {field.name} is unavailable.")
            continue
        result[field.name] = _convert(field, values[field.name])
    return result
