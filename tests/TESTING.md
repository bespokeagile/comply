# Comply Test Suite

## Quick start

```bash
# Run all tests (~7s)
pytest tests/comply/ -v

# Run only fast tests (skip funded scans + perf benchmarks)
pytest tests/comply/ -m "comply and not slow"

# Run only snapshot tests
pytest tests/comply/ -m snapshot

# Update snapshots after intentional changes
pytest tests/comply/ --update-snapshots
```

## Architecture

Tests use **deterministic seeding** — every persona produces identical data across runs.
No real API keys, servers, or LLM calls are needed.

| Component | How it works |
|-----------|-------------|
| **Database** | `SeedContext(seed)` in `comply/test_seed.py` produces repeatable UUIDs, timestamps, scores |
| **TestClient** | FastAPI's in-process `TestClient` — no subprocess or port needed |
| **Store isolation** | `conftest.py` patches `comply.store._DB_DIR` to `tmp_path` per test |
| **LLM calls** | Mocked via `unittest.mock.patch` on `comply.narration.*` |
| **Funded scans** | Real SQLite credit flow, scanner mocked via `comply.scanner.run_comply_scan` |
| **Snapshots** | JSON files in `tests/comply/snapshots/` — committed to git |

## Persona fixtures

Each fixture creates an isolated database seeded with a specific user profile:

| Fixture | Persona | Contains |
|---------|---------|----------|
| `new_user_client` | Empty database | Nothing — tests zero-state behavior |
| `single_repo_client` | 1 repo, 3 scans | Basic scan history |
| `journey_client` | 1 repo, 7 scans, gates, monitors | Full lifecycle data |
| `multi_repo_client` | 5 repos, programs | Portfolio/posture testing |
| `power_user_client` | 12 repos, heavy data | Performance benchmarks |
| `funded_client` | Empty + funded env vars | Funded scan credit system |

## Adding a new test

1. Pick the right fixture for your test (see table above)
2. Add `pytestmark = [pytest.mark.comply]` at module level
3. If your test compares structured output, use `assert_snapshot(actual, "name", update=update_snapshots)`
4. If your test takes >1s, add `pytest.mark.slow`

## Snapshot workflow

When you intentionally change an API response shape:

```bash
# Regenerate all snapshots
pytest tests/comply/ --update-snapshots

# Review what changed
git diff tests/comply/snapshots/

# Commit the updated snapshots alongside your code change
```

If a snapshot test fails on CI, it means the API response changed without updating the snapshot.
This is the intended behavior — it forces deliberate review of contract changes.

## File layout

```
tests/comply/
├── conftest.py              # Fixtures, store patching, snapshot infra
├── snapshots/               # Committed JSON snapshots (deterministic)
├── test_health_config.py    # Health, frameworks, config, capabilities
├── test_export.py           # JSON/SARIF/JUnit/Markdown export
├── test_persistence.py      # Stored scan access (Bug #2 regressions)
├── test_diff_regression.py  # Diff, baseline, regression detection
├── test_posture_mapping.py  # Posture, mapping, matrix, jurisdictions
├── test_programs.py         # Program CRUD lifecycle
├── test_gates_monitors.py   # Gate decisions, monitors, alerts, daemon
├── test_import.py           # SARIF/SBOM/JUnit import
├── test_forecasting.py      # Confidence decay, entanglement forecast
├── test_narration.py        # LLM narration + chat (mocked)
├── test_funded.py           # Funded scan credit system (mocked scanner)
├── test_edge_cases.py       # 404s, validation errors
└── test_performance.py      # Latency benchmarks (power_user persona)
```
