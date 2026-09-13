# Gaming Studio production authority

This is the first genuine Gaming Studio production authority. Earlier Gaming
Studio lifecycle objects and approvals in repository tests were **TEST FIXTURE
ONLY**. They are neither parents nor sources for this package.

## Approved intent root

`authority/gaming_studio/production_intent.json` is the authoritative verbatim
source, with schema `arcadev.gaming_studio.production_intent`, version 1. Its
`approved_intent` preserves the exact text from “Gaming Studio Production Intent”
through the final “later.” in the supplied approval block. Delimiter lines and
their separating blank lines are not part of the intent. Internal CRLF line
endings and Unicode punctuation are retained without normalization; the text
has 2,291 UTF-8 bytes and no terminal newline.

Intent SHA-256:
`352bd37d4ed3458030a3893f60fc36da4d360f8d55a4a0b5190688a9871690e8`.
The exact approval text is **I approve**.

The production loader pins that digest independently of the manifest. It rejects
modified text even when an attacker recomputes the claimed digest, altered
approval, unknown or missing fields, unsupported schema/version, duplicate keys,
noncanonical JSON, oversized records and invalid Unicode. Pinning the complete
approved bytes also rejects any added secret material. No timestamps or provider
metadata contribute to identity. Hash binding is an integrity check against the
repository trust root, not a digital signature or independent proof of who
supplied the approval.

Production code depends on no test helper. Validation reads bounded local files
and performs no network calls, child-process execution, application generation
or lifecycle transition. Dedicated tests are in
`tools/test_arcadev_gaming_studio_intent.py`.

The intent root grants no downstream lifecycle authority by itself.
