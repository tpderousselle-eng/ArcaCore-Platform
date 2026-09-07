# ARCA CENTUM / ARCACORE / ARCAOS MASTER ROADMAP

**Updated:** September 6, 2026  
**Purpose:** Portable source of truth for continuing ArcaCentum, ArcaCore, ArcaOS, ArcaCentum.ai, ArcaCapitalis, and infrastructure-independence work across chats.

---

## 0. Core Project Rules

**Company / ecosystem:** ArcaCentum, Inc.

**Primary products:**
- ArcaCentum.ai
- ArcaCapitalis
- ArcaCentum Credit
- ArcaOS
- Future ArcaCommerce AI
- Future Workforce Operations Platform
- Future shared communications / SMS / email infrastructure

**Core infrastructure:** ArcaCore

**Repository:** `tpderousselle-eng/ArcaCore-Platform`  
**Local repository:** `C:\Projects\ArcaCore`

### Generator-first rule

Never manually fix generated repository `backend/` output.

If generated backend code fails:

`generated output fails → identify generator defect → fix tools/ → regenerate → retest`

Protected existing local state:
- ` D tools.zip`
- `?? .codex/`

Never stage or commit these.

GitHub is the long-term source of truth.

---

## 1. Stabilization 25 — COMPLETE

Completed:
- 25.1 Golden matrix
- 25.2 Generated runtime
- 25.3 PostgreSQL
- 25.4 Docker / Compose
- 25.5 Kubernetes / health
- 25.6 Failure injection
- 25.7 Security
- 25.8 Determinism
- 25.9 Release gate

Certified Stabilization 25 baseline:

`0480a5b347f2715b44b0955fae111a3985380933`

Final result:

```text
ARCCORE FUNCTIONAL RELEASE GATE: PASS
ARCCORE SECURITY PROMOTION GATE: PASS
ARCCORE RELEASE GATE: PASS
STABILIZATION 25: COMPLETE
```

---

## 2. Sprint 26 — Schema Evolution & Migration System — FULLY CERTIFIED

### 26.1 — COMPLETE
Commit: `ea2773fda105547dae67e00e8827fe83a3f118b2`

Deterministic schema evolution planning:
- immutable canonical evolution plans
- deterministic ordering
- fields
- types
- nullability
- defaults
- indexes
- constraints
- relationships
- foreign keys
- enums
- encrypted fields
- audit fields
- version columns
- soft delete

Classifications:
- `SAFE_ADDITIVE`
- `REQUIRES_DATA_MIGRATION`
- `POTENTIALLY_DESTRUCTIVE`
- `UNSUPPORTED`

### 26.2 — COMPLETE
Commit: `bdfc413722e6f7ce9cfd8eb0e988d838c8b72353`

Safe deterministic Alembic migration generation:
- deterministic revision IDs
- deterministic upgrade/downgrade
- `MigrationPolicy`
- safe types/defaults
- destructive operations fail closed
- migration provenance validation

### 26.3 — COMPLETE
Commit: `fabad0c7e0c28be851d2dc498392d5ccaa281447`

Real PostgreSQL migration validation:
- PostgreSQL upgrade
- downgrade
- re-upgrade
- data preservation
- indexes
- constraints
- foreign keys
- generated ORM read/write validation
- failure atomicity

### 26.4 — COMPLETE
Commit: `0a3a2ae2a5e1edc20da0cd5709f6016db4f51a70`

Reviewed data migration policies:
- `DataTransform`
- `BackfillPolicy`
- `DataAssertion`
- reviewed transforms
- literal/copy/lower/upper/trim
- row assertions
- null assertions
- uniqueness assertions
- nullable → backfill → verify → NOT NULL workflow

### 26.5 — COMPLETE
Commit: `000c8999ff731608f8c9c1b4e6c898f494885722`

Safe type and enum evolution:
- `TypeCompatibility`
- safe string widening
- bounded string → text
- safe decimal precision widening
- safe integer → decimal where valid
- append-only enum additions
- reject unsafe narrowing
- reject scale changes
- reject float → int
- reject text → bounded string
- reject UUID → string
- reject unsafe JSON/array transitions

### 26.6 — COMPLETE
Commit: `73d425375131b1b727ea5241dd19c25382b571e4`

Advanced index migrations + safe migration CLI:
- partial indexes
- expression indexes
- deterministic digest/name verification
- restricted expression grammar
- explicit index removal authorization
- bounded JSON policy grammar
- review-only migration CLI
- inspect
- plan
- validate
- render
- path containment
- atomic no-overwrite writes
- forged enum DB type rejection
- hostile input protection

Final Codex Security scan:
`c94bb3f6-253b-4fbb-984f-25e817061f3d`

Findings:
- Critical 0
- High 0
- Medium 0
- Low 0

Full discovery:
- 506 passed
- 1 expected Docker opt-in skip

26.4–26.6 were merged into `main`.

Current certified main:
`641899c13dc3ddf72cf82951316dbfe34ca86d91`

GitHub Security Promotion:
- Run `34120573734`
- Result: SUCCESS

Passed:
- unittest discovery
- security hardening
- generated runtime
- PostgreSQL
- Kubernetes
- failure injection
- determinism
- release-gate tests
- real Docker / Compose
- promotion evidence
- attestation

---

## 3. Sprint 26.7 — Schema State & Migration Lifecycle Integration

**Status:** COMPLETE
Commit: `3804914ccca3f8b024d87b09df5f5024ef60d7c5`

Goal:
Turn schema evolution into a native ArcaCore lifecycle.

Lifecycle:

`previous accepted schema → proposed schema → evolution plan → migration policy → migration artifact → pending revision → future controlled execution`

Delivered capabilities:
- canonical schema snapshots
- schema digest
- parent/predecessor lineage
- evolution plan digest
- migration revision identity
- policy digest
- lifecycle state
- reversibility metadata
- strict revision lineage
- root schema state
- drift detection
- migration manifest
- accepted vs pending state
- atomic registry/state behavior
- native generator integration

Important:
Generating a migration must **NOT** automatically make the new schema accepted.

Possible lifecycle states:
- `ACCEPTED`
- `PLANNED`
- `RENDERED`
- `PENDING_EXECUTION`

No production migration execution occurs implicitly.

Target commit message:
`Sprint 26.7 - Integrate schema migration lifecycle`

---

## 4. Sprint 26.8 — Controlled Migration Execution & Rollback

**Status:** COMPLETE
Commit: `c66e27b785a559cbf9d8278b2182f54596a4d55c`

Goal:
Safely execute previously validated migrations against PostgreSQL.

Delivered capabilities:
- migration preflight
- accepted schema verification
- DB revision verification
- migration manifest verification
- evolution plan digest verification
- policy digest verification
- predecessor lineage verification
- drift rejection
- PostgreSQL connectivity validation
- execution locking
- PostgreSQL advisory lock or equivalent
- transactional DDL where honestly supported
- explicit transaction capability
- crash recovery lifecycle
- execution journal
- database committed / state-finalization reconciliation
- explicit apply
- status
- rollback
- recover
- safe reversible rollback only
- real PostgreSQL failure injection
- lock contention tests
- timeout tests
- interrupted execution recovery

Important:
Normal generation must NEVER automatically apply production migrations.

Unsafe rollback must fail closed.

Security review required because this introduces a real DB execution boundary.

Target commit message:
`Sprint 26.8 - Add controlled migration execution and rollback`

---

## 5. Sprint 26.9 — Schema-Aware Minimal-Diff Regeneration

**Status:** COMPLETE
Commit: `29688dbe6733277a8e0665e0f6ba6d52f487598a`

Goal:
Stop blind regeneration.

ArcaCore should understand ownership and change only files that legitimately need changing.

Ownership classes such as:
- `GENERATOR_OWNED`
- `USER_OWNED`
- `CONFLICTED`
- `STALE_GENERATED`

Rules:
- generator-owned + untouched → may safely update
- generator-owned + user modified → conflict, DO NOT overwrite
- user-owned → never modify
- stale generated → remove only if provenance proves safe

Generation process:

`new generation → isolated staging root → compare old manifest → compare current project → compare proposed output → canonical minimal-diff plan → preview → controlled apply`

Plan operations:
- create
- replace
- unchanged
- conflict
- candidate removal

No arbitrary source merge guessing.
No silent user-code overwrites.
No recursive destructive deletion.
Atomic/recoverable multi-file apply.

Target commit message:
`Sprint 26.9 - Add schema-aware minimal-diff regeneration`

After 26.9:
**SPRINT 26 ENDS — FULLY CERTIFIED.**

Final validation:
- 543 tests passed
- 1 expected Docker opt-in skip
- Codex Security scan `c8ff16b8-a0da-42e0-80d5-4fdf9d3e56ae`
- GitHub Security Promotion run `34043018358`: SUCCESS

Do NOT allow Sprint 26 to expand indefinitely.

---

## 6. Current Codex Batch

Active engineering work:

`Sprint 27.1 → Sprint 27.2 → Sprint 27.3`

Intended feature branch:
`sprint-27-closed-loop-foundation`

Rules:
- branch from certified main
- one clean commit per sprint
- push feature branch only
- never unattended direct-main
- mandatory tests per increment
- full discovery
- PostgreSQL where applicable
- security
- determinism
- failure injection
- Docker only where relevant
- `backend/` untouched
- `tools.zip` untouched
- `.codex/` untouched

If mandatory gate fails:

```text
STOP
NO COMMIT
NO PUSH
DO NOT CONTINUE
```

After 26.9:
- Codex stops
- Tyler reviews
- feature branch may be fast-forwarded to main
- GitHub Security Promotion must pass before Sprint 27

---

## 7. Sprint 27 — Closed-Loop Autonomous Generation

Purpose:
Turn ArcaCore from a code generator into a system that can generate, run, observe failures, identify the responsible generator, repair, retry, and verify a complete application.

### 27.1 Canonical Project / Application Manifest
Track:
- project identity
- modules
- schema state
- runtime requirements
- infrastructure requirements
- generated surfaces
- dependency graph
- target platforms
- environment requirements

### 27.2 Closed-Loop Generated-App Runtime Harness
Validate:
- application boot
- API
- database
- generated tests
- health endpoints
- runtime dependencies
- container runtime where applicable

### 27.3 Failure Localization to Responsible Generator

`runtime/test failure → identify failing generated surface → map back to responsible generator/tool → produce structured diagnosis`

No manual backend repair.

### 27.4 Deterministic Retry & Recovery

`fix generator → regenerate affected surface → retry → compare → confirm deterministic recovery`

Prevent uncontrolled retry loops.

### 27.5 End-to-End Autonomous Build Orchestrator

`specification → architecture → schema → backend → tests → runtime → validation → regeneration → release candidate`

### 27.6 Runtime / Recovery Security Hardening
Protect against:
- hostile specs
- malicious generated paths
- arbitrary execution
- secret leakage
- infinite retry
- resource exhaustion
- unsafe shell behavior
- dependency abuse

Sprint 27 ends after 27.6.

---

## 8. Sprint 28 — Platform Primitives

### 28.1 Multitenancy
- organizations
- tenant isolation
- tenant-owned records
- tenant-aware queries
- tenant security

### 28.2 Generated RBAC / Policy Systems
- roles
- permissions
- policies
- generated authorization boundaries
- object/resource permissions

### 28.3 Secrets & Environment Configuration Lifecycle
- environment schemas
- secret references
- no secret generation into source
- dev/staging/prod separation
- validation
- rotation-ready architecture

### 28.4 Background & Scheduled Jobs
- queues
- worker model
- retries
- schedules
- job lifecycle
- failure handling
- idempotency

### 28.5 Events / Webhooks / Event Bus
- internal events
- external webhooks
- signed webhook delivery
- retry
- replay protection
- event schemas

### 28.6 File / Object Storage Primitives
- uploads
- metadata
- access policy
- object storage abstraction
- signed access
- file lifecycle

Sprint 28 ends after 28.6.

---

## 9. Sprint 29 — Production Intelligence

### 29.1 Structured Logging
- consistent event schema
- request correlation
- application identity
- tenant identity where appropriate
- safe redaction

### 29.2 Metrics & Traces
- performance metrics
- request traces
- database timing
- service dependencies
- health signals

### 29.3 Runtime Diagnostics & Health Intelligence
Understand:
- degraded dependencies
- DB state
- worker state
- queue health
- migration status
- configuration failures
- runtime readiness

### 29.4 Cost / Capacity / Resource Metadata
Track metadata for:
- CPU
- memory
- storage
- worker capacity
- AI usage
- infrastructure requirements
- operational cost signals

### 29.5 Plugin / Extension Hooks
Create controlled extension architecture without unsafe generator-core modification.

### 29.6 Stable Internal API / SDK
Create stable surfaces for:
- ArcaCentum.ai
- ArcaOS
- future ArcaCentum products

Sprint 29 ends after 29.6.

---

## 10. Sprint 30 — ArcaCore v1 Certification

Sprint 30 certifies what already exists rather than becoming another endless feature sprint.

### 30.1 Expanded Golden Application Matrix
Test representative generated apps including combinations of:
- field types
- relationships
- indexes
- validation
- encryption
- auditing
- versioning
- soft delete
- migrations
- multitenancy
- RBAC
- jobs
- events
- storage

### 30.2 Autonomous Generation / Regeneration Validation
Validate:
- clean generation
- schema evolution
- migrations
- minimal-diff regeneration
- user-owned code preservation
- failure recovery
- deterministic rebuild

### 30.3 Security / Hostile-Spec Audit
Red-team ArcaCore against:
- malicious DSL/specs
- path traversal
- arbitrary SQL
- arbitrary Python
- malicious defaults
- migration manipulation
- filesystem attacks
- command injection
- secret exposure
- denial-of-service inputs
- hostile plugin behavior

Blocking release condition:
- Critical 0
- High 0
- Exploitable Medium 0

### 30.4 PostgreSQL / Docker / Kubernetes Production Certification
Certify:
- PostgreSQL
- migrations
- persistence
- Docker
- Compose
- Kubernetes
- health/readiness
- restart behavior
- failure recovery
- determinism
- promotion evidence

### 30.5 ARCCORE V1 RELEASE GATE

Target result:

```text
ARCCORE FUNCTIONAL RELEASE GATE: PASS
ARCCORE SECURITY PROMOTION GATE: PASS
ARCCORE RELEASE GATE: PASS
ARCCORE V1: COMPLETE
```

After 30.5:
**ArcaCore v1 is certified.**

---

## 11. ArcaCentum.ai Architecture

ArcaCentum.ai is the flagship conversational application studio.

Vision:

`Describe an idea → AI understands product → architecture/specification → ArcaCore generation → backend → frontend → tests → security → preview → deployment → eventually mobile/app-store release`

Approved visual direction:
- premium dark
- blue/cyan/purple
- cosmic/orb artwork
- modern futuristic AI product identity

Approved headline:
**“Turn your ideas into native apps with intelligence.”**

Existing website includes:
- product capabilities
- Smart Discovery
- “Describe it. Watch it get built.”
- niche/market intelligence
- workflow/product sections
- FAQ
- CTA
- footer

Do NOT broadly redesign this site.
Improve functionality/integration instead.

---

## 12. ArcaCentum.ai Domain

`arcacentum.ai` is owned.

Connected from GoDaddy to Emergent using Domain Connect.

DNS values observed:
- A `@` → `162.159.142.117`
- A `@` → `172.66.2.113`
- CNAME `www` → `arcacentum.ai`

The real ArcaCentum.ai website began loading from the custom domain instead of the GoDaddy parked page.

Do not randomly alter DNS without verification.

---

## 13. Google OAuth — Must Fix Before Serious Launch

Current bad flow:

`ArcaCentum.ai → Continue with Google → auth.emergentagent.com → Emergent → “Grant Permission to Idea To App 116”`

Desired flow:

`ArcaCentum.ai → Continue with Google → Google OAuth → ArcaCentum → Studio / ArcaOS`

Requirements:
- ArcaCentum-owned Google OAuth application
- ArcaCentum branding
- owned authorized domains
- ArcaCentum support
- ArcaCentum privacy / terms
- owned client credentials
- remove Idea To App 116
- remove customer-facing Emergent branding

Prefer shared OAuth identity: **ArcaCentum**.

---

## 14. ArcaOS / Mission Control

ArcaOS already exists.

Architecture:

`ArcaCentum.ai login → Studio → Mission Control / ArcaOS`

**MISSION CONTROL V1 IS FROZEN.**

Do not rebuild it.
Do not redesign it.
Do not replace navigation.
Only genuine bug fixes unless Tyler explicitly approves a design change.

Existing Mission Control includes:
- Executive Dashboard
- Ask ArcaOS
- AI Attention
- Daily Brief
- Product Catalog
- Projects
- Project Bible
- Business Brief
- Decision Log
- Roadmap
- Milestones
- Search
- Prompt Library
- Notifications
- Members
- Activity

Dashboard intelligence includes:
- company health
- confidence
- AI confidence
- active products
- active projects
- decisions
- attention
- milestones
- blockers
- recommendations
- “What should I work on today?”
- AI Attention Center
- Product Health
- Roadmap
- Release Center
- Discovery Pipeline
- Knowledge Graph
- CEO Metrics
- Recent Activity

Future work should make the DATA and INTELLIGENCE behind this UI real.

Do not rebuild the shell.

---

## 15. ArcaOS Long-Term Role

ArcaOS should become the operating intelligence for ArcaCentum.

Long-term responsibilities:
- understand product state
- understand GitHub
- understand ArcaCore builds
- understand roadmaps
- understand milestones
- identify blockers
- summarize company state
- identify what Tyler should work on
- monitor product health
- understand business knowledge
- coordinate AI agents
- support executive decisions
- supervise builds
- eventually take approved actions

Architecture:

`ArcaOS → ArcaCore → ArcaCentum products → runtime / business / GitHub / communications / analytics`

---

## 16. ArcaOS Site Intelligence Agent — MUST BUILD

This is an explicit must-do feature.

It should eventually:
- audit ArcaCentum websites
- inspect product pages
- detect stale copy
- detect broken links
- detect incorrect product status
- inspect accessibility
- inspect SEO
- inspect responsiveness
- inspect performance
- identify outdated screenshots
- identify poor images
- recommend image replacements
- generate new images
- remove outdated page elements
- propose redesigned sections
- prepare GitHub branches
- generate before/after previews
- run tests
- request approval
- deploy approved safe changes

Operating modes:
1. OBSERVE
2. RECOMMEND
3. PREPARE
4. EXECUTE

Example future command:
“I don’t like the ArcaCentum Credit image. Create three alternatives.”

Expected flow:
`understand brand → generate options → prepare preview → Tyler selects → branch change → tests → merge/deploy`

---

## 17. Site Intelligence Safety / Governance

Frozen surfaces must be known by ArcaOS.

Examples:
- Mission Control v1 design
- approved ArcaCentum parent composition
- approved ArcaCentum.ai direction

Possible AUTO-FIX:
- broken internal links
- stale factual product status
- accessibility attributes
- metadata
- safe non-visual bugs
- safe performance problems

APPROVAL REQUIRED:
- redesign
- navigation
- deletion of public content
- major image replacement
- pricing
- legal content
- authentication
- major product positioning

ArcaOS must never have uncontrolled permission to randomly redesign products.

---

## 18. ArcaCentum Parent Website

`arcacentum.com` is the parent-company site.

Approved visual direction:
- cinematic cosmic design
- integrated orb
- Earth / world scale
- blue/purple energy
- premium dark environment

Approved hero:
**“Intelligence for a more human future.”**

Supporting positioning:
ArcaCentum is an AI technology company creating intelligent products that help people turn ideas into real-world software, businesses, and opportunities.

Parent website structure:
- hero
- company positioning
- portfolio
- accessibility / vision
- three product pillars
- company ecosystem structure
- company-stage positioning
- final CTA
- footer

Current public portfolio:
- ArcaCentum.ai
- ArcaCapitalis
- ArcaCentum Credit
- ArcaOS
- More products in development

Do not broadly redesign parent site.

---

## 19. ArcaOS Public Product Card

Approved public positioning:

**ArcaOS**

**AI OPERATING SYSTEM & MISSION CONTROL**

Description concept:
“The intelligence and operating layer for the ArcaCentum ecosystem — unifying projects, decisions, product health, AI attention, knowledge, roadmaps, and executive operations in one command center.”

Status:
`IN DEVELOPMENT · MISSION CONTROL V1`

ArcaOS card design is approved.

---

## 20. ArcaCapitalis — Existing Design Problem

The original ArcaCapitalis website looked too generic:
- brick-wall hero
- white content areas
- traditional navy footer
- generic consulting cards
- traditional corporate presentation

Content was acceptable.
Visual presentation was not strong enough for the ArcaCentum ecosystem.

---

## 21. ArcaCapitalis — Approved New Design Direction

Approved visual:
- lone person overlooking futuristic city
- glowing Arca intelligence orb
- cosmic sky
- blue/cyan/purple light
- warm futuristic horizon
- premium executive tone
- futuristic but grounded

Approved headline:

**BUILD FIRST. SCALE LAST.**

**Structure it.  
Build it.  
Scale it.**

Supporting copy:
ArcaCapitalis helps entrepreneurs and growing companies design stronger business foundations through strategic research, operational structuring, and growth planning.

Buttons:
- Explore Services
- Book a Consultation

Supporting phrase:
**STRATEGY • STRUCTURE • SUSTAINABILITY**

This is the approved ArcaCapitalis direction.

---

## 22. ArcaCapitalis — Entire Page Visual System

Important decision:
The approved ArcaCapitalis reference should influence the ENTIRE website, not only the hero.

BUT:
Do NOT literally use the entire mockup image as a giant webpage.

The reference is the VISUAL SOURCE OF TRUTH.

Implement:
- real HTML text
- real navigation
- real buttons
- real cards
- real responsive sections

Full-page flow:

`Hero → Method / Services → Economic Masonry → Deliverables / Engagement → Final CTA → Footer`

Visual behavior:
- Hero: highest cosmic intensity
- Method / Services: dark structural environment with restrained cosmic continuity
- Economic Masonry: architectural / layered intelligence focus
- Deliverables / Engagement: executive dark environment
- Final CTA: slightly stronger cosmic atmosphere again
- Footer: deep dark fade

NO large white sections.
NO generic corporate section breaks.
NO giant screenshot pasted above raw HTML.

---

## 23. ArcaCapitalis — Current Emergent Failure

Emergent initially implemented the redesign incorrectly.

It:
- pasted the entire visual mockup as a giant image
- duplicated navigation
- duplicated hero text
- duplicated hero CTAs
- placed raw page copy underneath
- used white background
- displayed nearly unstyled HTML
- used emoji-like service icons
- kept mismatched old footer

Do NOT publish that implementation.

A corrected REFERENCE-DRIVEN implementation prompt was prepared.

Core correction rule:
**Do not use the attached image itself as the website. Implement the design as a real responsive website.**

---

## 24. ArcaCapitalis — Approved Page Structure

### Hero
BUILD FIRST. SCALE LAST.

Structure it.  
Build it.  
Scale it.

### Build Before You Scale
Focus:
- research
- architecture
- operating processes
- documentation
- decision frameworks
- readiness planning

### ArcaCapitalis Method
01 Diagnose  
02 Structure  
03 Validate  
04 Build  
05 Prepare to Scale

Desktop: architectural/horizontal progression  
Mobile: vertical progression

### Core Services
- Strategic Research
- Business Architecture
- Operational Structuring
- Process & SOP Development
- Business Consulting
- Growth Readiness

Use premium dark/translucent cards.
No emoji icons.

### Signature Concept: ECONOMIC MASONRY

**Strong businesses are built layer by layer.**

Visual hierarchy:

```text
GROWTH
↑
VALIDATION
↑
OPERATIONS
↑
SYSTEMS
↑
STRUCTURE
↑
FOUNDATION
```

Core philosophy:

Build the foundation first.  
Reinforce each layer.  
Scale only when the structure can support it.

Economic Masonry is ArcaCapitalis’s principle that sustainable businesses are deliberately constructed, with each level reinforced before the next is added.

Foundation precedes expansion.  
Structure precedes scale.  
Planning precedes execution.

Economic Masonry should become a recognizable ArcaCapitalis methodology.

### Deliverables
- Business Blueprint
- Operating Model
- Market Research Brief
- Process Map
- SOP Package
- Organizational Structure
- Decision Framework
- Launch Readiness Plan
- Growth Readiness Assessment
- Business Systems Roadmap

Must say:
“Deliverables vary by engagement. Not every client receives every deliverable.”

### Engagement
**Built around the business, not a template.**

Preserve:
“Professional consulting engagements start at $750.”

“Consultation required prior to engagement.”

Do not create fake pricing tiers.

### ArcaCentum Relationship
Part of the ArcaCentum ecosystem.

ArcaCapitalis remains the primary identity.

### Final CTA
**Build something designed to last.**

---

## 25. ArcaCapitalis Design Rules

Use:
- deep navy / black
- restrained blue
- cyan
- violet
- premium typography
- dark translucent panels
- architecture
- blueprint
- structural motifs
- subtle stars
- restrained glow
- executive visual tone

Avoid:
- giant white sections
- generic Bootstrap cards
- fake dashboards
- fake testimonials
- fake logos
- fake metrics
- crypto/trading aesthetic
- generic corporate stock art
- excessive neon

All page text should remain visible without scroll-trigger animation.
Animation is enhancement only.

---

## 26. ArcaCentum Infrastructure Independence

This is a FORMAL long-term company milestone.

Goal:
Eventually detach production from Emergent.

Emergent should become OPTIONAL development tooling, not production infrastructure.

---

## 27. Infrastructure Independence Requirements

Final independence criteria:
- complete source code in ArcaCentum-controlled GitHub
- all assets owned by ArcaCentum
- ArcaCentum-owned Google OAuth
- ArcaCentum-owned databases
- ArcaCentum-owned API/model credentials
- own secrets management
- own CI/CD
- own hosting/cloud
- own storage
- own monitoring/logging
- own backups
- own domains/DNS
- ArcaOS can prepare changes
- ArcaCore can validate/build/deploy
- no production request requires Emergent

---

## 28. Emergent Detachment Strategy

Do NOT do a big-bang migration.

Gradual migration:
1. GitHub becomes source of truth
2. Complete app code exported/owned
3. Move OAuth credentials to ArcaCentum
4. Move third-party service accounts
5. Move database/data
6. Make apps independently runnable
7. Build owned CI/CD
8. Deploy parallel ArcaCentum environment
9. Validate production behavior
10. Switch DNS
11. Monitor
12. Retire Emergent dependency

Detaching from Emergent does NOT mean redesigning everything.

Preserve:
- Mission Control UI
- ArcaCentum parent site
- ArcaCentum.ai design
- approved ArcaCapitalis redesign

We are replacing the CONTROL PLANE beneath them.

---

## 29. Shared ArcaCore Service Layer

Potential future common services:
- ArcaIdentity
- ArcaAuth
- ArcaBilling
- ArcaMessaging
- ArcaEmail
- ArcaSMS
- ArcaStorage
- ArcaJobs
- ArcaEvents
- ArcaAudit
- ArcaNotifications
- ArcaAnalytics
- ArcaAI Gateway
- ArcaSecrets

Architecture:

```text
                 ArcaOS
                   │
        ┌──────────┼──────────┐
        │          │          │
 ArcaCentum.ai ArcaCapitalis Credit ...
        │          │          │
        └──────────┼──────────┘
                   │
                ArcaCore
                   │
         Shared Arca Services
```

---

## 30. Future ArcaCentum.ai Product Roadmap

After ArcaCore reaches required maturity, ArcaCentum.ai should gain:
- conversational product planning
- architecture generation
- specification generation
- ArcaCore orchestration
- frontend generation
- web application generation
- live preview
- staging environment
- production environment
- automated debugging
- recovery workflows
- schema visual management
- GitHub two-way sync
- integrations
- plugins
- team workflows
- approvals
- Flutter/mobile generation
- app-store publishing
- templates
- marketplace
- launch certification

Future user-facing build timeline:

`Idea → Plan → Architecture → Models → Backend → Frontend → Tests → Security → Preview → Deployment`

---

## 31. Mobile / App Store Future

Long-term ArcaCentum.ai capability:

`Build mobile app → compliance validation → package build → user-owned Apple developer account → user-owned Google Play account → submission assistance → submission status → rejection explanation/fix → resubmit`

Do not promise fully automatic acceptance from Apple or Google.

---

## 32. Shared Communications Future

### Two-way SMS
- branded transactional SMS
- alerts
- reminders
- missing-document requests
- verification requests
- reply by text
- workflow routing

### Unified communications inbox
- multiple email identities
- personal and business inbox connections
- understand which address received email
- reply from correct identity
- combine email + SMS
- shared ArcaCore messaging layer

---

## 33. ArcaCommerce AI

Future product: ArcaCommerce AI

Purpose:
AI-powered e-commerce research and launch platform.

Core capabilities:
- product opportunity research
- low-star review analysis
- product improvement concepts
- fee/margin calculations
- supplier comparison
- sample tracking
- launch checklists
- listing generation

Advanced tiers later:
- Amazon SP-API
- inventory
- restock forecasting
- ad analytics
- P&L dashboards
- supplier messaging
- freight/inspection
- multi-marketplace
- team accounts
- listing submission
- ArcaCentum Credit integration

Run on shared ArcaCore infrastructure.

---

## 34. Workforce Operations Product

Future ArcaCentum product.

Initial niche:
- security companies
- staffing companies

Capabilities:
- scheduling
- mobile time clock
- GPS/geofence
- offline clock-in
- shift swaps
- PTO
- missed-punch corrections
- payroll-ready timesheets
- labor dashboards
- notifications
- RBAC
- audit logs
- guard-card/certification alerts
- post orders
- incident reports
- patrol checkpoint scans

Also should run on shared ArcaCore infrastructure.

---

## 35. Long-Term Company Model

ArcaCentum should not become a collection of unrelated apps.

Long-term architecture:

- **ArcaCore** = shared technical foundation
- **ArcaOS** = company/product operating intelligence
- **ArcaCentum.ai** = AI software-building interface
- **ArcaCapitalis** = business architecture / strategic structuring
- **ArcaCentum Credit** = credit/funding readiness platform
- **Future products** = specialized applications using shared infrastructure

---

## 36. End-State Vision

Tyler describes a business/product goal to ArcaOS or ArcaCentum.ai.

ArcaOS understands:
- company context
- product context
- roadmap
- user intent
- design constraints
- frozen surfaces
- security policies

ArcaCore handles:
- schema
- code generation
- migrations
- regeneration
- runtime validation
- infrastructure
- tests
- security
- deployment

ArcaOS monitors:
- product health
- GitHub
- infrastructure
- analytics
- customer behavior
- business state

Then intelligence can recommend or prepare improvements.

Example:

`ArcaOS detects outdated page → recommends correction → prepares branch → generates/updates image if necessary → runs tests → shows preview → Tyler approves → CI/CD deploys → ArcaOS verifies production`

That is the future closed-loop ArcaCentum ecosystem.

---

## 37. Immediate Next Actions

### Engineering
1. Complete Sprint 27.1 canonical application manifest
2. Complete Sprint 27.2 closed-loop runtime harness
3. Complete Sprint 27.3 failure localization
4. Review branch
5. Do not begin Sprint 27.4 without explicit authorization

### Product / Design
1. Correct ArcaCapitalis Emergent implementation
2. Do NOT publish broken current preview
3. Use approved ArcaCapitalis image as reference-driven FULL-PAGE visual system
4. Real HTML/CSS, not giant screenshot
5. Review desktop + mobile before publishing
6. Preserve ArcaCentum.ai visual direction
7. Preserve parent-site visual direction
8. Preserve frozen Mission Control v1
9. Later replace Emergent OAuth branding
10. Begin planning Infrastructure Independence after ArcaCore reaches required maturity

---

## 38. Absolute Do-Not-Lose Decisions

- Sprint 26 ends at 26.9.
- Sprint 30.5 is ArcaCore v1 Release Gate.
- Mission Control v1 is already built and FROZEN.
- Do not rebuild ArcaOS UI.
- ArcaOS Site Intelligence Agent is a must-do.
- ArcaOS should eventually redesign/replace images, remove sections, and propose site changes through controlled approval workflows.
- ArcaCentum Infrastructure Independence is a formal must-do milestone.
- Emergent eventually becomes optional.
- GitHub should become source of truth.
- ArcaCore remains generator-first.
- Never manually patch generated `backend/`.
- ArcaCapitalis gets the new cosmic/futuristic executive design.
- “Structure it. Build it. Scale it.” is approved.
- “Build First. Scale Last.” remains core ArcaCapitalis philosophy.
- Economic Masonry should become a signature ArcaCapitalis methodology.
- ArcaCapitalis visual reference should influence the ENTIRE site, not just the hero.
- The reference image must NOT be used as one giant website screenshot.
- ArcaCentum parent site stays.
- ArcaCentum.ai visual identity stays.
- Google OAuth must eventually become ArcaCentum-owned and ArcaCentum-branded.
- All future ArcaCentum products should increasingly use shared ArcaCore infrastructure.

---

## Sprint 27 Feature-Branch Status

- Sprint 27.1 canonical application manifest: certified.
- Sprint 27.2 closed-loop runtime harness: certified.
- Sprint 27.3 failure localization: certified.
- Cross-platform runtime containment portability repair: certified.
- Sprint 27.4 deterministic retry and recovery workflow: certified.
- Sprint 27.5 autonomous build orchestrator: certified.
- Sprint 27.6 runtime and recovery security hardening: certified.
- Sprint 27 is fully certified on main at `641899c13dc3ddf72cf82951316dbfe34ca86d91` by GitHub Security Promotion run `34120573734` (SUCCESS).

## Sprint 28 Feature-Branch Status

- Sprint 28.1 native multitenancy primitives: complete locally.
- Sprint 28.2 generated RBAC and policy systems: complete locally.
- Sprint 28.3 secrets and environment configuration lifecycle: complete locally.
- Tenant-aware relationship integrity repair: complete locally.
- Sprint 28.4 background and scheduled jobs: complete locally.
- Sprint 28.5 events, webhooks, and event bus: complete locally.
- Sprint 28.6 file and object storage: complete locally.
- Sprint 28 is locally complete and awaiting merge, promotion, and certification.
- Sprint 29 has not started.
