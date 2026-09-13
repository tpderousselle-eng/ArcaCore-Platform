"""Immutable Gaming Studio production intent; no lifecycle execution authority.

The digest pins the verbatim UTF-8 text between the approval block delimiters,
excluding delimiter-separating blank lines. Internal CRLF bytes are preserved.
Changing both a document and its claimed digest cannot replace this trust root.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


INTENT_SCHEMA = "arcadev.gaming_studio.production_intent"
INTENT_SCHEMA_VERSION = 1
APPROVED_INTENT_DIGEST = "352bd37d4ed3458030a3893f60fc36da4d360f8d55a4a0b5190688a9871690e8"
APPROVAL_TEXT = "I approve"
MAX_AUTHORITY_BYTES = 100_000
AUTHORITY_DIRECTORY = Path(__file__).resolve().parents[1] / "authority" / "gaming_studio"


def canonical_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("Authority must be finite, valid Unicode JSON.") from error


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Authority contains duplicate JSON keys.")
        result[key] = value
    return result


def parse_authority(data: bytes) -> dict:
    """Bounded, strict canonical JSON reader shared by production records."""
    if not isinstance(data, bytes) or len(data) > MAX_AUTHORITY_BYTES:
        raise ValueError("Authority exceeds its byte limit or is not bytes.")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Authority is not valid UTF-8 JSON.") from error
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise ValueError("Authority JSON is not canonical.")
    return value


def read_authority(path: Path) -> bytes:
    """Read at most limit + 1 bytes; reject links and non-regular files."""
    path = Path(path)
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ValueError("Authority must be a regular file, not a link.")
    with path.open("rb") as stream:
        data = stream.read(MAX_AUTHORITY_BYTES + 1)
    if len(data) > MAX_AUTHORITY_BYTES:
        raise ValueError("Authority exceeds its byte limit.")
    return data


@dataclass(frozen=True)
class ProductionIntent:
    approved_intent: str

    @classmethod
    def from_bytes(cls, data: bytes) -> "ProductionIntent":
        value = parse_authority(data)
        keys = {"schema", "schema_version", "product_key", "product_display_name",
                "approved_intent", "approved_intent_sha256", "user_approval_text"}
        if set(value) != keys:
            raise ValueError("Production intent contains unknown or missing fields.")
        if value["schema"] != INTENT_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != INTENT_SCHEMA_VERSION:
            raise ValueError("Unsupported production intent schema/version.")
        if value["product_key"] != "gaming_studio" or value["product_display_name"] != "Gaming Studio":
            raise ValueError("Production product identity does not match.")
        if value["user_approval_text"] != APPROVAL_TEXT:
            raise ValueError("Production approval text does not match.")
        if not isinstance(value["approved_intent"], str):
            raise ValueError("Production intent must be text.")
        # An exact allowlist of approved bytes rejects *all* added secret material,
        # including credential formats that heuristic secret scanners miss.
        actual = digest_bytes(value["approved_intent"].encode("utf-8"))
        if actual != APPROVED_INTENT_DIGEST or value["approved_intent_sha256"] != actual:
            raise ValueError("Production intent digest does not match approved bytes.")
        return cls(value["approved_intent"])

    def canonical_bytes(self) -> bytes:
        result = canonical_bytes({
            "schema": INTENT_SCHEMA,
            "schema_version": INTENT_SCHEMA_VERSION,
            "product_key": "gaming_studio",
            "product_display_name": "Gaming Studio",
            "approved_intent": self.approved_intent,
            "approved_intent_sha256": APPROVED_INTENT_DIGEST,
            "user_approval_text": APPROVAL_TEXT,
        })
        # Also reject forged direct dataclass construction at serialization.
        self.from_bytes(result)
        return result


def load_production_intent(path: Path = AUTHORITY_DIRECTORY / "production_intent.json") -> ProductionIntent:
    return ProductionIntent.from_bytes(read_authority(path))
