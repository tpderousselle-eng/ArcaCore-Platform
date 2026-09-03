# Sprint 23.2: Encrypted fields

## Purpose

Encrypted fields protect selected string values at rest while preserving ordinary
plaintext strings in generated SQLAlchemy models and Pydantic schemas. Encryption
and decryption happen in a generated SQLAlchemy TypeDecorator. The database stores
only authenticated, versioned ciphertext.

This feature protects database contents and raw backups. It does not mask values in
API responses, logs, traces, or application memory, and it does not replace endpoint
authorization or secret management.

## DSL

| Declaration | Result |
| --- | --- |
| `secret:str:encrypted` | Uses `ARCACORE_ENCRYPTION_KEYS` |
| `notes:text:encrypted=NOTES_KEYRING` | Uses the named environment variable |
| `secret:str:nullable:encrypted` | Allows `None` without creating ciphertext |
| `secret:str:length=200:encrypted` | Validates plaintext length in schemas |
| `secret:str:encrypted:validator=rules.clean` | Runs the existing schema validator on plaintext |

`encrypted` supports `str` and `text` fields only. A custom environment name must
start with an uppercase ASCII letter and contain only uppercase ASCII letters,
digits, and underscores. The default name is `ARCACORE_ENCRYPTION_KEYS`.

Modifier order is flexible except that `regex=` remains the final literal modifier,
as in the existing field grammar. Duplicate encrypted modifiers and an empty or
invalid custom environment name fail before generation.

## Keys and rotation

The environment variable contains one or more comma-separated, URL-safe base64
encodings of exactly 32 random bytes. The first key is active for new writes. All
configured keys are tried during reads, which permits a deployment to read old data
while new writes move to a replacement key.

Generate a development key in PowerShell:

```powershell
$env:ARCACORE_ENCRYPTION_KEYS = python -c "import base64; from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print(base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode('ascii'))"
```

For rotation, place the new key first and retain the previous key after a comma until
all rows have been rewritten:

```powershell
$env:ARCACORE_ENCRYPTION_KEYS = "<new-base64-key>,<old-base64-key>"
```

Changing the keyring does not automatically rewrite existing rows. A migration or
application job must load and update each encrypted value before an old key can be
removed. Production keys should come from the deployment secret manager, never from
the DSL, generated source, registry, or version control.

## Storage format and authentication

Each non-null bind creates a fresh 12-byte nonce and encrypts UTF-8 plaintext with
AES-256-GCM. Stored values use this format:

```text
v1.<urlsafe-base64(nonce + ciphertext + authentication-tag)>
```

The generated type authenticates the `table.field` name as associated data. This
means tampering, a wrong key, or copying ciphertext into a different encrypted
column fails authentication instead of returning corrupted plaintext. Rewriting the
same plaintext produces a different token.

Malformed tokens, missing or malformed keyrings, wrong keys, and authentication
failures raise explicit runtime errors. Error messages identify the environment
variable but never include key material or plaintext.

## Model, schema, and registry behavior

The database column compiles to `TEXT` on SQLite and PostgreSQL. The ORM attribute
accepts and returns `str`; nullable fields also accept and return `None`. The
generated Create, Update, and Response schemas keep the normal plaintext type and
constraints. Their JSON Schema property includes `x-arca-encrypted: true`.

Length, minimum length, regex, named format, and custom validator rules operate on
plaintext in the schema layer. The encryption type does not enforce those schema
rules when an ORM model is constructed directly.

Registry metadata records only:

- `encrypted: true`
- `encryption_key_env: <environment-variable-name>`

The registry and generated source never contain the key value.

## Deliberate restrictions

AES-GCM encryption is randomized, so encrypted fields are not searchable by their
plaintext value. Generated model comparisons raise `TypeError`. An encrypted field
cannot be:

- a primary or foreign key, relationship, or delete-control field;
- unique, directly indexed, or defaulted;
- a computed or hybrid field;
- referenced by a computed or hybrid expression;
- included in `index()`, `partial_index()`, `expression_index()`,
  `unique_together()`, or `check()`.

These restrictions prevent the generator from implying database behavior that
randomized ciphertext cannot provide. This increment does not implement blind
indexes, deterministic encryption, key-provider plugins, automatic migrations, or
automatic key rotation jobs.

## Dependency

Generated encrypted models require `cryptography`. Install the bounded dependency
for this feature with:

```powershell
python -m pip install -r tools\requirements-encryption.txt
```

Plain generated models do not import `cryptography`, so projects without encrypted
fields retain their existing runtime dependency behavior.

## Local verification

From `C:\Projects\ArcaCore`, run:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone tools.test_slug tools.test_url tools.test_custom_validators tools.test_hybrid_properties tools.test_encrypted_fields -v
```

Expected: 226 tests, `OK`.

Normal discovery should report 227 tests:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

The 14 encrypted-field tests cover randomized database round trips, updates,
Unicode and nullable values, plaintext schema validation, registry/CLI metadata,
missing and malformed keyrings, tamper/wrong-key/cross-column rejection, rotation,
query restrictions, SQLite execution, PostgreSQL DDL, invalid DSL, indexes and
constraints, computed/hybrid boundaries, direct generator preflight, soft-delete
composition, custom keys, and plain-model compatibility. Generated application
files and persistent databases are not written by the smoke suite.

## References

The implementation follows SQLAlchemy's documented TypeDecorator bind/result
processing contract:
[SQLAlchemy Custom Types](https://docs.sqlalchemy.org/en/20/core/custom_types.html).

Nonce size, authentication behavior, key size, and failure semantics follow the
cryptography AESGCM API:
[Cryptography AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/).
