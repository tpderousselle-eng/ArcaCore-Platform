import unittest

from tools.authorization import PolicyContract, PrincipalContext, authorize


class AuthorizationPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = PolicyContract.create({
            "editor": {"create", "read", "list", "own_update"},
            "manager": {"create", "read", "list", "update", "delete", "restore"},
            "viewer": {"read", "list"},
        }, denied_permissions={"delete"})
        self.viewer = PrincipalContext("user-a", "tenant-a", ("viewer",))

    def test_default_deny_unknown_missing_and_malformed(self):
        self.assertFalse(authorize(self.policy, self.viewer, "execute"))
        self.assertFalse(authorize(self.policy, None, "read"))
        self.assertFalse(authorize(None, self.viewer, "read"))
        with self.assertRaises(PermissionError): PrincipalContext("u", "t", ("admin;drop",))

    def test_allowed_and_denied_actions(self):
        self.assertTrue(authorize(self.policy, self.viewer, "read"))
        self.assertFalse(authorize(self.policy, self.viewer, "update"))
        manager = PrincipalContext("m", "tenant-a", ("manager",))
        self.assertTrue(authorize(self.policy, manager, "update"))
        self.assertFalse(authorize(self.policy, manager, "delete"))

    def test_tenant_and_role_spoofing_fail_closed(self):
        self.assertFalse(authorize(self.policy, self.viewer, "read", resource_tenant_id="tenant-b"))
        forged = PrincipalContext("u", "tenant-a", ("unknown",))
        self.assertFalse(authorize(self.policy, forged, "read"))

    def test_ownership_never_bypasses_tenant_or_explicit_deny(self):
        editor = PrincipalContext("owner", "tenant-a", ("editor",))
        self.assertTrue(authorize(self.policy, editor, "update", resource_tenant_id="tenant-a", owner_id="owner"))
        self.assertFalse(authorize(self.policy, editor, "update", resource_tenant_id="tenant-b", owner_id="owner"))

    def test_policy_round_trip_is_deterministic_and_forgery_rejected(self):
        copy = PolicyContract.from_dict(self.policy.canonical_dict())
        self.assertEqual(copy.digest, self.policy.digest)
        value = self.policy.canonical_dict(); value["extra"] = True
        with self.assertRaises(ValueError): PolicyContract.from_dict(value)

    def test_duplicate_and_malformed_definitions_rejected(self):
        for roles in ({"Bad": {"read"}}, {"viewer": {"read;exec"}}, {"viewer": "read"}):
            with self.subTest(roles=roles), self.assertRaises(ValueError): PolicyContract.create(roles)


if __name__ == "__main__": unittest.main()
