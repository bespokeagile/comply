# Comply CI/CD Integration

Run compliance scans automatically on every push or pull request.

## GitHub Actions

### Quick Start

Create `.github/workflows/comply.yml`:

```yaml
name: Compliance Scan
on:
  pull_request:
  push:
    branches: [main]

jobs:
  comply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run compliance scan
        uses: ./comply/ci/github-action.yml
        with:
          framework: eu-ai-act
          depth: content
```

### With Semantic Analysis (LLM-powered)

```yaml
      - name: Run compliance scan
        uses: ./comply/ci/github-action.yml
        with:
          framework: eu-ai-act,nist-ai-rmf
          depth: semantic
          llm-key: ${{ secrets.ANTHROPIC_API_KEY }}
          llm-provider: anthropic
          fail-below: '60'
          fail-on-regression: 'true'
```

### With External SARIF Merge

Run Semgrep (or any SAST tool) first, then merge its findings into the compliance report:

```yaml
      - name: Run Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          publishToken: ${{ secrets.SEMGREP_TOKEN }}

      - name: Run compliance scan + merge SARIF
        uses: ./comply/ci/github-action.yml
        with:
          framework: owasp-llm-top10
          depth: content
          sarif-path: semgrep.sarif
```

### Using Hosted API

Skip local installation by pointing to a hosted Comply instance:

```yaml
      - name: Run compliance scan (hosted)
        uses: ./comply/ci/github-action.yml
        with:
          framework: eu-ai-act
          api-url: https://comply-demo.bespokeagile.com
```

### Action Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `framework` | `eu-ai-act` | Framework(s), comma-separated |
| `depth` | `content` | `structure`, `content`, or `semantic` |
| `fail-below` | *(none)* | Score threshold (0-100). Leave empty to always pass. |
| `fail-on-regression` | `false` | Fail on new compliance gaps |
| `llm-key` | *(none)* | API key for semantic analysis |
| `llm-provider` | `anthropic` | `anthropic`, `openai`, `gemini`, `grok` |
| `sarif-path` | *(none)* | SARIF file from another tool to merge with results |
| `upload-sarif` | `true` | Upload SARIF to GitHub Code Scanning |
| `post-comment` | `true` | Post summary as PR comment |
| `working-directory` | `.` | Path to the repository to scan |
| `api-url` | *(none)* | Hosted API URL (omit to run locally) |

### Action Outputs

| Output | Description |
|--------|-------------|
| `score` | Compliance score (0-100) |
| `report-path` | Path to JSON report |
| `sarif-path` | Path to SARIF report |

---

## GitLab CI

### Quick Start

Add to `.gitlab-ci.yml`:

```yaml
include:
  - local: comply/ci/gitlab-ci-template.yml

comply-scan:
  extends: .comply-scan
  variables:
    COMPLY_FRAMEWORK: "eu-ai-act"
    COMPLY_FAIL_BELOW: "50"
```

### With Semantic Analysis

```yaml
comply-scan:
  extends: .comply-scan
  variables:
    COMPLY_FRAMEWORK: "eu-ai-act,nist-ai-rmf"
    COMPLY_DEPTH: "semantic"
    COMPLY_LLM_KEY: $ANTHROPIC_API_KEY
    COMPLY_LLM_PROVIDER: "anthropic"
    COMPLY_FAIL_BELOW: "60"
    COMPLY_FAIL_ON_REGRESSION: "true"
```

### With External SARIF Merge

```yaml
comply-scan:
  extends: .comply-scan
  variables:
    COMPLY_FRAMEWORK: "owasp-llm-top10"
    COMPLY_SARIF_PATH: "semgrep.sarif"
```

### Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPLY_FRAMEWORK` | `eu-ai-act` | Framework(s), comma-separated |
| `COMPLY_DEPTH` | `content` | Scan depth |
| `COMPLY_FAIL_BELOW` | *(none)* | Score threshold |
| `COMPLY_FAIL_ON_REGRESSION` | `false` | Fail on regressions |
| `COMPLY_LLM_KEY` | *(none)* | API key (use CI/CD variables) |
| `COMPLY_LLM_PROVIDER` | `anthropic` | LLM provider |
| `COMPLY_MAX_FILES` | `500` | Max files to scan |
| `COMPLY_SARIF_PATH` | *(none)* | External SARIF file to merge |

### GitLab Features

- **JUnit integration**: Test results appear in merge request widgets
- **Artifacts**: Reports stored for 30 days
- **Variables**: Use CI/CD settings for secrets

---

## Generic CI/CD

For any CI system, use the CLI directly:

```bash
# Install
pip install bespoketracker-comply

# Scan with score threshold
python -m comply scan . --framework eu-ai-act --fail-below 50

# SARIF output (GitHub Code Scanning, VS Code)
python -m comply scan . --format sarif -o ./reports

# JUnit output (most CI systems)
python -m comply scan . --format junit -o ./reports

# Markdown output (PR comments)
python -m comply scan . --format markdown > compliance.md

# Import external SARIF with architectural enrichment
python -m comply import semgrep.sarif --framework owasp-llm-top10 --repo .

# Regression detection
python -m comply baseline --auto --framework eu-ai-act
python -m comply scan . --fail-on-regression
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Scan passed (score >= threshold, no regressions) |
| 1 | Scan failed (score < threshold, or regression detected) |
| 2 | Error (scan could not complete) |

---

## Compliance Badge

Add a live compliance badge to your README:

```markdown
![Comply](https://your-comply-server/gate/badge/eu_ai_act)
![Comply](https://your-comply-server/gate/badge/nist_ai_rmf?repo=my-repo)
```

The badge shows the latest scan score for the given framework. Colors: green (70+), yellow (40-69), red (<40).

---

## Pre-commit Hook

Run a quick compliance check before every commit:

```bash
# Install
cp comply/ci/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Configure (optional, via environment)
export COMPLY_FRAMEWORK=eu-ai-act    # default
export COMPLY_DEPTH=structure         # fast, default
export COMPLY_FAIL_BELOW=50           # threshold, default none
```

The hook uses `structure` depth by default for speed (<10s). Skip with `git commit --no-verify`.
