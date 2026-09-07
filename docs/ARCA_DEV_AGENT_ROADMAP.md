# ArcaDev Agent Roadmap

**Status:** Formal future ArcaCentum capability — LOCKED IN  
**Owner:** ArcaCentum, Inc.  
**Primary systems:** ArcaCentum.ai + ArcaOS + ArcaCore  
**Purpose:** Let users create and run their own specialized software-engineering agents with safe repository access, tool execution, testing, review, approvals, and deployment workflows without depending on a third-party builder.

---

## 1. Product Principle

ArcaCentum should support a first-party coding-agent experience comparable in capability class to modern autonomous software-engineering agents, while remaining an original ArcaCentum product.

ArcaCentum must not copy third-party branding, proprietary implementations, or claim to be another vendor's coding agent.

The product should instead provide a native ArcaCentum engineering-agent system that is powered by ArcaOS orchestration and ArcaCore validation.

Working product name: **ArcaDev Agent**.

Final branding may change later.

---

## 2. Target User Experience

A user should eventually be able to say:

> “Build authentication, add billing, fix the failing tests, and open a pull request.”

The system should safely execute an end-to-end workflow equivalent to:

```text
User Request
    ↓
ArcaOS Planning
    ↓
Agent / Team Assignment
    ↓
Isolated Repository Workspace
    ↓
Code / File Changes
    ↓
Tests / Builds / Migrations
    ↓
ArcaCore Validation
    ↓
Security Review
    ↓
Diff / Preview
    ↓
User Approval
    ↓
Commit / Pull Request / Deployment
```

The user should not need to manually operate Git, a terminal, or CI/CD for ordinary supported workflows.

---

## 3. User-Created Coding Agents

Users should be able to create their own specialized engineering agents.

A user-defined agent may declare:

- display name
- engineering role
- model/provider policy
- allowed repositories
- allowed branches
- allowed tools
- blocked tools
- language/framework specialties
- coding conventions
- testing requirements
- security requirements
- deployment permissions
- approval requirements
- network permissions
- secret-access policy
- maximum task runtime
- maximum retry budget
- collaboration rules

Example:

```text
Agent: FinTech Engineer
Role: Backend + PostgreSQL specialist
Frameworks: FastAPI, SQLAlchemy, React
Rules:
- never manually rewrite migration history
- always run security tests
- require approval before production deployment
Allowed repos:
- Project A
Allowed actions:
- read
- edit
- test
- commit
Blocked actions:
- production deploy
```

Another example:

```text
Agent: Security Reviewer
Role: Independent security auditor
Allowed actions:
- read repository
- inspect diffs
- run security tests
- propose fixes
Blocked actions:
- feature development
- direct production deployment
```

---

## 4. Agent Registry

ArcaOS should maintain a first-class **Agent Registry**.

Each registered agent should have a canonical, versioned contract describing:

- agent identity
- role
- capabilities
- tool permissions
- repository permissions
- tenant/organization ownership
- prompt/persona version
- model policy
- security policy
- approval policy
- concurrency limits
- audit metadata
- enabled/disabled state

The Agent Registry should compose with existing ArcaOS Prompt Library personas rather than replace them.

Prompt Library persona → Agent Contract → Tool/Repo Policy → Execution Runtime.

---

## 5. Arca Council Integration

ArcaDev Agent should integrate with the future **Arca Council** multi-agent architecture.

Representative software team:

```text
Arca Council
├── Chief Product Strategist
├── Software Architect
├── Backend Engineer
├── Frontend Engineer
├── Mobile Engineer
├── Security Officer
├── QA Engineer
└── Release Manager
```

Potential operating modes:

### Single Agent
One specialized agent completes a bounded task.

### Lead + Reviewer
One agent implements; a second independent agent reviews.

### Engineering Team
Several agents work on separate scoped tasks in isolated worktrees/branches.

### Council Deliberation
Architect, security, product, and engineering agents compare recommendations before implementation.

### Chair Synthesis
An ArcaOS Chair/Lead produces the final recommendation or integration plan for user approval.

No agent should be able to silently override another agent's explicit blocking security finding.

---

## 6. Repository Intelligence

The system should understand repository structure before changing code.

Required future capabilities include:

- repository tree indexing
- symbol/function/class discovery
- dependency graph
- framework detection
- build/test command discovery
- architecture summaries
- git history awareness where permitted
- changed-file ownership/context
- project instructions / agent rules
- generated-code boundaries
- protected/frozen directories

ArcaDev must distinguish user-owned source from generated or protected source.

ArcaCore repositories should continue honoring generator-first rules.

---

## 7. Isolated Engineering Workspaces

Every autonomous engineering task should execute in an isolated environment.

Preferred primitives:

- git worktree or temporary branch
- isolated filesystem workspace
- container/sandbox where appropriate
- bounded CPU/memory/runtime
- controlled network access
- scoped secrets
- explicit repository permissions

Agents must not edit the user's main branch directly unless an explicitly authorized workflow allows it.

No force push by default.

No history rewrite without explicit approval.

---

## 8. Tool Execution Layer

ArcaDev should provide a bounded tool runtime for software engineering.

Potential tools:

- file read/write
- repository search
- git status/diff/branch/commit
- test runner
- linter
- formatter
- type checker
- build system
- package manager
- container runtime
- database migration tooling
- local HTTP/runtime testing
- ArcaCore generator
- ArcaCore release gate

Security requirements:

- no arbitrary shell access by default
- allowlisted commands or constrained command runner
- no shell injection
- no untrusted `eval` / `exec`
- no arbitrary plugin/import execution
- bounded output and runtime
- deterministic logging/audit
- secrets redacted

---

## 9. Coding Model Layer

ArcaDev should support a model abstraction rather than being permanently tied to one model provider.

The platform may route tasks based on:

- coding complexity
- context window requirements
- latency
- cost
- security policy
- customer preference
- organization policy

The model layer should never receive broader repository, secret, or tenant access than the task requires.

Future provider support should remain policy-driven and replaceable.

---

## 10. Planning and Task State

Long-running engineering work should use durable task state.

A task should track:

- user request
- normalized engineering objective
- plan
- sub-tasks
- assigned agent(s)
- repository/worktree
- current state
- attempts
- blockers
- tests executed
- changed files
- security findings
- approvals
- final result

Task execution should survive controlled retries/recovery without losing the audit trail.

This should build directly on ArcaCore's autonomous orchestrator and deterministic recovery workflow.

---

## 11. Engineering State Machine

A bounded state machine should govern autonomous coding work.

Representative states:

```text
planned
queued
running
blocked
awaiting_approval
reviewing
validated
ready_to_merge
completed
failed
cancelled
```

Impossible transitions must be rejected.

A failed build/test/security review must never be reported as success.

---

## 12. Approval Gates

Agents may operate autonomously only within explicitly authorized boundaries.

Examples of actions that should generally require approval:

- destructive database migration
- production deployment
- credential/secret changes
- branch deletion
- force push
- history rewrite
- billing/payment configuration changes
- authentication/security policy changes
- infrastructure teardown
- broad dependency upgrades with major-version impact

Users/organizations should be able to tighten approval policy further.

---

## 13. Security Review Architecture

ArcaDev should support independent review agents.

A Security Reviewer should be able to:

- review the full task diff
- inspect generated artifacts
- run security regressions
- identify privilege escalation
- inspect tenant isolation
- inspect secret handling
- inspect command/network execution
- inspect storage/path containment
- inspect dependency risk
- block promotion

A blocking security finding must fail closed until fixed or explicitly handled under an authorized governance policy.

---

## 14. Tenant and Organization Isolation

ArcaDev must be fully multitenant.

Tenant A must not be able to:

- read Tenant B repositories
- view Tenant B task history
- access Tenant B agents
- access Tenant B worktrees
- access Tenant B secrets
- view Tenant B logs/diffs
- reuse Tenant B execution credentials

Agent definitions, tasks, workspaces, secrets, and audit records must be tenant-scoped where appropriate.

This should build on Sprint 28 multitenancy and RBAC primitives.

---

## 15. Secret and Credential Boundaries

Agents should use secret references rather than durable secret values.

Examples:

- GitHub credentials
- package registry credentials
- deployment credentials
- API keys
- database credentials
- signing keys

Secrets should be resolved only at the trusted runtime boundary.

Secret values must not be written into:

- source files
- prompts stored in durable logs
- task reports
- diffs
- agent definitions
- event payloads
- job payloads
- commit messages

---

## 16. GitHub / Source Control Integration

ArcaDev should eventually support:

- repository connection
- branch creation
- isolated worktrees
- commits
- pull requests
- PR updates
- review comments
- CI checks
- merge readiness
- protected branch policy
- user approval before sensitive pushes

The system should maintain a strict audit trail of every source-control mutation.

---

## 17. Test and Validation Pipeline

Before code can be declared complete, ArcaDev should be able to invoke relevant validation such as:

- unit tests
- integration tests
- generated runtime tests
- PostgreSQL tests
- migration validation
- Docker/Compose tests
- Kubernetes validation
- type checking
- linting
- deterministic regeneration
- security scan
- ArcaCore release gate

Validation requirements should be project-specific and agent-policy-aware.

---

## 18. Recovery and Self-Correction

ArcaDev should use ArcaCore's failure localization and deterministic recovery capabilities.

Representative loop:

```text
implement
→ test
→ localize failure
→ identify responsible generator/file/agent
→ prepare bounded correction
→ retest affected scope
→ full validation
```

Retries must be bounded.

The system should never enter an endless agent loop.

---

## 19. Parallel / Multi-Agent Engineering

Future support should allow multiple agents to work concurrently when safe.

Requirements:

- isolated worktrees/branches
- non-overlapping task scopes where practical
- file ownership/conflict detection
- deterministic integration order
- merge-conflict handling
- independent review
- bounded concurrency
- cost/resource budgets

One agent should not silently overwrite another agent's unmerged work.

---

## 20. User Experience in ArcaCentum.ai

Potential Studio experience:

### Agent Builder
Create/edit agent role, tools, permissions, rules, model policy, and repository access.

### Engineering Task
Natural-language task submission.

### Live Task Timeline
Shows:

- plan
- current agent
- tool calls
- files changed
- tests
- blockers
- approvals
- security findings

### Diff Review
Before/after code review and changed-file summary.

### Approval Center
Approve/reject sensitive actions.

### Team View
Shows multiple engineering agents and assigned tasks.

### Release View
ArcaCore validation + security + deployment readiness.

---

## 21. Smart Discovery Integration

Smart Discovery should eventually be able to hand an approved product brief directly into ArcaDev / Arca Council.

Target flow:

```text
Idea
→ Smart Discovery
→ Product Brief
→ Arca Council Review
→ Architecture / Build Plan
→ User Approval
→ ArcaDev Engineering Team
→ ArcaCore Generation / Validation
→ Preview
→ Deployment
```

This creates a true closed loop from idea to working software.

---

## 22. Showroom / Dogfooding Rule

New ArcaCentum showroom products should be used to prove ArcaDev and ArcaCore capabilities.

Strategic target:

> “This product was designed through ArcaOS, implemented by ArcaDev agents, validated by ArcaCore, security-reviewed, and deployed through ArcaCentum-owned infrastructure.”

Do not use a third-party builder as the hidden implementation engine for products whose purpose is to demonstrate ArcaCentum's own builder capabilities once ArcaDev is sufficiently capable.

Existing legacy products may transition gradually.

---

## 23. Infrastructure Dependencies

ArcaDev should be built after the required ArcaCore foundations exist.

Primary dependencies include:

- Sprint 27 autonomous orchestrator
- deterministic recovery
- failure localization
- canonical application manifest
- Sprint 28 multitenancy
- Sprint 28 RBAC
- Sprint 28 secrets lifecycle
- Sprint 28 jobs
- Sprint 28 events/webhooks
- Sprint 28 storage
- Sprint 29 observability/diagnostics
- Sprint 29 plugin/action framework
- stable internal API/SDK
- Sprint 30 ArcaCore v1 certification

Do not derail ArcaCore v1 certification to prematurely implement the full ArcaDev product.

---

## 24. Recommended Implementation Sequence

1. Complete Sprint 28.
2. Complete Sprint 29.
3. Complete Sprint 30 / ArcaCore v1 certification.
4. Formalize ArcaOS Agent Registry schema.
5. Formalize Arca Council role/orchestration contracts.
6. Build isolated repository/worktree execution runtime.
7. Build constrained engineering tool executor.
8. Build model-provider abstraction.
9. Build durable engineering task state machine.
10. Add single-agent coding workflow.
11. Add independent reviewer/security agent workflow.
12. Add GitHub branch/commit/PR workflow.
13. Integrate ArcaCore validation and release gate.
14. Add user-configurable Agent Builder UI.
15. Add multi-agent engineering teams.
16. Connect Smart Discovery → Council → ArcaDev.
17. Build first ArcaCentum showroom product entirely through the system.
18. Expand deployment capabilities under ArcaCentum-owned infrastructure.

---

## 25. Definition of Success

ArcaDev is successful when a user can create an engineering agent such as:

> “Senior FastAPI/PostgreSQL engineer. Can edit and test this repository. Must run migrations, unit tests, and security review. Cannot deploy without my approval.”

and then request:

> “Add organization invitations and role-based permissions.”

The system can then:

- understand the repository
- create an isolated workspace
- plan the change
- edit the correct files
- run tests
- localize and repair failures
- run independent security review
- show the user the diff
- request approval where required
- create a commit/pull request
- validate through ArcaCore
- preserve tenant/repository isolation
- maintain a complete audit trail

without relying on Emergent to implement the feature.

---

## 26. Locked Decision

**ArcaDev Agent / user-created coding agents are a formal future ArcaCentum capability.**

The capability should integrate with:

- ArcaCentum.ai Studio
- ArcaOS
- Prompt Library
- Agent Registry
- Arca Council
- Smart Discovery
- ArcaCore
- GitHub/source control
- ArcaCentum-owned deployment infrastructure

Its strategic purpose is to let users create safe, specialized AI engineering agents and software teams that can plan, code, test, review, and ship software using ArcaCentum's own platform.
