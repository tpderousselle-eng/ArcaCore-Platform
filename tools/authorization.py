"""Deterministic, default-deny authorization policy primitives."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
SUPPORTED_ACTIONS = frozenset({"create", "read", "list", "update", "delete", "restore"})


def _name(value, label):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f"{label} must be a bounded lowercase ASCII identifier.")
    return value


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    permissions: tuple[str, ...]

    def __post_init__(self):
        _name(self.name, "Role")
        if (not isinstance(self.permissions, tuple) or not self.permissions
                or tuple(sorted(set(self.permissions))) != self.permissions):
            raise ValueError("Role permissions must be non-empty, unique, and sorted.")
        for value in self.permissions:
            _name(value, "Permission")

    def canonical_dict(self):
        return {"name": self.name, "permissions": list(self.permissions)}


@dataclass(frozen=True)
class PolicyContract:
    roles: tuple[RoleDefinition, ...]
    denied_permissions: tuple[str, ...] = ()

    def __post_init__(self):
        if (not isinstance(self.roles, tuple) or not self.roles
                or tuple(sorted(self.roles, key=lambda role: role.name)) != self.roles
                or len({role.name for role in self.roles}) != len(self.roles)
                or any(not isinstance(role, RoleDefinition) for role in self.roles)):
            raise ValueError("Policy roles must be non-empty, unique, and sorted.")
        if tuple(sorted(set(self.denied_permissions))) != self.denied_permissions:
            raise ValueError("Denied permissions must be unique and sorted.")
        for value in self.denied_permissions:
            _name(value, "Permission")

    @classmethod
    def create(cls, roles: dict[str, object], denied_permissions=()):
        if not isinstance(roles, dict):
            raise ValueError("Roles must be a mapping.")
        parsed = []
        for name, permissions in roles.items():
            if not isinstance(permissions, (tuple, list, set, frozenset)):
                raise ValueError("Role permissions must be a collection.")
            parsed.append(RoleDefinition(name, tuple(sorted(set(permissions)))))
        return cls(tuple(sorted(parsed, key=lambda role: role.name)), tuple(sorted(set(denied_permissions))))

    def canonical_dict(self):
        return {"roles": [role.canonical_dict() for role in self.roles],
                "denied_permissions": list(self.denied_permissions)}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"roles", "denied_permissions"}:
            raise ValueError("Policy metadata is malformed.")
        if not isinstance(value["roles"], list) or not isinstance(value["denied_permissions"], list):
            raise ValueError("Policy metadata is malformed.")
        roles = []
        for item in value["roles"]:
            if not isinstance(item, dict) or set(item) != {"name", "permissions"} or not isinstance(item["permissions"], list):
                raise ValueError("Role metadata is malformed.")
            roles.append(RoleDefinition(item["name"], tuple(item["permissions"])))
        return cls(tuple(roles), tuple(value["denied_permissions"]))

    @property
    def digest(self):
        raw = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class PrincipalContext:
    principal_id: object
    tenant_id: object
    roles: tuple[str, ...]

    def __post_init__(self):
        if self.principal_id is None or self.tenant_id is None:
            raise PermissionError("Authenticated principal and tenant context are required.")
        if not isinstance(self.roles, tuple) or tuple(sorted(set(self.roles))) != self.roles:
            raise PermissionError("Trusted role context is malformed.")
        try:
            for role in self.roles: _name(role, "Role")
        except ValueError as error:
            raise PermissionError("Trusted role context is malformed.") from error


def authorize(policy: PolicyContract, principal: PrincipalContext, action: str,
              *, resource_tenant_id=None, owner_id=None) -> bool:
    """Return a decision. Unknown, missing, cross-tenant, and explicit deny all deny."""
    if not isinstance(policy, PolicyContract) or not isinstance(principal, PrincipalContext):
        return False
    if action not in SUPPORTED_ACTIONS:
        return False
    if resource_tenant_id is not None and resource_tenant_id != principal.tenant_id:
        return False
    permissions = set()
    by_name = {role.name: role for role in policy.roles}
    for role_name in principal.roles:
        role = by_name.get(role_name)
        if role is None:
            return False
        permissions.update(role.permissions)
    candidates = {action}
    if owner_id == principal.principal_id:
        candidates.add(f"own_{action}")
    if candidates & set(policy.denied_permissions):
        return False
    return bool(candidates & permissions)
