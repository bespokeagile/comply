# Contributing to BespokeTracker Comply

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/bespoketracker/comply.git
cd comply

# Install in development mode
pip install -e ".[semantic,docx]"

# Run the test suite (91 tests, ~7s)
pytest tests/comply/ -v

# Run only fast tests (skip funded scans + perf benchmarks)
pytest tests/comply/ -m "comply and not slow"

# Start the dev server with test data
./dev_server.sh
```

## Project Structure

```
comply/
  __main__.py           CLI entry point
  scanner.py            Core scan orchestration
  app.py                FastAPI web server
  routes.py             REST endpoints
  tiers.py              Tier gating (free/pro/enterprise)
  licensing.py          License key generation & validation
  billing.py            Stripe integration
  report.py             Terminal & file formatters
  formats.py            SARIF, JUnit, Markdown exports
  docx_report.py        DOCX report generator
  store.py              SQLite scan history
  cache.py              LRU model cache
  regression.py         Baseline regression detection
  evidence_layers.py    Three-layer evidence aggregation
  _vendor/
    codebase_scanner.py    Standalone codebase scanner
    compliance_eval.py     Evidence evaluation engine
    framework_loader.py    YAML framework loader
    llm_client.py          LLM provider abstraction
  adapters/             Audit log adapters (gateway, kong, gravitee, file)
  dashboard/            Web SPA (vanilla JS)
  data/
    frameworks.yaml     Framework definitions (CC-BY-4.0)
  ci/                   CI/CD templates (GitHub Actions, GitLab CI)
```

## How to Contribute

### Report Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- `bespoketracker-comply --version` output
- OS and Python version

### Add a Compliance Framework

1. Add the framework to `data/frameworks.yaml`:
   ```yaml
   your_framework_id:
     label: "Your Framework Name"
     version: "2024"
     description: "..."
     articles:
       section_name:
         label: "Section Label"
         controls:
           - id: "YF-1"
             requirement: "The system shall..."
             evidence_fn: "evidence_audit_logging"
   ```

2. If you need a new evidence function, add it to `_vendor/compliance_eval.py`:
   ```python
   def _evidence_your_function(req: str, model: Dict) -> Dict:
       files = model.get("files", [])
       # ... evaluate evidence ...
       return _make("met", ["evidence found"], file_evidence=[...])
   ```

3. Register it in `_EVIDENCE_FN_MAP` at the bottom of `compliance_eval.py`.

4. Add tests and submit a PR.

### Improve Evidence Detection

The core evidence evaluator is in `_vendor/compliance_eval.py`. Each evidence function:

1. Receives the full codebase model (files, features, relationships)
2. Searches for compliance-relevant patterns
3. Returns `met`, `partial`, or `gap` with specific evidence and file paths

To improve accuracy:
- Add import detection for new frameworks/libraries in `_detect_imports()`
- Add file pattern matching in `_file_has_keywords()`
- Reduce false positives by using word-boundary matching

### Write Tests

Tests live in `tests/comply/` with 91 deterministic tests across 13 files. See `tests/comply/TESTING.md` for the full contributor guide.

```bash
# Full suite
pytest tests/comply/ -v

# Snapshot tests only
pytest tests/comply/ -m snapshot

# Update snapshots after intentional API changes
pytest tests/comply/ --update-snapshots
```

### Dev Server for Manual Testing

`dev_server.sh` resets the database, seeds a test persona, and starts the server in background. It uses **isolated** storage (`~/.comply-dev`) and port (`9001`) so it never touches real user data in `~/.comply`.

```bash
# Interactive persona picker
./dev_server.sh

# Direct persona selection
./dev_server.sh journey      # full compliance journey (scan > remediate > gate > monitor)
./dev_server.sh multi_repo   # 5 repos, mixed frameworks, gates, monitors
./dev_server.sh power_user   # 12 repos, enterprise scenario

# Stop / check status
./dev_server.sh stop
./dev_server.sh status
```

| Environment | Port | Data directory | Purpose |
|-------------|------|---------------|---------|
| Production | 8001 | `~/.comply` | Real user data, `bespoketracker-comply serve` |
| Dev/test | 9001 | `~/.comply-dev` | Throwaway test data, `./dev_server.sh` |

Personas produce deterministic data, so the same persona always generates the same scans, scores, and history. This makes it easy to visually verify UI changes.

## Code Style

- Python 3.9+ compatible (`Optional[X]` not `X | None`)
- No runtime Kuzu dependency in the `comply/` package
- All new features must have tests
- Evidence functions should include `fileEvidence` with specific paths

## Pull Request Process

1. Fork the repo and create your branch from `main`
2. Add tests for new functionality
3. Ensure all tests pass (`pytest tests/ -v`)
4. Update README.md if adding new commands or endpoints
5. Submit the PR with a clear description

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Framework definitions in `data/frameworks.yaml` are licensed under CC-BY-4.0.
