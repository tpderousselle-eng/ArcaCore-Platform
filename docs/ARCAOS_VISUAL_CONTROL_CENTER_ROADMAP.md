# ArcaOS Visual Control Center Roadmap

**Status:** Formal future ArcaCentum capability — LOCKED IN  
**Owner:** ArcaCentum, Inc.  
**Primary system:** ArcaOS + ArcaCore  
**Purpose:** Give ArcaCentum direct, private control over visual upgrades, site fixes, motion, assets, previews, approvals, and deployment so Emergent becomes optional rather than required.

---

## 1. Product Principle

ArcaCentum must own its visual system.

The long-term operating rule is:

> ArcaCentum defines and owns the visual assets, composition, motion, controls, approvals, and deployment. External builders may assist with implementation, but they do not control the design system.

Emergent may remain useful as optional development tooling during transition, but it must not remain required for production visual maintenance, redesigns, fixes, or deployments.

---

## 2. Target Capability

Build an **ArcaOS Visual Control Center** integrated with the existing ArcaOS Site Intelligence Agent.

The system should let Tyler or another authorized operator open any ArcaCentum-controlled website or product surface and safely inspect, modify, preview, approve, and deploy visual changes without manually editing source code.

Representative future command:

> “The ArcaCentum.ai homepage feels too dull. Keep the layout, make the hero more cinematic, add a slow shooting star and subtle orbital motion, and show me three previews.”

Expected flow:

`request → understand page + brand + frozen constraints → generate controlled visual proposal → render preview → compare before/after → Tyler approval → ArcaCore validation/security/tests → GitHub branch → deployment`

---

## 3. Core Visual Scene Model

Important page sections should be represented through a structured **Visual Scene Model** rather than opaque CSS-only behavior.

Each scene may describe:
- background image/video/layer
- foreground layers
- transparent overlays
- logos/emblems
- gradients
- masks/blends
- stars/particles
- shooting stars
- orbital/light effects
- glow
- atmosphere/cloud layers
- text blocks
- buttons / CTAs
- spacing/layout anchors
- responsive positioning
- animation parameters
- reduced-motion behavior
- frozen/protected elements
- approval requirements

The scene model must never turn live controls into picture-based fake UI.

Navigation, text, links, buttons, forms, authentication controls, account controls, and application interactions remain real DOM/application elements.

---

## 4. Arca Asset System

ArcaCentum should own a reusable asset library with explicit purpose and provenance.

Example hero asset pack:

```text
hero-background.webp
arca-orb.webp
orbital-rings.webp
stars.webp
atmosphere.webp
foreground.webp
shooting-star.svg
```

Required capabilities:
- asset upload
- AI-generated replacement asset
- version history
- source/provenance metadata
- responsive variants
- desktop/tablet/mobile crops
- compression/optimization
- transparent layer support
- rollback
- approved/frozen asset states

ArcaOS must understand which asset belongs to which page/scene/layer.

---

## 5. Visual Controls

The Visual Control Center should expose direct controls instead of requiring repeated free-form prompts for every small change.

Representative controls:

### Hero Background
- Change image
- Generate new image
- Position
- Scale
- Blend
- Brightness
- Contrast
- Overlay strength
- Responsive crop

### Arca Orb / Emblem
- Glow intensity
- Pulse enabled
- Pulse speed
- Drift
- Orbit intensity
- Scale
- Position

### Stars / Particles
- Enabled
- Density
- Drift speed
- Opacity
- depth/parallax

### Shooting Star
- Enabled
- frequency range
- direction
- speed
- trail intensity
- randomization bounds

### Mouse Parallax
- Off / Low / Medium
- maximum translation
- easing

### Atmosphere
- cloud drift
- glow
- opacity
- depth

Every control must have safe bounded ranges.

---

## 6. Motion Architecture

Motion must be applied to independent visual layers where possible.

Do not expect a flattened hero image to provide independently animated planets, rings, stars, glow, city, or atmosphere.

Preferred architecture:

`base environment + transparent motion layers + live UI above`

Examples:
- base background remains mostly fixed
- stars drift slowly
- orbital layer rotates or shifts slowly
- Arca glow gently pulses
- atmosphere moves independently
- shooting star is a separate animated element
- cursor parallax remains optional and secondary

Motion principles:
- premium and restrained
- no excessive gaming-style animation
- GPU-friendly transforms where practical
- bounded animation loops
- no layout shift
- no content visibility dependency
- full `prefers-reduced-motion` support

All important content must be visible with animation disabled.

---

## 7. AI Design Commands

ArcaOS should allow high-level natural-language instructions, but translate them into structured visual changes instead of uncontrolled page rewrites.

Examples:
- “Make this hero more cinematic without changing the layout.”
- “Replace this image but preserve the composition.”
- “Add one slow shooting star every 20–35 seconds.”
- “Darken the left side so the headline reads better.”
- “Show three Arca orb alternatives.”
- “Fix the mobile crop.”

ArcaOS should map requests to the Visual Scene Model and expose the resulting structured changes before execution.

---

## 8. Preview + Approval Workflow

All meaningful visual changes should support:
- current vs proposed comparison
- desktop preview
- tablet preview
- mobile preview
- animation preview
- reduced-motion preview
- accessibility contrast checks
- responsive overflow checks
- changed-asset inventory
- changed-code inventory

Approval states:
- Reject
- Revise
- Approve Preview
- Approve Deployment

Major visual changes must not deploy automatically without approval.

---

## 9. ArcaCore Integration

ArcaCore should validate proposed site changes before deployment.

Required validation may include:
- deterministic build
- source integrity
- route integrity
- authentication regression
- accessibility checks
- responsive layout checks
- asset path containment
- broken-link checks
- security scan
- build/runtime validation
- preview deployment validation
- GitHub diff verification

Target pipeline:

```text
ArcaOS Visual Control Center
        ↓
Structured Visual Change
        ↓
ArcaCore Validation
        ↓
Security / Tests / Build
        ↓
Preview
        ↓
Tyler Approval
        ↓
GitHub
        ↓
ArcaCentum-owned Deployment
```

---

## 10. Site Intelligence Integration

This capability extends the existing **ArcaOS Site Intelligence Agent**.

Site Intelligence should identify:
- stale copy
- broken links
- incorrect product status
- weak or outdated imagery
- poor hero composition
- inaccessible contrast
- mobile/responsive defects
- excessive blank space
- performance issues
- outdated screenshots
- visually inconsistent sections

The Visual Control Center provides the controlled editing surface used to prepare and approve the fix.

---

## 11. Governance / Frozen Surfaces

ArcaOS must know which surfaces are frozen or protected.

Examples:
- Mission Control / ArcaOS v1 shell
- approved ArcaCentum parent composition
- approved ArcaCentum.ai structure
- approved ArcaCapitalis direction

Possible safe automatic corrections:
- broken internal links
- metadata
- accessibility attributes
- safe non-visual defects
- safe performance improvements
- factual product status corrections where source-of-truth is clear

Approval required:
- redesign
- navigation changes
- deletion of public content
- major image replacement
- hero composition changes
- pricing
- legal content
- authentication
- product positioning
- production deployment of material visual changes

---

## 12. Infrastructure Independence Goal

The Visual Control Center is part of the formal ArcaCentum infrastructure-independence plan.

End state:
- ArcaCentum owns source code
- ArcaCentum owns assets
- ArcaCentum owns authentication
- ArcaCentum owns secrets
- ArcaCentum owns build/validation
- ArcaCentum owns previews
- ArcaCentum owns CI/CD
- ArcaCentum owns hosting/deployment
- ArcaOS prepares controlled visual/site changes
- ArcaCore validates them
- Tyler approves them
- no production visual update requires Emergent

Emergent becomes optional development tooling only.

---

## 13. ArcaOS End-User Mission Control Personalization

ArcaOS should also expose a safe **user personalization layer** for Mission Control itself.

The official Mission Control design remains the protected default. Users customize only their own presentation layer unless an authorized organization administrator publishes a shared default.

User capabilities should include:
- drag-and-drop dashboard rearrangement
- resize cards/widgets
- show/hide modules
- choose which metrics appear first
- select or generate background imagery
- choose approved themes such as cosmic, minimal, or compact
- adjust bounded glow/motion intensity
- compact vs spacious density
- save multiple named layouts such as CEO View, Product View, Finance View, or Operations View
- reset instantly to the official default
- preview desktop/tablet/mobile where applicable
- optional team layout sharing where permissions allow

The personalization architecture should be:

`Official Mission Control shell → protected functional layout contract → per-user personalization layer → optional organization default`

Customization must never break:
- routes
- permissions
- RBAC
- authentication
- required alerts
- required compliance/security surfaces
- underlying ArcaOS data models
- system-critical actions

Examples of user AI commands:
- “Put Product Health, Blockers, and Revenue at the top.”
- “Make my Mission Control cleaner and more executive.”
- “Use this background image but keep all widgets readable.”
- “Create a Finance View and an Operations View.”

ArcaOS should preview the personalized layout before applying it.

Organization administrators should eventually be able to define a branded organization default using approved company assets, colors, backgrounds, and widget ordering without altering the underlying ArcaOS application shell.

This capability should use the same Visual Scene Model, asset provenance, preview, rollback, reduced-motion, and bounded-control principles as the main Visual Control Center.

---

## 14. Implementation Sequence

Do **not** derail ArcaCore Sprints 28–30 to build this prematurely.

Recommended sequence:

1. Complete and certify ArcaCore Sprint 27.
2. Complete Sprint 28 platform primitives.
3. Complete Sprint 29 production intelligence and stable internal SDK.
4. Complete Sprint 30 / ArcaCore v1 certification.
5. Formalize Visual Scene Model schemas and contracts.
6. Build Arca Asset System.
7. Build ArcaOS Visual Control Center UI.
8. Integrate Site Intelligence recommendations.
9. Add structured AI design commands.
10. Add preview / before-after / device simulation.
11. Add End-User Mission Control Personalization and saved per-user layouts.
12. Add organization-level branded/default Mission Control layouts with RBAC controls.
13. Integrate ArcaCore validation/security/release checks.
14. Integrate GitHub branch/approval workflow.
15. Connect to ArcaCentum-owned deployment infrastructure.
16. Migrate visual-maintenance workflows away from Emergent.
17. Retain Emergent only as optional tooling if useful.

---

## 15. Definition of Success

This capability is complete when Tyler can make a request such as:

> “Replace this hero image, keep the layout, add a subtle shooting star, and fix the mobile crop.”

and ArcaOS can:
- understand the exact page and protected constraints
- generate or select the required assets
- prepare deterministic structured changes
- show desktop/tablet/mobile previews
- preserve real UI controls
- validate the change through ArcaCore
- provide a clear before/after diff
- request approval
- create the GitHub change
- deploy through ArcaCentum-owned infrastructure
- rollback safely if needed

It should also be complete when an end user can say:

> “Make my Mission Control cleaner, move Product Health and Blockers to the top, use this background, and save it as CEO View.”

and ArcaOS can safely preview and apply that personalization without changing the protected functional shell.

---

## 16. Locked Decision

**ArcaOS Visual Control Center is a formal future ArcaCentum capability.**

**End-User Mission Control Personalization is also a formal future ArcaOS capability.**

These are not optional polish and should not be forgotten after ArcaCore v1.

Their strategic purpose is to give ArcaCentum private, durable control over visual design, site maintenance, motion, previews, approvals, fixes, deployment, and safe user-customizable Mission Control experiences across the ecosystem.
