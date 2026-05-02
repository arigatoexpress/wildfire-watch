# tests/

Cross-module integration tests for wildfire-watch. Module-level unit tests
stay co-located with their module:

  - `sim/tests/`
  - `sim/swarm/tests/`
  - `sapphire_integration/tak/tests/`
  - `valuation/tests/`

`tests/` is reserved for tests that exercise more than one module — wiring,
end-to-end flow, schema-vs-emitter contracts, and similar.

## Running

```bash
# All integration tests
/usr/local/bin/python3 -m pytest tests/integration -q

# Whole repo (unit + integration)
/usr/local/bin/python3 -m pytest -q
```

The `integration` job in `.github/workflows/ci.yml` runs `pytest tests/integration -q`
on every push and PR.

## Adding a new integration test

1. Drop a `test_*.py` file in `tests/integration/`.
2. Keep it under ~30 seconds. The integration job is a serial blocker.
3. Use stdlib + pytest + pyyaml + flask only. No new pip deps without
   weighing them against the cost of slowing down CI.
4. Lazy-import optional deps (`jsonschema`, `requests`, `flask`) inside the
   test body so the test still collects when the dep is missing.
5. Use `tmp_path` (pytest's per-test temp dir fixture) for any output —
   never write to `~/wildfire-watch-flights/` or anywhere outside the
   repo / temp.
6. Use seeded scenarios for determinism — pass `seed=0` to
   `RunnerConfig` / `SwarmRunnerConfig`.
7. Don't add emoji.
