"""Validated, deterministic multitenancy contracts used by generated applications."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,62}\Z")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a bounded ASCII identifier.")
    return value


@dataclass(frozen=True)
class TenantContract:
    """Canonical declaration for an explicitly tenant-scoped module."""

    key: str = "tenant_id"
    python_type: str = "str"

    def __post_init__(self):
        _identifier(self.key, "Tenant key")
        if self.python_type not in {"str", "int", "uuid"}:
            raise ValueError("Tenant key type must be str, int, or uuid.")

    def canonical_dict(self) -> dict:
        return {"key": self.key, "python_type": self.python_type}

    @property
    def digest(self) -> str:
        raw = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()

    @classmethod
    def from_dict(cls, value: dict):
        if not isinstance(value, dict) or set(value) != {"key", "python_type"}:
            raise ValueError("Tenant contract is malformed.")
        return cls(**value)


@dataclass(frozen=True)
class TenantContext:
    """Server-established tenant identity; never construct from request payloads."""

    tenant_id: object

    def __post_init__(self):
        if self.tenant_id is None or isinstance(self.tenant_id, bool):
            raise PermissionError("Trusted tenant context is required.")
        if isinstance(self.tenant_id, str) and (not self.tenant_id or len(self.tenant_id) > 255):
            raise PermissionError("Trusted tenant context is invalid.")


def trusted_tenant_id(context: TenantContext):
    if not isinstance(context, TenantContext):
        raise PermissionError("Trusted tenant context is required.")
    return context.tenant_id


def reject_tenant_spoofing(values: dict, key: str = "tenant_id") -> dict:
    if not isinstance(values, dict):
        raise ValueError("Record values must be a mapping.")
    if key in values:
        raise ValueError("Tenant ownership is assigned by the trusted server context.")
    return dict(values)


def tenant_unique_columns(columns, contract: TenantContract, *, global_scope=False):
    """Return canonical database uniqueness columns without weakening global rules."""
    values = tuple(columns)
    if not values or any(not isinstance(item, str) for item in values):
        raise ValueError("Unique columns are invalid.")
    if global_scope:
        return values
    return values if contract.key in values else (contract.key, *values)
