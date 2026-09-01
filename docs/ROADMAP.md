# ArcaCore Roadmap

Version: 1.0

---

# Vision

ArcaCore is evolving from a code generator into an application compiler.

The objective is to allow developers to describe an application once and have ArcaCore generate every layer consistently.

---

# Current Sprint

## Sprint 14 — Metadata Foundation

Status: In Progress

Objectives

- Expand Registry
- Version Registry
- Prepare relationship intelligence
- Strengthen metadata model

---

# Completed Milestones

## Foundation

- ✅ Project architecture
- ✅ Modular generator
- ✅ Parser
- ✅ Module definition
- ✅ SQLAlchemy renderer
- ✅ Template engine
- ✅ Automatic Black formatting

---

## Model Generation

- ✅ Model generation
- ✅ Schema generation
- ✅ CRUD generation
- ✅ Service generation
- ✅ Router generation

---

## ORM Intelligence

- ✅ Foreign keys
- ✅ Relationship generation
- ✅ back_populates generation
- ✅ Automatic timestamps

---

## Registry

- ✅ Metadata registry
- ✅ Automatic model registration

---

# Upcoming Sprints

## Sprint 15

Relationship Intelligence

- Reverse relationship discovery
- Relationship validation
- Relationship graph

---

## Sprint 16

Validation Engine

- Duplicate fields
- Duplicate tables
- Invalid foreign keys
- Reserved keywords
- Circular references

---

## Sprint 17

Migration Intelligence

- Schema comparison
- Migration planning
- Alembic generation

---

## Sprint 18

Database Features

- UUID support
- Enum support
- Composite indexes
- Soft deletes
- Audit metadata

---

## Sprint 19

Backend Intelligence

- Pagination
- Search
- Filtering
- Sorting
- Authorization metadata

---

## Sprint 20

Frontend Generation

- React pages
- Forms
- Tables
- API hooks
- TanStack Query

---

## Sprint 21

AI Compiler

- Prompt → Metadata
- Metadata → Application
- Visual Designer
- Plugin System

---

# Long-Term Goals

Generate complete applications including:

- Backend
- Frontend
- Database
- Documentation
- Tests
- Deployment

from a single metadata model.

---

# Guiding Principle

Every sprint should improve one of two things:

- ArcaCore understands applications better.

or

- ArcaCore generates applications better.

If a feature does neither, it should be reconsidered.