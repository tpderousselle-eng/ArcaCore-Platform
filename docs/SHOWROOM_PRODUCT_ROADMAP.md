# ArcaCentum Showroom Product Roadmap

**Status:** Product showcase / future commercial concept  
**Purpose:** Demonstrate how ArcaCentum + ArcaCore can modernize real operational workflows with production-grade software.

---

## Showroom Product 01 — ArcaCentum Warehouse Operations

**Working name:** ArcaCentum Warehouse Operations  
**Category:** Warehouse / Workforce Operations  
**Positioning:** A scanner-first operational workflow platform for warehouses that reduces unnecessary travel, paper-based indirect tracking, exception delays, and coordinator bottlenecks.

This should be built as an original ArcaCentum product concept. It must not copy BasicTE or any employer-owned software, proprietary screen, code, workflow implementation, or branding.

### Core Showroom Scenario

A warehouse worker encounters a missing unit while using an RF scanner.

Instead of physically driving back to a coordinator, the worker can select a scanner action such as:

`Missing Unit`

The system should automatically:
- capture worker identity
- capture scanner/device identity
- capture SKU/item
- capture warehouse location
- capture expected quantity
- timestamp the exception
- start the configured indirect activity code for the exception when appropriate
- notify the coordinator / inventory-control queue
- check for approved alternate inventory locations when integration data is available
- return the next safe instruction to the worker
- close the indirect activity when the exception is resolved
- preserve the complete audit trail

Example configurable activity codes from a real warehouse workflow:
- `98` — Break
- `99` — Lunch
- `64` — Missing Unit

These are examples only. **Activity codes must be customer-configurable and never hardcoded as universal values.**

---

## Scanner-Based Indirect Activity Tracking

Replace daily handwritten indirect forms with a scanner-native workflow.

The employee selects the activity by description instead of having to remember or manually write a code.

Required behavior:
- configurable Activity Code Catalog
- activity name + code
- automatic start timestamp
- automatic end timestamp
- calculated duration
- employee identity
- device identity
- shift / work assignment context
- optional warehouse zone/location
- reason / exception linkage
- immutable audit history
- correction workflow with supervisor authorization

### Persistent Current Activity Banner

The scanner should always show the worker's current active status, for example:

`MISSING UNIT (64) — 00:07:42`

The worker should be able to clearly see:
- current activity
- activity code
- elapsed time
- whether the activity is direct or indirect
- the safe action to end/resume work

This prevents forgotten activity codes, duplicate entries, and inaccurate end-of-shift paperwork.

---

## Inventory Exception Center

Initial exception types should include:
- Missing Unit
- Wrong Item in Location
- Empty Location
- Quantity Mismatch
- Damaged Unit
- Bad / Unreadable Barcode
- Blocked Location
- Cycle Count Requested
- Replenishment Needed
- Other configurable warehouse exception

Each exception should have:
- structured reason
- item/location context
- worker/device identity
- timestamps
- coordinator status
- resolution
- audit log
- optional linked indirect activity

---

## Coordinator / Inventory-Control Console

Coordinators should receive exceptions digitally instead of requiring the worker to return in person.

Capabilities:
- live exception queue
- priority / age of exception
- worker and current location
- item / SKU / location information
- quick responses
- assign alternate location
- request cycle count
- request replenishment
- mark issue resolved
- send instruction back to scanner
- escalation to inventory control or supervisor

Example quick responses:
- Continue to next task
- Check alternate location
- Cycle count requested
- Replenishment requested
- Proceed to problem solve
- Wait for coordinator

---

## RF / Barcode Scanner Support

The platform should support warehouse scanner workflows including:
- SKU / UPC / item scans
- carton scans
- pallet scans
- location / bin scans
- hardware scanner trigger input
- rugged Android devices where supported
- browser/PWA fallback where appropriate
- configurable scan validation
- duplicate-scan protection
- safe retry behavior

---

## Offline / Weak-Wi-Fi Operation

Warehouses can have dead zones.

Required design goals:
- local bounded transaction queue
- offline-safe activity start/end handling
- idempotent sync
- duplicate prevention
- deterministic conflict handling
- visible sync status
- no silent data loss

---

## Warehouse Workflow Engine

Future supported workflows may include:
- picking
- putaway
- receiving
- replenishment
- inventory moves
- cycle counts
- damages
- shortages / overages
- returns
- exception handling
- indirect labor activities
- task reassignment

---

## Workforce / Identity / Permissions

Use shared ArcaCore capabilities for:
- multitenancy
- employee identity
- device identity
- warehouse/site identity
- shift context
- RBAC
- supervisor permissions
- coordinator permissions
- inventory-control permissions
- admin permissions
- audit logs

Representative roles:
- Warehouse Associate
- Forklift Operator
- Coordinator
- Inventory Control
- Supervisor
- Operations Manager
- Administrator

---

## WMS / ERP Integration Layer

The product should be able to complement existing warehouse systems rather than requiring a company to replace everything at once.

Future adapter architecture may support approved integrations with:
- SAP
- Manhattan
- Oracle
- Blue Yonder
- customer-owned WMS systems
- approved APIs
- event/webhook integrations
- controlled flat-file / batch interfaces where necessary

No unauthorized scraping or reverse engineering of proprietary systems.

---

## Analytics / Management Intelligence

Supervisor dashboards should eventually show:
- direct vs indirect labor time
- indirect time by activity code
- missing-unit frequency
- missing-unit resolution time
- recurring problem locations
- recurring problem SKUs
- exception volume by shift / zone
- cycle-count requests
- replenishment delays
- coordinator response time
- worker travel / workflow bottlenecks where safely measurable
- inventory accuracy signals

### ArcaOS Intelligence Layer

Longer term, ArcaOS should be able to identify patterns such as:

`Location B-14 generated 11 missing-unit exceptions this week. Recommend cycle count / replenishment investigation.`

AI recommendations must remain advisory unless a safe, approved workflow explicitly allows execution.

---

## Safety Requirements

Warehouse safety is mandatory.

The product must not encourage scanner interaction while powered equipment is moving.

Design principles:
- scanner workflows assume the operator is safely stopped before interaction
- avoid distracting prompts while equipment is in motion
- clear confirmation for safety-sensitive actions
- no routing instruction should override facility safety rules
- customer-specific safety policy support

---

## ArcaCore Dependencies

This showroom product should intentionally demonstrate the value of shared ArcaCore infrastructure.

Key dependencies include:
- Sprint 28.1 — Multitenancy
- Sprint 28.2 — RBAC / policy generation
- Sprint 28.3 — Secrets / environment lifecycle
- Sprint 28.4 — Background / scheduled jobs
- Sprint 28.5 — Events / webhooks / event bus
- Sprint 28.6 — File / object storage where needed
- Sprint 29.1 — Structured logging
- Sprint 29.2 — Metrics / traces
- Sprint 29.3 — Runtime diagnostics
- Sprint 29.6 — Stable internal API / SDK

Shared services may include:
- ArcaIdentity
- ArcaAuth
- ArcaJobs
- ArcaEvents
- ArcaAudit
- ArcaNotifications
- ArcaAnalytics
- ArcaMessaging

---

## Showroom Demo Goal

The first public/internal showroom demo does not need a live customer WMS.

Build a controlled demonstration with:
- mock warehouse inventory
- mock locations
- mock SKUs
- mock workers / devices
- RF-scanner-style interface
- configurable indirect activity codes
- Missing Unit workflow
- coordinator dashboard
- real-time exception status
- alternate-location recommendation from demo inventory
- activity timing
- audit history
- management analytics

Primary demonstration flow:

`Scan location → expected unit missing → Missing Unit → indirect code starts automatically → coordinator receives exception → alternate location / next action returned → exception resolved → indirect activity ends → dashboard/audit updated`

The showroom should prove that ArcaCentum can build a practical enterprise workflow system, not merely a visual prototype.

---

## Relationship to Workforce Operations Platform

This concept expands the previously planned Workforce Operations product.

The existing Workforce Operations roadmap remains focused on areas such as:
- scheduling
- time clock
- GPS/geofence
- shift swaps
- PTO
- payroll-ready timesheets
- notifications
- RBAC
- audit logs
- security/staffing workflows

Warehouse Operations can become either:
1. a specialized module inside the broader Workforce Operations platform, or
2. a separate ArcaCentum product using the same ArcaCore services.

Final product architecture/branding can be decided later.
