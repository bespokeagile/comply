"""Incremental scanning: detect changes, map impact, selective re-evaluation.

Given a baseline scan and a current repo state, determines which compliance
controls need re-evaluation and which can be carried forward from the baseline.
Uses _STRATEGY_MAP from remediation.py as the reverse index: each strategy's
keywords/import_hints/fn_hints define which file patterns trigger which
evidence functions.
"""

import os
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple


# ── Manifest files that affect dependency-based evidence functions ─────────

_MANIFEST_FILES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock", "build.gradle", "pom.xml",
    "composer.json", "composer.lock",
}

# Evidence functions that check dependencies / supply chain
_DEPENDENCY_EVIDENCE_FNS = {
    "evidence_ai_supply_chain",
    "evidence_model_provenance",
}


# ── Change Detection ──────────────────────────────────────────────────────

def detect_changes(repo_path: str, baseline_sha: str) -> Optional[Dict]:
    """Detect file-level changes between baseline commit and current HEAD.

    Returns None if git diff cannot be computed (no git, invalid SHA, etc.).
    Returns a ChangeSummary dict on success.
    """
    if not baseline_sha or not os.path.isdir(os.path.join(repo_path, ".git")):
        return None

    try:
        # Get current HEAD SHA
        current_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        if not current_sha:
            return None

        # Same commit -- no changes
        if current_sha == baseline_sha:
            return {
                "baseline_sha": baseline_sha,
                "current_sha": current_sha,
                "changed": [],
                "added": [],
                "deleted": [],
                "renamed": [],
                "total_changed": 0,
            }

        # Get file-level diff
        result = subprocess.run(
            ["git", "diff", "--name-status", baseline_sha, current_sha],
            cwd=repo_path, capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            return None

        changed, added, deleted, renamed = [], [], [], []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            if status == "M":
                changed.append(parts[1])
            elif status == "A":
                added.append(parts[1])
            elif status == "D":
                deleted.append(parts[1])
            elif status.startswith("R"):
                # Renamed: old_path -> new_path
                renamed.append({"from": parts[1], "to": parts[2]})
                deleted.append(parts[1])
                added.append(parts[2])

        return {
            "baseline_sha": baseline_sha,
            "current_sha": current_sha,
            "changed": changed,
            "added": added,
            "deleted": deleted,
            "renamed": renamed,
            "total_changed": len(changed) + len(added) + len(deleted),
        }

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ── Impact Mapping ────────────────────────────────────────────────────────

def _tokenize_path(path: str) -> Set[str]:
    """Extract word-level tokens from a file path for keyword matching."""
    lower = path.lower()
    # Split on path separators, underscores, hyphens, dots
    tokens = set(re.split(r'[/_\-.\\\s]+', lower))
    # Also split camelCase
    tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', path))
    tokens.discard("")
    return tokens


def _is_manifest(path: str) -> bool:
    """Check if a file is a package manifest / dependency file."""
    basename = os.path.basename(path)
    return basename in _MANIFEST_FILES


def map_impact(changes: Dict, strategy_map: Dict) -> Dict:
    """Map file-level changes to affected evidence functions.

    Args:
        changes: Output from detect_changes()
        strategy_map: _STRATEGY_MAP from remediation.py

    Returns:
        ImpactAssessment with affected/unaffected evidence function sets.
    """
    if not changes or changes["total_changed"] == 0:
        return {
            "affected_fns": set(),
            "unaffected_fns": set(strategy_map.keys()),
            "manifest_changed": False,
            "affected_files": [],
            "details": {},
        }

    all_changed_files = changes["changed"] + changes["added"] + changes["deleted"]
    affected_fns = set()
    details = {}  # evidence_fn -> list of triggering files

    # Check if any manifest file changed (triggers dependency evidence fns)
    manifest_changed = any(_is_manifest(f) for f in all_changed_files)
    if manifest_changed:
        affected_fns.update(_DEPENDENCY_EVIDENCE_FNS & set(strategy_map.keys()))

    # For each changed file, check which strategies it triggers
    for filepath in all_changed_files:
        tokens = _tokenize_path(filepath)

        for efn, strategy in strategy_map.items():
            if efn in affected_fns:
                continue  # Already marked

            keywords = set(k.lower() for k in strategy.get("keywords", []))
            import_hints = set(k.lower() for k in strategy.get("import_hints", []))
            fn_hints = set(k.lower() for k in strategy.get("fn_hints", []))

            # Check if file path tokens match any strategy keywords
            matched = False
            if tokens & keywords:
                matched = True
            elif tokens & import_hints:
                matched = True
            elif tokens & fn_hints:
                matched = True

            if matched:
                affected_fns.add(efn)
                if efn not in details:
                    details[efn] = []
                details[efn].append(filepath)

    # New files are conservatively treated as potentially matching any evidence fn
    # that checks for file existence patterns (docs, configs, etc.)
    # But we don't want to mark everything affected for a single new file.
    # The keyword matching above handles this well enough.

    # Deleted files: if a file that was providing evidence is removed,
    # the evidence function must be re-evaluated. The keyword matching
    # covers this since deleted files are in all_changed_files.

    unaffected_fns = set(strategy_map.keys()) - affected_fns

    return {
        "affected_fns": affected_fns,
        "unaffected_fns": unaffected_fns,
        "manifest_changed": manifest_changed,
        "affected_files": all_changed_files,
        "details": details,
    }


# ── Incremental Report Building ──────────────────────────────────────────

def build_incremental_report(
    baseline_report: Dict,
    fresh_report: Dict,
    impact: Dict,
) -> Dict:
    """Merge baseline (carried forward) and fresh (re-evaluated) results.

    Controls whose evidence_fn is in impact["affected_fns"] use fresh results.
    All other controls carry forward from baseline.
    Each control gets an `evaluation_source` tag.

    Args:
        baseline_report: The previous full scan report
        fresh_report: A new scan report (may be partial or full)
        impact: Output from map_impact()

    Returns:
        Merged report with evaluation_source annotations and incremental metadata.
    """
    affected_fns = impact.get("affected_fns", set())

    # Build lookup of fresh controls by controlId
    fresh_controls = {}
    for article in fresh_report.get("articles", []):
        for ctrl in article.get("controls", []):
            fresh_controls[ctrl["controlId"]] = ctrl

    # Merge articles
    merged_articles = []
    total_reevaluated = 0
    total_carried = 0

    for article in baseline_report.get("articles", []):
        merged_controls = []
        for ctrl in article.get("controls", []):
            efn = ctrl.get("evidence_fn", "")
            cid = ctrl["controlId"]

            if efn in affected_fns and cid in fresh_controls:
                # Use fresh evaluation
                merged_ctrl = dict(fresh_controls[cid])
                merged_ctrl["evaluation_source"] = "incremental"
                total_reevaluated += 1
            else:
                # Carry forward from baseline
                merged_ctrl = dict(ctrl)
                merged_ctrl["evaluation_source"] = "carried_forward"
                total_carried += 1

            merged_controls.append(merged_ctrl)

        # Recompute article-level counts
        met = sum(1 for c in merged_controls if c.get("status") == "met")
        partial = sum(1 for c in merged_controls if c.get("status") == "partial")
        gap = sum(1 for c in merged_controls if c.get("status") == "gap")

        merged_articles.append({
            **{k: v for k, v in article.items() if k != "controls"},
            "met": met,
            "partial": partial,
            "gap": gap,
            "controls": merged_controls,
        })

    # Recompute summary
    all_controls = [c for a in merged_articles for c in a.get("controls", [])]
    total = len(all_controls)
    met = sum(1 for c in all_controls if c.get("status") == "met")
    partial = sum(1 for c in all_controls if c.get("status") == "partial")
    gap = sum(1 for c in all_controls if c.get("status") == "gap")
    score = round((met + 0.5 * partial) / total * 100, 1) if total > 0 else 0

    # Build merged report
    merged = dict(fresh_report)
    merged["articles"] = merged_articles
    merged["summary"] = {
        "met": met,
        "partial": partial,
        "gap": gap,
        "total": total,
        "score": score,
    }
    merged["incremental"] = {
        "baseline_id": baseline_report.get("scanId", ""),
        "baseline_sha": impact.get("baseline_sha", ""),
        "current_sha": impact.get("current_sha", ""),
        "files_changed": len(impact.get("affected_files", [])),
        "controls_reevaluated": total_reevaluated,
        "controls_carried_forward": total_carried,
        "evidence_fns_affected": sorted(impact.get("affected_fns", set())),
        "evidence_fns_carried": sorted(impact.get("unaffected_fns", set())),
    }

    return merged


# ── Preview (no evaluation, just impact assessment) ───────────────────────

def preview_impact(
    changes: Dict,
    strategy_map: Dict,
    baseline_report: Dict,
) -> Dict:
    """Preview the impact of changes without running any evaluation.

    Returns a summary suitable for UI display before the user commits to a scan.
    """
    impact = map_impact(changes, strategy_map)
    affected_fns = impact["affected_fns"]

    # Count controls affected
    controls_affected = 0
    controls_carried = 0
    affected_control_ids = []

    for article in baseline_report.get("articles", []):
        for ctrl in article.get("controls", []):
            if ctrl.get("evidence_fn", "") in affected_fns:
                controls_affected += 1
                affected_control_ids.append(ctrl["controlId"])
            else:
                controls_carried += 1

    return {
        "files_changed": changes["total_changed"],
        "files": {
            "changed": changes["changed"],
            "added": changes["added"],
            "deleted": changes["deleted"],
        },
        "controls_affected": controls_affected,
        "controls_carried": controls_carried,
        "controls_total": controls_affected + controls_carried,
        "affected_control_ids": affected_control_ids,
        "affected_evidence_fns": sorted(affected_fns),
        "manifest_changed": impact["manifest_changed"],
        "same_commit": changes["total_changed"] == 0,
    }
