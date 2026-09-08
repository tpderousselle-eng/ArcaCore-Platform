# ArcaCentum.ai Private Beta Program

**Status:** Formal future launch capability — LOCKED IN  
**Owner:** ArcaCentum, Inc.  
**Primary product:** ArcaCentum.ai  
**Purpose:** Create a controlled, professional private-beta intake, invitation, onboarding, testing, and feedback workflow for the first real ArcaCentum.ai users.

---

## 1. Beta Principle

Do not open ArcaCentum.ai broadly before one complete user journey is reliable.

Target minimum beta journey:

`idea → Smart Discovery → product brief → build → preview → revise → save → feedback`

Beta quality is measured primarily by whether a normal nontechnical user can complete that journey without ArcaCentum staff manually rescuing the session.

The first beta should be intentionally small and curated.

Recommended initial cohort:

- 5–10 testers
- mixed technical ability
- mixed product ideas
- at least one nontechnical user
- at least one small-business owner
- at least one game-builder candidate
- at least one technically experienced tester
- at least one tester willing to intentionally stress/break workflows

---

## 2. Public Beta Entry Point

Add a clear public CTA such as:

**Apply for Private Beta**

Suggested flow:

`landing page → beta application → review → invitation → account creation → onboarding → testing → feedback`

Do not automatically grant access to every applicant during the first cohort.

---

## 3. Beta Application Form

The application should be short enough to complete quickly while collecting enough context to select useful testers.

Required fields:

1. **Name**
2. **Email address**
3. **What do you want to build?**
4. **Technical experience**
   - No coding experience
   - Some coding experience
   - Developer / technical professional
5. **What kind of product do you want to create?**
   - Web app
   - Mobile app
   - Business/internal tool
   - Game
   - Other
6. **Are you willing to report bugs and provide feedback?**
7. **How often could you test during the beta?**
8. **Anything specific you want ArcaCentum.ai to help you create?**

Optional fields may include:

- company / organization
- preferred platform
- country / region
- referral source

Do not request sensitive personal information unless it is genuinely required for the beta.

---

## 4. Beta Notice

Place a concise notice near the form:

> **Private Beta — Limited Access**  
> ArcaCentum.ai is still in active development. Beta testers may encounter bugs, incomplete features, or changes during testing. Feedback from beta participants will help shape the platform before public launch.

Do not imply production-grade reliability during beta.

---

## 5. Email Consent

Beta communication consent must be explicit.

Required checkbox:

> `I agree to receive emails related to the ArcaCentum.ai private beta, including invitations, testing updates, bug follow-ups, and beta release information.`

Consent state should be stored with timestamp and policy/version metadata where appropriate.

Do not silently subscribe beta applicants to unrelated marketing campaigns.

---

## 6. Applicant States

Use a bounded state model such as:

- APPLIED
- UNDER_REVIEW
- WAITLISTED
- INVITED
- ACCEPTED
- ACTIVE_TESTER
- PAUSED
- COMPLETED
- DECLINED
- REMOVED

Transitions should be explicit and auditable.

Do not expose internal reviewer notes to applicants.

---

## 7. Beta Selection

The goal is not to pick only the most technically advanced applicants.

Select a useful mix of testers based on:

- technical experience
- product category
- willingness to provide feedback
- availability
- diversity of intended use cases
- likelihood of exercising different ArcaCentum capabilities

Initial cohort should deliberately include nontechnical users because ArcaCentum.ai is intended to reduce the need for traditional programming expertise.

---

## 8. Invitation Workflow

Approved applicants receive a controlled beta invitation email.

Invitation should include:

- confirmation that they were selected
- beta status / limitations
- secure account creation or login link
- onboarding instructions
- expected feedback responsibilities
- support/bug-reporting path
- applicable beta terms/privacy links

Invitation tokens, if used, must be:

- unpredictable
- single-purpose
- expiration-bounded
- non-enumerable
- revocable where practical
- never logged in plaintext

Do not grant access merely from a user-supplied email parameter.

---

## 9. Beta Access Control

Private beta access should be represented as a real entitlement/role, not a hidden front-end toggle.

Possible entitlement:

`arca_beta_tester`

Access checks must occur at trusted backend/service boundaries.

Beta access should compose with:

- ArcaCore multitenancy
- RBAC
- account identity
- usage/credit limits
- billing state if applicable

Do not allow a normal account to obtain beta access by changing client-side state.

---

## 10. Beta Onboarding

First-login onboarding should be short and task-oriented.

Recommended steps:

1. Welcome to the ArcaCentum.ai private beta.
2. Explain that the product is still in development.
3. Ask what they want to build.
4. Launch Smart Discovery.
5. Explain how to preview/revise the generated result.
6. Show where to report bugs or feedback.

Avoid long onboarding tutorials before the user can actually create something.

---

## 11. Feedback System

Feedback should be built directly into the authenticated product experience.

Recommended feedback actions:

- Report a bug
- Something was confusing
- Missing feature
- Build failed
- Build result was wrong
- Design/visual feedback
- General suggestion
- Positive feedback

Each feedback record should automatically capture safe context where available:

- application/product surface
- page/module
- build/project identifier
- browser/device metadata
- timestamp
- relevant safe error code
- app version
- user-provided description

Do not automatically capture secrets, passwords, private prompts, source code, or uploaded file contents unless the user explicitly chooses to include them.

---

## 12. Build-Failure Feedback

If a generated build fails during beta, provide a dedicated action such as:

**Report this build**

ArcaOS should eventually correlate:

`user feedback → build ID → ArcaCore validation result → failure localization → responsible generator/system`

This turns beta failures into structured engineering intelligence instead of disconnected support messages.

---

## 13. Beta Analytics

Track aggregate product-learning metrics such as:

- application started
- Smart Discovery completed
- product brief produced
- build started
- build succeeded
- preview opened
- revision requested
- project saved
- feedback submitted
- user returned for second session

Also track failure categories and drop-off points.

Do not treat vanity sign-up counts as the primary beta success metric.

Primary question:

> Can a normal person describe what they want and receive a useful working result without manual rescue?

---

## 14. Beta Dashboard in ArcaOS

ArcaOS / Mission Control should eventually expose a private Beta Operations view showing:

- applicants
- invited testers
- active testers
- waitlist
- build success rate
- build-failure categories
- feedback volume
- unresolved blockers
- common requests
- tester activity
- cohort retention
- launch-readiness indicators

This is an internal operations surface and should not be exposed to beta testers.

---

## 15. Support Workflow

Beta support should use a controlled path such as:

- in-product support ticket
- feedback record
- support email

Support records should link to the tester account and relevant project/build where possible.

The user should not need to explain their whole context repeatedly.

---

## 16. Terms / Privacy / Safety

Before activation, beta testers should receive clear beta terms and privacy information.

At minimum communicate:

- product is pre-release
- features may change
- bugs/outages may occur
- data handling rules
- acceptable use
- ownership/licensing expectations for user-generated projects/assets
- feedback usage terms
- how to leave the beta

Do not market experimental functionality as guaranteed or production-ready.

If minors are ever permitted to use ArcaCentum.ai directly, create a separate age-appropriate legal/privacy and parental-consent review before enabling that audience.

---

## 17. Beta Credits / Limits — LOCKED POLICY

### Founding Tester pricing

The first private beta cohort — **ArcaCentum.ai Founding Testers** — receives beta access **free of charge**.

Founding Testers should not be required to purchase normal production credits in order to help ArcaCentum test an unfinished product.

Their primary value to ArcaCentum during this phase is:

- real-world usage
- product feedback
- build-failure discovery
- edge-case discovery
- usability feedback
- bug reports
- repeated testing

### Free does not mean unlimited

Founding Tester usage must remain bounded and server-enforced.

Recommended starting model:

- initial beta credit grant per selected tester
- target starting range: approximately **500–1,000 beta credits** per tester unless later testing shows a different amount is more appropriate
- credits may expire at the end of the beta/cohort period
- no automatic unlimited refill
- bounded AI/model usage
- bounded build count where needed
- bounded storage
- abuse/rate controls remain active

The exact numeric credit grant remains configurable and may change as real usage cost is understood.

### Manual top-ups

ArcaCentum may manually grant additional beta credits when a tester:

- is actively providing useful feedback
- reaches the limit through legitimate testing
- is testing an important scenario
- needs additional credits to reproduce a defect

Manual top-ups should be auditable.

Do not silently create unlimited accounts.

### Beta credit identity

Beta credits should be distinguishable from normal purchased/promotional production credits where practical.

Possible metadata:

- grant type: `FOUNDING_BETA`
- amount granted
- amount remaining
- granted timestamp
- expiration timestamp if applicable
- grant reason
- authorized grant source

This prevents beta grants from being confused with cash-equivalent purchased balances.

### User-visible transparency

Beta testers should be able to see:

- their beta credit balance
- approximate usage
- expiration if applicable
- whether additional testing credits can be requested

Do not surprise testers with charges.

### No automatic billing

Founding Testers must not be automatically converted into a paid subscription merely because the private beta ends.

Any future paid conversion requires a clear affirmative user action and disclosure of pricing.

### Future pricing progression

The planned progression is:

- **Founding Private Beta:** free access + capped beta credits
- **Expanded Private Beta:** may remain free or introduce selectively discounted credits depending on platform maturity and testing goals
- **Public Beta:** may introduce normal paid plans, paid credit packs, launch discounts, or promotional credits
- **General Availability:** standard production pricing model

Do not begin charging beta testers merely because infrastructure costs exist; charging should begin when ArcaCentum can provide sufficiently reliable productive value rather than primarily asking users to debug the platform.

### Billing-system separation

Beta entitlements and free beta-credit grants should integrate with the account/credit system without creating fake payment transactions.

A free beta grant is not a Stripe purchase and should not be represented as one.

Usage limits must remain enforced at trusted server/service boundaries.

---

## 18. Beta Cohorts

Use cohorts rather than one giant beta.

Example:

### Cohort 1 — Founding Testers
5–10 curated testers.

Focus:
- basic end-to-end usability
- Smart Discovery quality
- build reliability
- onboarding confusion
- high-severity defects

Commercial policy:
- free private-beta access
- capped ArcaCentum-provided beta credits
- manual top-ups for productive testing when approved

### Cohort 2 — Expanded Private Beta
20–50 testers after Cohort 1 blockers are resolved.

Focus:
- wider product categories
- scale
- more devices/browsers
- collaboration
- account/credit behavior

Commercial policy may remain free or begin testing discounted credit models only after ArcaCentum is providing reliable productive value.

### Cohort 3 — Pre-Public Beta
Larger controlled audience.

Focus:
- launch-readiness
- support load
- abuse controls
- performance
- conversion/onboarding

This cohort may be used to validate production pricing and paid-credit behavior before broad launch.

Do not increase cohort size simply because signups exist.

---

## 19. Beta Exit Criteria

Do not move from private beta toward public launch until agreed minimum criteria are met.

Possible criteria:

- stable authentication
- stable account/entitlement flow
- Smart Discovery reliably completes
- representative apps build successfully
- preview/revision workflow works
- project persistence works
- no blocking Critical/High security findings
- build failures produce actionable diagnostics
- beta users can submit feedback
- no major cross-tenant or data-isolation defects
- support burden is manageable
- core flows work on supported desktop/mobile browsers

ArcaCore v1 certification should be completed before treating ArcaCentum.ai as ready for a serious external beta dependent on ArcaCore generation.

---

## 20. Founding Tester Identity

The first cohort may be branded as:

**ArcaCentum.ai Founding Testers**

Possible recognition later:

- Founding Tester badge
- profile/account designation
- early-access status
- launch acknowledgment if the tester explicitly opts in

Do not promise permanent free access or lifetime benefits unless ArcaCentum intentionally adopts such a policy.

The locked beta-credit policy does **not** create a permanent free-account entitlement after the beta.

---

## 21. Implementation Sequence

Recommended sequence:

1. Complete ArcaCore v1 certification.
2. Confirm ArcaCentum.ai end-to-end builder path works using ArcaCore.
3. Complete production OAuth / signup readiness.
4. Implement private-beta application page/form.
5. Implement applicant state model and admin review.
6. Implement invitation/entitlement workflow.
7. Implement beta-credit grant ledger and server-side beta usage limits.
8. Implement first-login beta onboarding.
9. Implement in-product feedback capture.
10. Implement ArcaOS Beta Operations dashboard.
11. Add beta analytics and failure correlation.
12. Create Founding Tester cohort.
13. Grant each selected tester a bounded free beta-credit allowance.
14. Invite first 5–10 testers.
15. Manually top up productive testers when justified.
16. Resolve blocking findings before expanding cohort.
17. Test paid/discounted credit behavior only when the platform is mature enough to provide reliable productive value.

Do not use Emergent as the hidden builder behind beta showcase results once ArcaCentum's own ArcaCore/ArcaDev path is capable of producing them.

---

## 22. Definition of Success

The private beta system is working when ArcaCentum can:

- collect structured applications
- review/select a small cohort
- invite approved testers securely
- grant beta access server-side
- grant bounded free beta credits without fake billing transactions
- show remaining beta credits clearly
- top up legitimate testers through an auditable admin workflow
- onboard users quickly
- let them attempt a real build
- capture structured feedback and failures
- correlate feedback to projects/builds
- observe cohort health in ArcaOS
- revoke/pause beta access when needed
- expand cohorts intentionally

without manually managing the entire program through DMs, spreadsheets, ad-hoc email lists, or manual payment workarounds.

---

## 23. Locked Decision

**ArcaCentum.ai will use a structured private-beta application and invitation system before broad public access.**

The first beta cohort should be small, curated, and intentionally diverse in technical experience and product goals.

Email collection is required for beta communication, with explicit beta-specific consent.

**ArcaCentum.ai Founding Testers will not pay for their initial private-beta usage. They will receive free, capped, server-enforced beta credits in exchange for meaningful testing and feedback.**

**Founding beta access is not unlimited, is not a promise of lifetime free access, and will not automatically convert into a paid subscription.**

The exact initial beta-credit amount remains configurable; the current planning target is approximately **500–1,000 credits per Founding Tester**, with auditable manual top-ups when justified.

The beta program is designed to generate product-learning and operational intelligence for ArcaOS, not merely collect signups.
