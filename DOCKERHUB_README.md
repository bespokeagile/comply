# Comply — AI Compliance Scanner

Comply scans your codebase against 10 compliance frameworks (117 controls) and produces an evidence-backed posture report with remediation guidance.

## Quick Start

```bash
docker run -d \
  -p 8001:8001 \
  -v comply-data:/root/.comply \
  -e COMPLY_LLM_KEY=sk-... \
  ntsalzman/comply
```

Dashboard at [localhost:8001](http://localhost:8001). Bring your own LLM API key (Anthropic, OpenAI, Gemini, or Grok).

## Frameworks

| Framework | Controls |
|-----------|----------|
| EU AI Act | 8 |
| NIST AI RMF 1.0 | 12 |
| ISO/IEC 42001:2023 | 10 |
| SOC 2 (AI) | 6 |
| OWASP LLM Top 10 | 34 |
| OWASP Agentic Top 10 | 30 |
| Insurance AI Attestation | 5 |
| California AB 2013 | 3 |
| California SB 942 | 4 |
| Colorado SB 24-205 | 5 |

## Features

- **Three-layer evidence**: code analysis, process maturity, runtime governance
- **30 evidence functions** detecting logging, access control, testing, prompt protection, and more
- **Remediation roadmap** with prioritized, graph-aware code suggestions
- **6 export formats**: JSON, SARIF, JUnit, Markdown, DOCX, ZIP audit bundle
- **AppSec integration**: import SARIF/SBOM/JUnit findings, 74 CWE-to-control mappings
- **CI/CD**: GitHub Actions, GitLab CI, pre-commit hook, `comply gate` command
- **7 audit log adapters**: Gateway, GitHub Actions, GitLab CI, Kong, Gravitee, Vanta, File
- **Continuous monitoring**: `comply watch` and `comply monitor` for ongoing compliance

## Configuration

Set your LLM key via the web UI, environment variable, or exec into the container:

```bash
docker exec -it <container> comply config set llm_api_key sk-...
docker exec -it <container> comply config set llm_provider anthropic
```

Scan history and configuration persist in the `/root/.comply` volume.

## Also Available

- **PyPI**: `pip install bespoketracker-comply`
- **GitHub**: [bespokeagile/comply](https://github.com/bespokeagile/comply) (BSL-1.1)
- **Docs**: [bespokeagile.com/comply/docs](https://bespokeagile.com/comply/docs/)
- **Live Demo**: [bespokeagile-comply-demo.fly.dev](https://bespokeagile-comply-demo.fly.dev/)
