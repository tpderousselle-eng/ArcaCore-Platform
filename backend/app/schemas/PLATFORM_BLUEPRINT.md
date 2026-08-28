# ArcaCore Platform Blueprint

## Vision

ArcaCore is the shared platform that powers every ArcaCentum product.

Rather than each product implementing its own authentication, users,
organizations, billing, notifications, permissions, and infrastructure,
those capabilities live inside ArcaCore and are shared.

---

# Platform Layers

```
                 Products
──────────────────────────────────────────────
ArcaCentum.ai
ArcaCentum Credit
ArcaCommerce
Workforce
Future Products

──────────────────────────────────────────────
ArcaCore Platform Services

Authentication
Authorization
Organizations
User Management
Billing
Notifications
Audit Logs
API Keys
Background Jobs
File Storage
AI Services

──────────────────────────────────────────────
Infrastructure

FastAPI
PostgreSQL
SQLAlchemy
Alembic
Docker
Redis (Future)
Object Storage (Future)
```

---

# Core Principles

- One authentication system.
- One authorization system.
- One user system.
- One organization system.
- One billing platform.
- One notification platform.
- One audit system.
- Shared infrastructure for every product.

No product should reimplement these capabilities.

---

# Identity Platform

Responsible for:

- Registration
- Login
- JWT Authentication
- Password Recovery
- Email Verification
- RBAC
- Organizations
- Team Membership
- Invitations
- Sessions (Future)
- MFA (Future)

---

# User Management

Responsible for:

- User Profiles
- User Search
- User Administration
- User Roles
- Account Status
- Preferences

---

# Organizations

Future responsibilities:

- Organization Creation
- Memberships
- Teams
- Departments
- Ownership
- Invitations
- Organization Settings

---

# Billing

Future responsibilities:

- Plans
- Subscriptions
- Invoices
- Payments
- Usage Tracking
- Limits
- Feature Access

---

# Notification Platform

Shared services:

- Email
- SMS
- Push Notifications
- In-App Notifications
- Webhooks

---

# Audit Platform

Every important action should be recorded.

Examples:

- Login
- Password Reset
- Role Change
- User Invitation
- Subscription Change
- API Key Creation

---

# API Platform

Future modules:

- Public API
- API Keys
- OAuth Applications
- SDKs
- Rate Limiting
- Usage Metrics

---

# AI Platform

Shared AI capabilities:

- AI Models
- AI Agents
- Workflow Engine
- Prompt Library
- Shared AI Services

Every ArcaCentum product should consume these services rather than
implementing them independently.

---

# Database Domains

Major domains planned for ArcaCore:

- Users
- Organizations
- Memberships
- Roles
- Permissions
- Audit Logs
- Notifications
- Billing
- Subscriptions
- API Keys
- AI Jobs
- Background Jobs

---

# Development Standards

Every feature should follow:

Request

↓

Router

↓

Service

↓

CRUD

↓

Database

Every feature should include:

- Model
- Migration
- Schema
- CRUD
- Service
- Permissions
- Router
- Swagger Verification
- Git Commit
- Git Push

---

# Long-Term Goal

ArcaCore should become the operating platform that powers every
ArcaCentum application.

Products should focus on solving business problems.

ArcaCore should provide the shared infrastructure that every product
depends on.