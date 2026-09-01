# Contributing to ArcaCore

Version: 1.0

---

# Purpose

This document defines the development standards for ArcaCore.

Every contribution should improve consistency, maintainability, and predictability.

---

# Core Philosophy

ArcaCore is an application compiler.

Developers describe applications.

ArcaCore generates software.

---

# Architecture Rules

## Single Responsibility

Every module should have one responsibility.

Examples

Parser

- Understand developer input.

Renderer

- Convert metadata into framework-specific code.

Template

- Presentation only.

Generator

- Coordinate generation.

Registry

- Persist metadata.

---

## Templates

Templates should contain presentation only.

Avoid placing business logic inside Jinja templates.

Complex decisions belong in renderers.

---

## Renderers

Renderers own framework-specific syntax.

Examples

- SQLAlchemy
- Pydantic
- FastAPI
- React

Templates should never understand framework rules.

---

## Registry

The Registry is the single source of truth for project metadata.

Future generators should consume registry data whenever possible instead of reparsing generated code.

---

# Development Workflow

Every change should follow this sequence:

1. Replace the entire file.
2. Save.
3. Run a smoke test.
4. Verify generated output.
5. Commit.

Avoid mixing multiple architectural changes into one step.

---

# File Replacement Policy

When replacing source files:

- Replace the complete file.
- Avoid partial patches.
- Keep changes atomic.
- Keep each replacement focused on one concern.

This makes reviews, debugging, and rollback much simpler.

---

# Testing

Every completed feature should include a smoke test.

Examples:

```bash
python -m tools.generate Invoice ...
```

or

```bash
python -m tools.test_parser
```

Generated code should also be reviewed for correctness.

---

# Code Style

Generated Python code should always be:

- Black formatted
- Readable
- Deterministic
- Explicit

Avoid clever implementations that reduce readability.

---

# Documentation

Every major architectural decision should be reflected in:

- ARCHITECTURE.md
- ROADMAP.md

Documentation is considered part of the implementation.

---

# Future Contributions

When introducing a new feature, consider:

- Does it improve understanding?
- Does it improve generation?
- Does it belong in the parser?
- Does it belong in a renderer?
- Does it belong in the registry?

Keeping responsibilities separated is more important than minimizing the number of files.

---

# Long-Term Goal

ArcaCore should evolve into a complete application compiler capable of generating production-ready software from a structured metadata model.