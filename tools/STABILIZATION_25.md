# Stabilization 25: Golden application matrix

Stabilization begins after Sprint 24.4 Health Checks, locally tested, committed,
and pushed to GitHub main as `b5bbe7b`.

| Increment | Status |
| --- | --- |
| 25.1 Golden Application Generation Matrix | Implemented; 8 dedicated and 315 discovery tests passed here; replacement ZIP prepared for local verification |
| 25.2 and later | Not started |

## 25.1 scope

The golden matrix generates five representative applications through the real
module pipeline:

1. Simple CRUD SaaS
2. E-commerce Product/Order
3. CRM Customer/Contact
4. Multi-tenant Workspace/User
5. An advanced combination of relationships, constraints, indexes, validation,
   computed and hybrid properties, encrypted fields, audit fields, optimistic
   versioning, and soft deletion

Every application is generated in its own temporary project root. The suite
checks all five generated layers, Python syntax, isolated imports, class and
module naming, registry completeness, schema/model/layer agreement,
deterministic complete replacement, module-order independence, pre-write
failure for invalid combinations, and cross-scenario isolation.

The canonical definitions live in `golden_matrix.py`; the executable contract
lives in `test_golden_matrix.py`. Neither the matrix nor its tests write to the
repository's `backend/` directory.

## Verification

Run the dedicated matrix:

```powershell
python -m unittest tools.test_golden_matrix -v
```

Run the complete generator suite:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

Stop after delivering Stabilization 25.1. Wait for the user's local test,
commit, and push result before starting 25.2 or any later increment.
