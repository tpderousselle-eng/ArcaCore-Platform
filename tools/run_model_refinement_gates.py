"""Run every discovered unittest in isolated, module-preserving worker shards.

The manifest records every discovered test ID exactly once. Workers use the
current interpreter and standard unittest loading; no tests are filtered out.
Reports must be written outside the source tree. Existing tests may exercise
generators in their own temporary workspaces, as in ordinary unittest discovery.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item.id()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Gate reports must be outside the repository.")
    output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        ids = json.loads(args.worker.read_text(encoding="utf-8"))
        suite = unittest.defaultTestLoader.loadTestsFromNames(ids)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        summary = {"discovered": len(ids), "ran": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": [(test.id(), reason) for test, reason in result.skipped]}
        summary["passed"] = result.wasSuccessful() and result.testsRun == len(ids)
        args.worker.with_suffix(".result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 0 if summary["passed"] else 1
    if not 1 <= args.workers <= 6:
        parser.error("Use one to six workers.")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tools"), pattern=args.pattern)
    ids = list(flatten(suite))
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("Discovery returned duplicate IDs or no tests.")
    modules = {}
    for test_id in ids:
        modules.setdefault(test_id.split(".")[0], []).append(test_id)
    # This module asserts two-second real process startup behavior. Run it
    # without CPU-saturating authority replay workers; keep its tests unchanged.
    serial = modules.pop("test_runtime_harness", [])
    shards = [[] for _ in range(args.workers)]
    loads = [0] * args.workers
    def weight(module, group):
        # Scheduling estimates only: never affect discovery or assertions.
        slow = {"test_golden_matrix": 650, "test_determinism": 400,
            "test_arcadev_architecture_clarification": 400,
            "test_arcadev_architecture_approval": 550,
            "test_arcadev_architecture_models_handoff": 450,
            "test_arcadev_backend_generation": 400, "test_arcadev_state_generation": 250}
        return slow.get(module, 80 + 4 * len(group) if module.startswith("test_arcadev_") else 2 * len(group))
    # Preserve each module's fixtures and class setup in one process.
    for module, group in sorted(modules.items(), key=lambda pair: (-weight(*pair), pair[0])):
        index = min(range(args.workers), key=lambda i: loads[i])
        shards[index].extend(group)
        loads[index] += weight(module, group)
    if sorted([t for shard in shards for t in shard] + serial) != sorted(ids):
        raise ValueError("Shard manifest differs from complete discovery.")
    (output / "manifest.json").write_text(json.dumps(ids, indent=2), encoding="utf-8")
    def run(index, shard):
        path = output / f"shard-{index}.json"
        path.write_text(json.dumps(shard), encoding="utf-8")
        with (output / f"shard-{index}.log").open("w", encoding="utf-8") as log:
            process = subprocess.run([sys.executable, "-B", "-u", str(Path(__file__).resolve()),
                "--output", str(output), "--worker", str(path)], cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(f"Shard {index}: exit {process.returncode}, {len(shard)} discovered tests", flush=True)
        return process.returncode, path.with_suffix(".result.json")
    print(f"Discovered {len(ids)} tests across {len(modules)} modules; running {len(shards)} shards.", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for future in as_completed([executor.submit(run, i, shard) for i, shard in enumerate(shards)]):
            code, path = future.result()
            result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"passed": False}
            result["passed"] = code == 0 and result["passed"]
            result["exit"] = code
            results.append(result)
    if serial:
        code, path = run("serial-runtime", serial)
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"passed": False}
        result["passed"] = code == 0 and result["passed"]
        result["exit"] = code
        results.append(result)
    summary = {"discovered": len(ids), "ran": sum(r.get("ran", 0) for r in results),
        "failures": sum(r.get("failures", 0) for r in results), "errors": sum(r.get("errors", 0) for r in results),
        "skipped": [s for r in results for s in r.get("skipped", [])],
        "passed": all(r["passed"] for r in results), "shards": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "shards"}, indent=2), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
