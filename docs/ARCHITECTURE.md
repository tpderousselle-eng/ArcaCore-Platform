# ArcaCore Architecture

Version: 1.0

---

# Vision

ArcaCore is an application compiler.

Instead of generating isolated source files, ArcaCore understands an application's structure through metadata and produces complete, production-ready software.

The long-term goal is to allow developers to describe an application once and let ArcaCore generate every layer consistently.

---

# Core Principles

## Single Source of Truth

Every application should have one metadata definition.

Everything else is generated from that metadata.

---

## Separation of Responsibilities

The system is divided into independent layers.

Parser

- Understands developer input.
- Produces metadata.

Registry

- Stores application metadata.
- Maintains project knowledge.

Renderers

- Convert metadata into framework-specific output.

Templates

- Contain presentation only.
- No business logic.

Generators

- Coordinate the rendering process.

---

## Deterministic Generation

The same metadata should always generate identical output.

Generation should never depend on hidden state.

---

## Convention Over Configuration

ArcaCore should make intelligent assumptions whenever possible.

Example:

customer_id:int:fk=customers.id

automatically generates

- ForeignKey
- relationship()
- back_populates
- timestamps
- imports

without additional configuration.

---

# Generation Pipeline

Developer Input

↓

Parser

↓

Metadata Model

↓

Registry

↓

Renderers

↓

Templates

↓

Black Formatter

↓

Generated Application

---

# Directory Structure

tools/

core/

renderers/

registry/

templates/

generators/

docs/

backend/

frontend/

---

# Registry

The registry is the project's memory.

It records:

- Models
- Fields
- Relationships
- Constraints

Future versions will also include:

- APIs
- Services
- Permissions
- Events
- UI metadata

---

# Rendering System

Templates never contain business rules.

Renderers prepare all framework-specific syntax before templates are rendered.

This keeps templates simple and reusable.

---

# Code Generation

Generated code should always be:

- readable
- formatted
- deterministic
- production-ready

Manual editing should remain possible.

Future generations should avoid overwriting user modifications without explicit approval.

---

# Future Direction

ArcaCore will evolve beyond a CRUD generator.

Future capabilities include:

- Relationship intelligence
- Migration generation
- Schema comparison
- ER diagrams
- React generation
- API generation
- GraphQL generation
- AI-assisted application generation

---

# Philosophy

Developers describe the application.

ArcaCore understands it.

Everything else is generated from understanding.