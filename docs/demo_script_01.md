# AI-Guided Compliance in 90 Seconds

**Format**: Split screen -- Claude Code terminal (left), Comply dashboard (right)
**Target length**: 90 seconds
**Tone**: Calm, confident, no hype. Let the product speak.
**Audience**: Engineering leads and CTOs evaluating compliance tooling

---

## Pre-roll (0:00 - 0:05)

**Visual**: Black screen. Text fades in:

> "What if your AI already knew how to do compliance?"

*Transition*: Cut to split-screen layout. Terminal left, dashboard right.

**Dashboard state**: Landing page showing the Comply sidebar with "AI Connected" indicator (green dot) visible in the sidebar footer. No scans loaded yet -- clean slate.

---

## Scene 1: The Ask (0:05 - 0:25)

### LEFT -- Terminal (Claude Code)

**User types:**

```
I need to check if my AI project meets EU AI Act requirements
```

**Claude responds** (text streams in):

> I'll scan your project against the EU AI Act. This framework covers 6 articles
> with 24 controls -- things like human oversight, transparency, data governance,
> and risk management.
>
> Let me run the scan now.

Claude calls `comply_scan`:
```
comply_scan(target=".", framework="eu-ai-act", depth="content")
```

**Result streams back:**
```json
{
  "scanId": "sc_7f3a...",
  "framework": "eu-ai-act",
  "score": 42,
  "met": 8,
  "partial": 6,
  "gap": 10,
  "total": 24,
  "dashboardUrl": "http://127.0.0.1:8001/#/detail/sc_7f3a..."
}
```

Claude summarizes:

> Your project scores **42/100** against the EU AI Act. You're meeting 8 of 24
> controls, 6 are partially covered, and 10 have gaps. The dashboard has your
> full breakdown.

### RIGHT -- Dashboard

**Bridge event**: `scan-complete` fires. Dashboard auto-navigates to detail view (`#/detail/sc_7f3a...`).

**What the viewer sees**:
1. Score gauge renders -- large circular gauge showing **42** in the center, purple ring partially filled
2. Summary bar appears: 8 met (green) | 6 partial (amber) | 10 gap (red)
3. Article accordion list loads below, showing per-article breakdowns:
   - Article 9: Risk Management -- 2 met, 1 partial, 2 gap
   - Article 10: Data Governance -- 1 met, 0 partial, 3 gap
   - Article 11: Technical Documentation -- 0 met, 2 partial, 1 gap
   - Article 13: Transparency -- 2 met, 1 partial, 1 gap
   - Article 14: Human Oversight -- 1 met, 1 partial, 2 gap
   - Article 15: Accuracy & Robustness -- 2 met, 1 partial, 1 gap

**Callout** (post-production): Subtle arrow or glow highlighting the "AI Connected" indicator in the sidebar footer, with caption: *"The dashboard follows the AI automatically"*

---

## Scene 2: The Gap (0:25 - 0:45)

### LEFT -- Terminal

**User types:**

```
What's my biggest gap?
```

**Claude responds** (streams in):

> Your biggest gap is **human oversight**. Article 14 requires that humans can
> monitor, intervene in, and override your AI system's decisions. Right now your
> codebase has no human-in-the-loop mechanism -- no override endpoint, no
> escalation path, no kill switch.
>
> This is a critical gap because it's a hard legal requirement, not a
> best-practice recommendation. Let me show you the exact control.

Claude calls `comply_show`:
```
comply_show(scan_id="sc_7f3a...", article_id="Article 14", control_id="14.1")
```

### RIGHT -- Dashboard

**Bridge event**: `highlight` fires with `articleId="Article 14"` and `controlId="14.1"`.

**What the viewer sees**:
1. Dashboard switches to the Controls tab
2. Article 14 accordion expands automatically
3. Control 14.1 row scrolls into view and pulses with the `ai-highlight` class (brief indigo glow effect)
4. Control detail row expands, showing:
   - **Status**: Gap (red badge)
   - **Requirement**: "Mechanisms for human review of AI decisions, escalation paths, override capabilities..."
   - **Recommendation**: "Implement a human oversight gateway with manual review triggers..."

**Callout**: Caption on the highlighted row: *"AI points. Dashboard follows."*

---

## Scene 3: The Fix (0:45 - 1:05)

### LEFT -- Terminal

**User types:**

```
How do I fix this?
```

**Claude responds** (streams in):

> Let me generate a prioritized remediation plan.

Claude calls `comply_remediate`:
```
comply_remediate(scan_id="sc_7f3a...")
```

**Result streams back** (Claude narrates the highlights):

> Here's your fix list, ordered by impact:
>
> **1. Add a human oversight gateway** (Control 14.1)
> Effort: Medium | Score impact: +12 points
> Create a review queue where flagged AI decisions wait for human approval.
> Add an `/api/review` endpoint that holds decisions above a confidence
> threshold and requires explicit sign-off before execution.
>
> **2. Implement audit logging** (Control 9.2)
> Effort: Low | Score impact: +8 points
> Add structured logging that captures who triggered the AI, what input it
> received, what it produced, and whether a human reviewed it. Write to an
> append-only log.
>
> **3. Add a transparency disclosure** (Control 13.1)
> Effort: Low | Score impact: +6 points
> Users interacting with your AI must be told they're interacting with an AI.
> Add a disclosure banner or API response header.
>
> Fixing just these three would bring you from **42 to 68** -- above the
> passing threshold for most audit frameworks.

### RIGHT -- Dashboard

**Bridge event**: `navigate` fires, keeping the detail view focused on scan `sc_7f3a...`.

**What the viewer sees**:
1. Dashboard remains on the detail view
2. The controls tab is active, showing the remediation context
3. The article accordions reflect the gap/partial/met status with color-coded badges

**Callout**: Caption over the terminal: *"Prioritized by impact. No compliance expertise needed."*

---

## Scene 4: The Export (1:05 - 1:20)

### LEFT -- Terminal

**User types:**

```
Generate the compliance report
```

**Claude responds:**

> I'll export your scan as a markdown report you can share with your team or
> auditor.

Claude calls `comply_export`:
```
comply_export(scan_id="sc_7f3a...", format="markdown")
```

**Result**: Claude confirms the export:

> Done. Your compliance report is ready:
>
> - **EU AI Act Compliance Report**
> - Repository: ./my-ai-project
> - Score: 42/100
> - 8 controls met, 6 partial, 10 gaps
> - Generated: 2026-03-15
>
> I can also export as SARIF for GitHub Security, JUnit for your CI pipeline,
> or JSON for programmatic use. Want me to set a baseline so we can track your
> progress over time?

### RIGHT -- Dashboard

**What the viewer sees**: Dashboard stays on the detail view. The Export tab is available in the tab bar (Overview | Controls | Layers | Regression | Export), reinforcing that the dashboard is a full reporting tool beyond the AI conversation.

**Callout**: Small badge next to export formats in the dashboard: *"SARIF, JUnit, Markdown, JSON"*

---

## Closing (1:20 - 1:30)

**Visual**: Split screen holds for a beat, then the terminal side fades to show three key messages stacked vertically:

> **No compliance expertise needed.**
> Your AI does the work.
> The dashboard follows along.

**Final frame**: Comply logo + tagline. URL: `comply.bespokeagile.com`

*Hold 3 seconds. Fade to black.*

---

## Production Notes

### Layout

- **Split ratio**: 55% terminal (left), 45% dashboard (right)
- **Terminal font**: SF Mono or JetBrains Mono, 14pt, dark background
- **Dashboard**: Use the default Comply dark theme (indigo/purple accent palette)
- Thin vertical divider line between the two panels, 1px, #333

### Camera and Recording

- Screen recording at 2x resolution (Retina), export at 1080p or 4K
- No camera/face -- this is a product demo, not a talking head
- If adding voiceover: male or female voice, measured pace, no excitement, slight warmth

### Transitions

- Scene-to-scene: 0.3s crossfade, no hard cuts
- Dashboard auto-navigation should be visible -- the viewer needs to see the page change happen in response to the AI, not cut to a new state
- Terminal text should stream character-by-character (not instant paste) to feel like a real AI conversation

### Callouts and Post-Production

- Use minimal callout overlays -- small, semi-transparent, bottom-right of each panel
- Callout font: system sans-serif, 11pt, white on dark translucent pill
- Highlight the "AI Connected" indicator in Scene 1 with a subtle zoom or glow
- In Scene 2, the `ai-highlight` CSS animation on control 14.1 should be clearly visible -- if needed, add a post-production glow ring around the row

### Timing

| Scene | Duration | Cumulative |
|-------|----------|------------|
| Pre-roll | 5s | 0:05 |
| Scene 1: The Ask | 20s | 0:25 |
| Scene 2: The Gap | 20s | 0:45 |
| Scene 3: The Fix | 20s | 1:05 |
| Scene 4: The Export | 15s | 1:20 |
| Closing | 10s | 1:30 |

Total: ~90 seconds. Can tighten to 75s by shortening Claude's responses in scenes 1 and 3. Can extend to 2 minutes by adding a Scene 2.5 where the user asks "Show me the other gaps too" and Claude walks through Article 10 (data governance).

### Audio

- Background: Minimal ambient music, low volume, no beat. Something like an Epidemic Sound "tech ambient" track.
- Terminal typing: Optional subtle keystroke sounds. Do not add sound effects to the dashboard transitions.
- Voiceover (if used): Record separately, mix at -6dB above music.

### What Must Be Real

Every tool call in this script uses real Comply MCP tools with real parameter signatures. To record authentically:

1. Clone a sample AI project (or use `bespoke-tracker` itself as the target)
2. Start the Comply server: `python -m comply.mcp_server`
3. Open the dashboard at `http://127.0.0.1:8001`
4. Open Claude Code in the terminal with the Comply MCP server connected
5. Type the prompts from the script -- Claude will call the real tools
6. The dashboard will auto-navigate via the SSE bridge

The score, control IDs, and article numbers will match whatever repo is actually scanned. Adjust the script's example numbers to match the real output. The narrative flow holds regardless of the specific score.

### Alternate Endings (if extending beyond 90s)

- **CI/CD path**: "Can I block deploys that fail compliance?" -> `comply_gate` with `min_score=60`
- **Multi-framework**: "How about SOC 2?" -> `comply_scan` with `framework="soc2-ai"`, dashboard shows second scan
- **Progress tracking**: "Set this as my baseline" -> `comply_baseline_set`, then show a rescan with `comply_diff`
