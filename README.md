# BespokeTracker Comply

**Compliance gap analysis for any codebase.** Scan any repository against 10 regulatory frameworks. Get evidence-backed compliance reports with specific file paths, control status, and remediation recommendations.

**Regulatory deadlines:** Colorado SB 24-205 (June 30, 2026) | EU AI Act (August 2, 2026)

[![PyPI version](https://img.shields.io/pypi/v/bespoketracker-comply)](https://pypi.org/project/bespoketracker-comply/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

## Install

```bash
# Standalone (pip)
pip install bespoketracker-comply

# From source
pip install -e ./comply

# With semantic analysis support
pip install bespoketracker-comply[semantic]
```

## Quick Start

```bash
# Scan a local repository
bespoketracker-comply scan /path/to/your/repo

# Scan a GitHub repository
bespoketracker-comply scan https://github.com/org/repo --framework eu-ai-act

# Multi-framework scan
bespoketracker-comply scan . --framework eu-ai-act,nist-ai-rmf,iso-42001

# Start the web dashboard
bespoketracker-comply serve
# Open http://localhost:8001

# Or run in background (returns to shell)
bespoketracker-comply serve --background

# Stop a background server
bespoketracker-comply stop
```

## Docker

```bash
# Build and run
docker build -t comply .
docker run -p 8001:8001 -v comply-data:/root/.comply comply

# With docker-compose (includes optional gateway sidecar)
docker compose up

# With gateway for three-layer evidence
docker compose --profile with-gateway up
```

## Supported Frameworks

| Framework | Controls | Description |
|-----------|----------|-------------|
| `eu-ai-act` | 8 | EU AI Act 2024/1689 (Articles 9-14) |
| `nist-ai-rmf` | 12 | NIST AI Risk Management Framework 1.0 |
| `iso-42001` | 10 | ISO/IEC 42001:2023 AI Management System |
| `california-ab-2013` | 3 | California AB 2013 AI Transparency Act |
| `california-sb-942` | 4 | California SB 942 AI Transparency |
| `colorado-sb-24-205` | 5 | Colorado SB 24-205 Consumer Protections |
| `soc2-ai` | 6 | SOC 2 AI Trust Services Criteria |
| `insurance-attestation` | 5 | Insurance AI Attestation (NAIC) |
| `owasp-llm-top10` | 10 | OWASP Top 10 for LLM Applications |
| `owasp-agentic-top10` | 10 | OWASP Agentic AI Top 10 |

## Three-Layer Evidence

Comply evaluates compliance across three layers:

1. **Layer 1 — Code**: Static analysis of your codebase (logging, tests, docs, auth, monitoring)
2. **Layer 2 — Process**: Development process maturity (baselines, regression tracking, CI gates)
3. **Layer 3 — Traffic**: AI agent governance (audit logs, access control, policy enforcement)

Layer 1 runs automatically. Layer 2 builds as you set baselines and track regressions. Layer 3 requires connecting audit log adapters.

### Audit Log Adapters

Connect external systems for Layer 3 evidence:

```yaml
# ~/.comply/config.yaml
adapters:
  gateway:
    mode: sqlite
    db_path: ./gateway.db
  kong:
    admin_url: http://localhost:8001
  gravitee:
    management_url: http://localhost:8083/management
  file:
    paths:
      - ./audit-logs/*.jsonl
```

```bash
# List adapters
bespoketracker-comply adapters list

# Test connectivity
bespoketracker-comply adapters test gateway

# Ingest records
bespoketracker-comply adapters ingest gateway
```

## CLI Reference

### `comply scan`

```
bespoketracker-comply scan <target> [options]

Options:
  -f, --framework FRAMEWORK  Framework(s), comma-separated (default: eu-ai-act)
  -d, --depth DEPTH          structure | content | semantic (default: content)
  -o, --output DIR           Output directory for reports
  --llm-key KEY              LLM API key (required for semantic depth)
  --llm-provider PROVIDER    anthropic | openai | gemini | grok
  --format FORMAT            terminal | json | sarif | junit | markdown
  --fail-below N             Exit 1 if score < N (for CI/CD)
  --fail-on-regression       Exit 1 if new gaps vs baseline
  --no-cache                 Skip scan model cache
```

### Other Commands

| Command | Description |
|---------|-------------|
| `serve [--port 8001] [--background]` | Start the web dashboard |
| `stop` | Stop a background server |
| `config show` | Show current configuration |
| `config set KEY VALUE` | Set a config value (e.g. `llm_api_key`, `llm_provider`) |
| `config path` | Print config file path |
| `frameworks` | List supported frameworks |
| `history [--repo PATH]` | Browse past scans |
| `diff SCAN1 SCAN2` | Compare two scans |
| `baseline --set ID` | Set compliance baseline |
| `cache stats\|clear` | Manage scan cache |
| `adapters list\|test\|ingest` | Manage audit log adapters |

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/scan` | Start a scan |
| `GET` | `/scan/{id}` | Poll scan status |
| `GET` | `/scan/{id}/report` | Get report JSON |
| `GET` | `/scan/{id}/download?fmt=` | Download (json/sarif/junit/markdown/docx/zip) |
| `GET` | `/scan/{id}/regression` | Regression check |
| `GET` | `/scan/{id}/progress` | Progress polling |
| `GET` | `/history` | Scan history |
| `GET` | `/diff?scan1=&scan2=` | Diff two scans |
| `GET` | `/adapters` | List adapters |
| `POST` | `/adapters/{name}/test` | Test adapter |
| `POST` | `/adapters/{name}/ingest` | Ingest records |
| `GET` | `/adapters/{name}/records` | Query records |
| `GET` | `/posture` | All-framework posture |
| `GET` | `/posture/{framework}` | Three-layer posture |
| `POST` | `/baseline/{id}` | Set baseline |
| `GET` | `/frameworks` | List frameworks |
| `POST` | `/audit` | Predicate gap audit (free) |
| `GET` | `/matrix?frameworks=` | Cross-framework matrix |
| `GET` | `/license` | License status |
| `POST` | `/license/activate` | Activate license key |
| `GET` | `/health` | Health + version |

## CI/CD Integration

### GitHub Actions

```yaml
- uses: ./comply/ci/github-action.yml
  with:
    framework: eu-ai-act
    fail-below: '50'
    upload-sarif: true
    post-comment: true
```

### GitLab CI

```yaml
include:
  - local: comply/ci/gitlab-ci-template.yml

comply-scan:
  extends: .comply-scan
  variables:
    COMPLY_FRAMEWORK: "eu-ai-act"
    COMPLY_FAIL_BELOW: "50"
```

### Generic CI

```bash
# Score gate
bespoketracker-comply scan . --fail-below 50

# SARIF for code scanning
bespoketracker-comply scan . --format sarif -o ./reports

# Regression detection
bespoketracker-comply baseline --auto
bespoketracker-comply scan . --fail-on-regression
```

## Standalone vs Monorepo

Comply works in two modes:

- **Standalone** (`pip install bespoketracker-comply`): Uses a vendored pure-Python scanner. No Kuzu or monorepo dependencies.
- **Monorepo**: When run inside the BespokeTracker monorepo, uses the full Kuzu-based pipeline for richer analysis.

Auto-detected at runtime — no configuration needed.

## Open Source: All Features Included

Comply is open source under the Apache 2.0 license. All features -- every framework, every scan depth, every export format -- are included with no feature gates.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Adding a New Framework

Framework definitions live in `data/frameworks.yaml` (CC-BY-4.0 licensed). To add a new framework:

1. Add the framework definition to `data/frameworks.yaml`
2. Map evidence functions in `_vendor/compliance_eval.py` `_EVIDENCE_FN_MAP`
3. Add tests in the test suite
4. Submit a PR

### Adding an Evidence Function

Evidence functions detect compliance-relevant patterns in codebases. See existing functions in `_vendor/compliance_eval.py` for the pattern.

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

Framework definitions (`data/frameworks.yaml`) are licensed under CC-BY-4.0.
