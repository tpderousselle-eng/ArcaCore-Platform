# ArcaCore Architecture

**Version:** 1.0.0  
**Status:** Living Document

---

# Mission

ArcaCore is the shared backend platform that powers every ArcaCentum product.

Instead of building isolated applications, ArcaCore provides reusable infrastructure that every product inherits.

Examples include:

- Authentication
- Authorization
- Organizations
- Workspaces
- Projects
- Tasks
- AI Services
- Billing
- Notifications
- Storage
- Audit Logging
- API Infrastructure

Every new product should reuse ArcaCore instead of reimplementing common functionality.

---

# Architecture Overview

Every feature follows the same layered architecture.

```
API Router
    ↓
Service
    ↓
CRUD
    ↓
SQLAlchemy Model
    ↓
Database
```

Each layer has one responsibility.

---

# Models

Models define database tables.

Responsibilities:

- Table definitions
- Relationships
- Constraints
- Database defaults

Models should never contain business logic.

---

# CRUD Layer

CRUD performs persistence only.

Responsibilities:

- Create
- Read
- Update
- Delete
- Database queries

CRUD must not:

- Validate permissions
- Execute workflows
- Coordinate multiple entities
- Perform business decisions

---

# Service Layer

Services contain business logic.

Responsibilities:

- Validation
- Permission checks
- Business rules
- Workflows
- Cross-module coordination
- Events

Services orchestrate CRUD operations.

---

# API Layer

Routers expose HTTP endpoints.

Responsibilities:

- Request validation
- Dependency injection
- Authentication
- Calling services
- Returning responses

Routers should stay thin.

---

# Core Framework

Shared infrastructure belongs in:

```
backend/app/core
```

Core components include:

- BaseCRUD
- BaseService
- BaseRouter (future)
- BaseResponse
- BaseExceptions
- Pagination
- Permission Helpers
- Utilities

Core should contain no application-specific business logic.

---

# Design Principles

## Single Responsibility

Each layer has one purpose.

Models → Database

CRUD → Persistence

Services → Business Logic

Routers → HTTP

---

## Reuse Before Copying

If functionality appears in multiple modules, move it into Core.

Avoid duplicated code.

---

## Business Logic Lives in Services

Correct:

```
Router
    ↓
Service
    ↓
CRUD
```

Incorrect:

```
Router
    ↓
CRUD
        ↓
Business Logic
```

---

## Thin Routers

Routers should only:

- Validate requests
- Inject dependencies
- Call services
- Return responses

Nothing more.

---

## Consistent APIs

Every endpoint should eventually return:

```json
{
    "success": true,
    "message": "...",
    "data": {}
}
```

Errors should follow a consistent format as well.

---

# Current Platform Structure

```
Organization
│
├── Members
├── Invitations
└── Workspaces
        │
        ├── Members
        └── Projects
```

Future expansion:

```
Projects
│
├── Tasks
├── Comments
├── Files
├── AI Conversations
├── Activity
├── Notifications
└── Automation
```

---

# Development Workflow

Every new module follows this sequence:

1. SQLAlchemy Model
2. Database Migration
3. Schema
4. CRUD
5. Service
6. Router
7. Route Registration
8. Smoke Test
9. Git Commit
10. Git Push

---

# Testing Requirements

Every module must pass:

- Migration succeeds
- Application starts
- Swagger smoke tests
- CRUD verification
- Permission verification

before being considered complete.

---

# Coding Standards

- Use type hints everywhere.
- Prefer explicit code over clever code.
- Keep methods focused.
- Use dependency injection.
- Follow consistent naming conventions.
- Minimize duplicated code.
- Favor reusable abstractions.

---

# Long-Term Vision

ArcaCore is not an application.

ArcaCore is the backend framework powering every ArcaCentum product.

Every future product should inherit:

- Authentication
- Organizations
- Permissions
- Billing
- AI
- Storage
- Notifications
- Auditing

without reimplementing those capabilities.

The goal is to build features once and reuse them everywhere.

---

# Status

This document is a living architectural guide.

As ArcaCore evolves, this document should evolve with it while preserving the core design principles.