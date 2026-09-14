# Gaming Studio production PLAN resolution

This batch records exactly three actual user-approved planning clarifications.
It does not approve the complete SoftwarePlan or authorize architecture, models,
backend/frontend implementation, production generation, or Sprint 32.
Future strategic expansion remains non-authoritative in
[the separate strategy register](GAMING_STUDIO_FUTURE_STRATEGY.md).

The original SoftwarePlan, unanswered review and historical checkpoint remain
byte-for-byte unchanged in `authority/gaming_studio/production_plan/`.
All new authority lives in its versioned `plan_resolution/` subdirectory.

## PLAN Resolution 1: explicit authority

The envelope schema is `arcadev.gaming_studio.plan_clarification_authorization`,
version 1. The nested public answer schema is `arcadev.plan_clarification_answer`,
version 1. `arcadev/gaming_studio_plan_resolution.py` contains a fixed production
mapping of the supplied question, referent, exact response and accepted values.
It does not parse arbitrary approval messages. Each answer and envelope approval
has `explicit_user` provenance; evidence quotes the complete unchanged response.

`clarification_authorization.json` retains all referent text and normalized
accepted values, ordinal, question ID/text, proposal SHA-256, relationship and
both sides of each finalization binding. For publishing, the referent is the
user-supplied approved interpretation, not an invented preceding recommendation.
The entire canonical envelope is pinned to SHA-256
`360fb151709a031f49109726f2c3f3b73c4d0c13364baadf2edf87f3b0a5562c`.
Exact byte comparison against public-contract reconstruction also runs for valid
inputs. Unknown fields, duplicate keys, excessive bytes, secret additions,
fixture authority, rehashed proposals and stale IDs cannot introduce authority.

Answer order is storage/retention, build isolation, then publishing/release.
`PlanFinalization.start(plan, handoff=...)` starts with all three unresolved.
Each public `PlanClarificationAnswer` targets the current finalization; public
`resolve` computes the next identity before the next answer is constructed.

| State | PlanFinalization ID |
| --- | --- |
| Initial | `arcadev_plan_final_369adbc2e30f9e839416f5e39023099a` |
| After storage | `arcadev_plan_final_176bfa0c13ed2699e5acc21a9016055f` |
| After isolation | `arcadev_plan_final_f2536b26b828fcadc86789d9d7e86074` |
| After publishing | `arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2` |

The historical PLAN validator recognizes the separate local resolution directory
while continuing to validate only the three immutable historical PLAN files.
The current-resolution validator is introduced by increment 3.

Increment 1 changes this document, adds the resolution module, authorization JSON
and `tools/test_arcadev_gaming_studio_plan_resolution_1.py`, and extends
`arcadev/gaming_studio_plan.py` to recognize the separate resolution directory.
The dedicated tests cover exact authority, scope, tampering, sequential/stale and
duplicate resolution, and prohibit approval, architecture, generation, network,
process execution and writes during authority construction/validation.
