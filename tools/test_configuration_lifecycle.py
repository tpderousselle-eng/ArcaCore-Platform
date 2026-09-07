import json
import unittest

from tools.configuration_lifecycle import (ConfigurationField, ConfigurationType,
    EnvironmentContract, SecretReference, SecretValue, resolve_environment)


class ConfigurationLifecycleTest(unittest.TestCase):
    def contract(self, name="production"):
        return EnvironmentContract.create(name, (
            ConfigurationField("API_URL", ConfigurationType.URL),
            ConfigurationField("DEBUG", ConfigurationType.BOOLEAN),
            ConfigurationField("POOL_SIZE", ConfigurationType.INTEGER),
            ConfigurationField("DATABASE_PASSWORD", ConfigurationType.STRING,
                secret=SecretReference("DATABASE_PASSWORD", "kubernetes/database-password", "v2")),
        ))

    def test_typed_values_and_runtime_secret_resolution(self):
        result = resolve_environment(self.contract(), {"API_URL": "https://example.test",
            "DEBUG": "false", "POOL_SIZE": "5", "DATABASE_PASSWORD": "super-secret-value"})
        self.assertEqual(result["POOL_SIZE"], 5); self.assertFalse(result["DEBUG"])
        self.assertIsInstance(result["DATABASE_PASSWORD"], SecretValue)
        self.assertEqual(result["DATABASE_PASSWORD"].reveal(), "super-secret-value")

    def test_missing_and_invalid_values_fail_closed_and_redacted(self):
        with self.assertRaises(ValueError) as caught:
            resolve_environment(self.contract(), {"API_URL": "bad", "DEBUG": "yes", "POOL_SIZE": "x"})
        self.assertNotIn("super-secret-value", str(caught.exception))

    def test_secret_values_never_enter_metadata_identity_or_repr(self):
        contract = self.contract(); raw = json.dumps(contract.canonical_dict(), sort_keys=True)
        self.assertNotIn("super-secret-value", raw + contract.digest)
        secret = SecretValue("super-secret-value")
        self.assertNotIn("super-secret-value", repr(secret) + str(secret))

    def test_environment_separation_has_no_fallback(self):
        production = self.contract("production"); staging = self.contract("staging")
        self.assertNotEqual(production.digest, staging.digest)
        with self.assertRaises(ValueError): resolve_environment(production, {})

    def test_malformed_names_references_duplicates_and_urls_rejected(self):
        for name in ("../prod", "Prod!", "a" * 64):
            with self.subTest(name=name), self.assertRaises(ValueError): EnvironmentContract.create(name, ())
        with self.assertRaises(ValueError): SecretReference("bad-name", "ref")
        field = ConfigurationField("VALUE", ConfigurationType.STRING)
        with self.assertRaises(ValueError): EnvironmentContract("test", (field, field))
        with self.assertRaises(ValueError): resolve_environment(
            EnvironmentContract.create("test", (ConfigurationField("URL", ConfigurationType.URL),)),
            {"URL": "file:///secret"})

    def test_environment_noise_does_not_change_identity(self):
        self.assertEqual(self.contract().digest, self.contract().digest)


if __name__ == "__main__": unittest.main()
