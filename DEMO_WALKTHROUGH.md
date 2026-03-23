# Comply Demo Walkthrough

**URL**: https://bespokeagile-comply-demo.fly.dev/
**Duration**: 10-15 minutes
**Audience**: CTO/CIO evaluating AI compliance tools

---

## Setup

- Open the demo URL in an incognito/private browser window (clean state)
- Have a second tab ready if you want to show the import flow
- Optional: have an API key ready for the semantic scan (Anthropic `sk-ant-...` or OpenAI `sk-...`)

---

## Act 1: The Free Scan (2 minutes)

**Goal**: Show instant value with zero friction.

1. **Land on the page** — note the privacy copy: "Your API key never touches our database"
2. **Enter a repo URL** — suggestions:
   - `https://github.com/langchain-ai/langchain` (AI framework, scores mid-range)
   - `https://github.com/vllm-project/vllm` (inference engine, interesting gaps)
   - `https://github.com/mlflow/mlflow` (ML platform, higher compliance maturity)
3. **Select a framework** — start with EU AI Act (the one everyone's asking about)
4. **Click "Run Free Scan"** — takes 30-60 seconds

**While scanning, talk through**:
- "This is a structure scan — we analyze file patterns, imports, dependencies, and the codebase graph. No AI, no API key, free."
- "We're evaluating against [X] controls from the EU AI Act."

5. **Results arrive** — walk through:
   - **Score gauge**: "This repo scores X% on EU AI Act compliance"
   - **Met/Partial/Gap breakdown**: "N controls are met, N partially, N are gaps"
   - **Click into an article** to expand controls
   - **Click a control** to see evidence: "Here's exactly what we found and where"

**Key talking point**: "You just got a compliance assessment in 60 seconds, for free, on a repo you've never scanned before."

---

## Act 2: The Semantic Upgrade (3 minutes)

**Goal**: Show the AI depth that justifies paid tiers.

*Skip this act if you don't have an API key — jump to Act 3.*

1. **Enter an API key** — the provider badge auto-detects (Anthropic/OpenAI/Gemini/Grok)
2. **Click "Run Full Scan"** — takes 2-3 minutes
3. **While scanning**: "Now Claude is reading the top-5 most relevant files for each gap control. It's not just matching keywords — it's understanding code intent."

4. **Results arrive** — the sidebar now shows both scans
5. **Click "Compare Scans"** — this is the money shot:
   - Side-by-side: structure vs semantic
   - Green highlights where semantic found evidence structure missed
   - Per-control delta: "Structure said gap, semantic says partial — here's what it found"
   - Semantic analysis text: "This middleware checks JWT tokens before forwarding requests to the model endpoint, constituting access control evidence"

**Key talking point**: "The compare view shows exactly what AI analysis adds. This isn't a black box — you can read the reasoning for every upgrade."

---

## Act 3: What To Do About It (3 minutes)

**Goal**: Transform assessment into action plan.

1. **Remediation tab** — click it
   - Phase lanes: Phase 1 (quick wins), Phase 2 (medium effort), Phase 3 (major work)
   - Each card shows: effort estimate, score delta, affected controls
   - **Score projection bar**: "If you do all quick wins, score goes from X% to Y%"

2. **What-if simulator** — check/uncheck items
   - "Select just the quick wins" — watch the projected score update live
   - "Add this medium-effort item" — score jumps again
   - "This lets you plan sprints around compliance impact"

3. **Code generation** — click "View Code Patch" on a remediation card
   - Shows a ready-to-use code template for the specific gap
   - Language-aware (Python/JS), parameterized with repo context

4. **Export tab** — show governance outputs:
   - "Full Compliance Report" — opens as printable HTML (PDF via browser print)
   - "Board Summary" — one-page executive view
   - "Evidence Binder" — structured Markdown for auditors

**Key talking point**: "We don't just tell you what's wrong. We tell you what to do, in what order, with what impact, and we generate the documents your auditor wants."

---

## Act 4: Import Existing Security Scans (2 minutes)

**Goal**: Show Comply as a compliance layer on top of existing tools.

1. **Scroll down to "or import existing results"** on the landing page
2. **Drop a SARIF file** (e.g., `test_imports/semgrep-ai-app.sarif`)
   - Auto-detects format: "SARIF — Semgrep — 12 findings detected"
   - Select framework, click "Map to Compliance"
   - Shows: findings mapped to compliance controls, CWE-to-control mapping
   - Architectural enrichment panel (if graph data available)

3. **Drop an SBOM file** (e.g., `test_imports/cyclonedx-ai-app.json`)
   - Auto-detects: "CycloneDX — 18 components detected"
   - Click "Analyze Supply Chain"
   - Shows: component inventory, AI/ML package detection, vulnerability mapping, license tracking

4. **Drop a JUnit file** (e.g., `test_imports/pytest-ai-platform.xml`)
   - Auto-detects: "JUnit XML — 34 tests detected"
   - Click "Analyze Test Evidence"
   - Shows: test results classified into compliance evidence categories, failed tests highlighted

**Key talking point**: "Your team already runs Semgrep, Trivy, or pytest. Comply maps those results to regulatory controls. You don't replace your security tools — you add a compliance lens on top."

---

## Act 5: Multi-Framework (1 minute)

**Goal**: Show efficiency across frameworks.

1. **Scan a second framework** on the same repo (e.g., OWASP LLM Top 10 after EU AI Act)
2. **Both scans appear in the sidebar** — click between them
3. If the overlap view is accessible: show the efficiency insight
   - "These 4 capabilities are shared across frameworks"
   - "Fixing audit logging satisfies requirements in EU AI Act AND OWASP LLM Top 10"
   - "35% effort reduction by addressing shared capabilities first"

**Key talking point**: "Most companies face multiple frameworks. We show you where they overlap so you fix things once, not three times."

---

## Closing (1 minute)

**Recap the value chain**:
1. Free scan in 60 seconds — know where you stand
2. AI semantic analysis — understand why
3. Remediation roadmap — know what to do
4. Import existing tools — leverage what you have
5. Governance exports — prove you did it
6. Rescan to show progress — demonstrate improvement

**The ask**: "Try it on your own repos. The free scan works on any public GitHub repo. For private repos, we offer a self-hosted option. Happy to do a deeper assessment if you want to go further."

---

## FAQ / Objections

**"How is this different from Snyk/SonarQube?"**
They find bugs. We map regulatory requirements to code. Complementary — in fact, you can import their SARIF output into Comply to add the compliance layer.

**"Is the free scan actually useful?"**
Yes. Our improvement loop data shows the free structure scan now matches semantic analysis within 1.6% on average. The gap is where AI genuinely adds value (reading code intent vs. matching patterns).

**"What about private repos?"**
Self-hosted: `pip install bespoketracker-comply` or Docker. Code never leaves your network.

**"Which frameworks do you support?"**
10 total: EU AI Act, NIST AI RMF, SOC 2 AI, ISO 42001, OWASP LLM Top 10, OWASP Agentic Top 10, plus 4 more in the self-hosted version.

**"How do I know the evidence functions are accurate?"**
Published methodology: 18-repo validation study, +27% improvement from correction loop, 0 regressions, 96.3% convergence. Full data in our research directory.
