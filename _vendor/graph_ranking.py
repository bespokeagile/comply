"""Graph-based file ranking for semantic scan file selection.

Computes structural importance metrics from the codebase dependency graph
(import relationships) and combines them with keyword relevance to select
better files for semantic analysis.

The insight: a file that sits at an architectural boundary, is imported by
many other modules, or connects different parts of the codebase is more
likely to contain compliance-relevant infrastructure than a file that
merely has "audit" in its name.

Metrics computed per file:
- in_degree: how many files import this one (infrastructure signal)
- out_degree: how many files this one imports (integration breadth)
- betweenness: sits on shortest paths between modules (gateway/middleware)
- pagerank: recursive importance (core system files)
- module_boundary: connects different top-level directories (cross-cutting)
- config_proximity: graph distance to config files (system-level behavior)
"""
from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple


def compute_graph_metrics(codebase_model: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Compute per-file graph metrics from the codebase model.

    Parameters
    ----------
    codebase_model : dict
        Output of scan_codebase() with files and relationships.

    Returns
    -------
    dict
        Mapping of file path -> {metric_name: value}.
    """
    files = codebase_model.get("files", [])
    relationships = codebase_model.get("relationships", [])

    if not files or not relationships:
        return {}

    # Build adjacency lists from filtered relationships
    all_paths = {f["path"] for f in files}
    adj_out = defaultdict(set)  # file -> files it imports
    adj_in = defaultdict(set)   # file -> files that import it

    for rel in relationships:
        src, dst = rel.get("from", ""), rel.get("to", "")
        if src in all_paths and dst in all_paths and src != dst:
            # Filter noisy edges: skip if the import is a single common
            # token (os, re, sys, etc.) that substring-matches many paths
            if _is_plausible_edge(src, dst, rel):
                adj_out[src].add(dst)
                adj_in[dst].add(src)

    # Identify config files and test files for proximity metrics
    config_files = set()
    test_files = set()
    for f in files:
        path = f["path"]
        if f.get("is_config") or _looks_like_config(path):
            config_files.add(path)
        if f.get("has_tests") or _looks_like_test(path):
            test_files.add(path)

    # Compute metrics
    metrics = {}
    nodes = list(all_paths)

    # Degree metrics (raw, normalized below)
    raw_in = {}
    raw_out = {}
    for path in nodes:
        raw_in[path] = len(adj_in.get(path, set()))
        raw_out[path] = len(adj_out.get(path, set()))

    # PageRank (iterative, ~20 iterations on <1000 nodes is instant)
    pr = _pagerank(nodes, adj_in, adj_out, iterations=20, damping=0.85)

    # Betweenness centrality (approximate: sample source nodes for large graphs)
    bc = _betweenness_centrality(nodes, adj_out, sample_limit=100)

    # Module boundary and config proximity
    mb = {}
    for path in nodes:
        mb[path] = _module_boundary_score(
            path, adj_out.get(path, set()), adj_in.get(path, set())
        )

    config_dist = _bfs_distance_to_set(nodes, adj_out, adj_in, config_files)

    # Normalize ALL metrics to [0, 1] range
    max_in = max(raw_in.values()) if raw_in else 1
    max_out = max(raw_out.values()) if raw_out else 1

    for path in nodes:
        dist = config_dist.get(path, 999)
        metrics[path] = {
            "in_degree": raw_in[path] / max_in if max_in > 0 else 0.0,
            "out_degree": raw_out[path] / max_out if max_out > 0 else 0.0,
            "pagerank": pr.get(path, 0.0),
            "betweenness": bc.get(path, 0.0),
            "module_boundary": mb[path],
            "config_proximity": 1.0 / (1.0 + dist) if dist < 999 else 0.0,
        }

    return metrics


def rank_files_for_evidence(
    files: List[Dict],
    evidence_fn: str,
    graph_metrics: Dict[str, Dict[str, float]],
    keyword_scores: Optional[Dict[str, float]] = None,
    top_n: int = 5,
) -> List[Dict]:
    """Rank files by combined keyword + graph relevance for an evidence function.

    Strategy: graph metrics BOOST keyword-matched files and SUPPLEMENT
    when keyword matches are sparse. Files with keyword matches always
    rank above files without, but graph metrics determine which
    keyword-matched files are most architecturally important. If fewer
    than top_n files have keyword matches, graph-only ranked files fill
    the remaining slots.

    Parameters
    ----------
    files : list
        File info dicts from codebase model.
    evidence_fn : str
        The evidence function name (e.g., "evidence_audit_logging").
    graph_metrics : dict
        Output of compute_graph_metrics().
    keyword_scores : dict or None
        Pre-computed keyword scores per file path (0 = no match).
        If None, only graph scores are used.
    top_n : int
        Number of files to return.

    Returns
    -------
    list
        Top N files sorted by combined relevance.
    """
    if not graph_metrics:
        return files[:top_n]

    # Get evidence-type affinity weights
    affinity = _EVIDENCE_AFFINITY.get(evidence_fn, _DEFAULT_AFFINITY)

    kw_matched = []   # (kw_score, graph_score, file) -- has keyword match
    graph_only = []   # (graph_score, file) -- no keyword match

    for f in files:
        path = f["path"]
        gm = graph_metrics.get(path, {})

        # Compute graph score from affinity-weighted metrics
        graph_score = sum(
            affinity.get(metric, 0.0) * gm.get(metric, 0.0)
            for metric in affinity
        )

        kw_score = keyword_scores.get(path, 0.0) if keyword_scores else 0.0

        if kw_score > 0:
            # Keyword-matched: rank by keyword score, break ties by graph
            kw_matched.append((kw_score, graph_score, f))
        else:
            graph_only.append((graph_score, f))

    # Sort keyword-matched by kw_score desc, then graph_score desc
    kw_matched.sort(key=lambda x: (-x[0], -x[1]))
    graph_only.sort(key=lambda x: -x[0])

    # Take keyword-matched first, fill remainder with graph-only
    result = [f for _, _, f in kw_matched[:top_n]]
    remaining = top_n - len(result)
    if remaining > 0:
        result.extend(f for _, f in graph_only[:remaining])

    return result


# ── Evidence-type affinity weights ────────────────────────────────

# Different graph positions suggest different evidence types.
# These weights are initial heuristics; Phase 4d evaluation will
# validate and tune them against correction data.

_DEFAULT_AFFINITY = {
    "in_degree": 0.3,
    "betweenness": 0.3,
    "pagerank": 0.2,
    "module_boundary": 0.1,
    "config_proximity": 0.1,
}

_EVIDENCE_AFFINITY = {
    # Audit logging: central infrastructure files that many modules use
    "evidence_audit_logging": {
        "in_degree": 0.4,
        "betweenness": 0.3,
        "pagerank": 0.2,
        "module_boundary": 0.05,
        "config_proximity": 0.05,
    },
    "evidence_traceability": {
        "in_degree": 0.4,
        "betweenness": 0.3,
        "pagerank": 0.2,
        "module_boundary": 0.05,
        "config_proximity": 0.05,
    },
    # Monitoring: high centrality, config-adjacent
    "evidence_continuous_monitoring": {
        "in_degree": 0.2,
        "betweenness": 0.2,
        "pagerank": 0.2,
        "module_boundary": 0.1,
        "config_proximity": 0.3,
    },
    # Access control: gateway/middleware files at module boundaries
    "evidence_human_oversight_gateway": {
        "in_degree": 0.2,
        "betweenness": 0.4,
        "pagerank": 0.1,
        "module_boundary": 0.2,
        "config_proximity": 0.1,
    },
    "evidence_access_control": {
        "in_degree": 0.2,
        "betweenness": 0.4,
        "pagerank": 0.1,
        "module_boundary": 0.2,
        "config_proximity": 0.1,
    },
    "evidence_logical_access": {
        "in_degree": 0.2,
        "betweenness": 0.4,
        "pagerank": 0.1,
        "module_boundary": 0.2,
        "config_proximity": 0.1,
    },
    # Performance measurement: test-adjacent, high PageRank
    "evidence_performance_measurement": {
        "in_degree": 0.1,
        "betweenness": 0.1,
        "pagerank": 0.4,
        "module_boundary": 0.1,
        "config_proximity": 0.3,
    },
    # Risk assessment: config-adjacent, cross-cutting
    "evidence_risk_assessment_gateway": {
        "in_degree": 0.1,
        "betweenness": 0.2,
        "pagerank": 0.2,
        "module_boundary": 0.2,
        "config_proximity": 0.3,
    },
    # Data handling: gateway files, config-adjacent
    "evidence_data_handling": {
        "in_degree": 0.1,
        "betweenness": 0.3,
        "pagerank": 0.2,
        "module_boundary": 0.2,
        "config_proximity": 0.2,
    },
    # Input/output validation: gateway/middleware
    "evidence_input_sanitization": {
        "in_degree": 0.15,
        "betweenness": 0.4,
        "pagerank": 0.15,
        "module_boundary": 0.2,
        "config_proximity": 0.1,
    },
    "evidence_output_validation": {
        "in_degree": 0.15,
        "betweenness": 0.4,
        "pagerank": 0.15,
        "module_boundary": 0.2,
        "config_proximity": 0.1,
    },
}


# ── Graph algorithms ──────────────────────────────────────────────

def _pagerank(
    nodes: List[str],
    adj_in: Dict[str, Set[str]],
    adj_out: Dict[str, Set[str]],
    iterations: int = 20,
    damping: float = 0.85,
) -> Dict[str, float]:
    """Simple iterative PageRank."""
    n = len(nodes)
    if n == 0:
        return {}

    pr = {node: 1.0 / n for node in nodes}

    for _ in range(iterations):
        new_pr = {}
        for node in nodes:
            rank_sum = 0.0
            for src in adj_in.get(node, set()):
                out_deg = len(adj_out.get(src, set()))
                if out_deg > 0:
                    rank_sum += pr[src] / out_deg
            new_pr[node] = (1 - damping) / n + damping * rank_sum
        pr = new_pr

    # Normalize to [0, 1]
    max_pr = max(pr.values()) if pr else 1.0
    if max_pr > 0:
        pr = {k: v / max_pr for k, v in pr.items()}
    return pr


def _betweenness_centrality(
    nodes: List[str],
    adj_out: Dict[str, Set[str]],
    sample_limit: int = 100,
) -> Dict[str, float]:
    """Approximate betweenness centrality via BFS from sampled sources.

    For graphs with <1000 nodes, this is fast. For larger graphs,
    we sample source nodes to keep it O(sample_limit * (V + E)).
    """
    bc = defaultdict(float)
    n = len(nodes)
    if n < 2:
        return dict(bc)

    # Sample sources if graph is large
    import random
    sources = nodes if n <= sample_limit else random.sample(nodes, sample_limit)

    for src in sources:
        # BFS from src
        dist = {src: 0}
        sigma = defaultdict(float)  # number of shortest paths
        sigma[src] = 1.0
        pred = defaultdict(list)    # predecessors on shortest paths
        queue = deque([src])
        order = []

        while queue:
            v = queue.popleft()
            order.append(v)
            for w in adj_out.get(v, set()):
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist.get(w) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        # Back-propagation
        delta = defaultdict(float)
        for w in reversed(order):
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != src:
                bc[w] += delta[w]

    # Normalize
    max_bc = max(bc.values()) if bc else 1.0
    if max_bc > 0:
        bc = {k: v / max_bc for k, v in bc.items()}
    return dict(bc)


def _module_boundary_score(
    path: str,
    imports: Set[str],
    imported_by: Set[str],
) -> float:
    """Score how much a file bridges different top-level directories."""
    my_module = _top_level_dir(path)
    neighbors = imports | imported_by
    if not neighbors:
        return 0.0

    other_modules = set()
    for n in neighbors:
        mod = _top_level_dir(n)
        if mod != my_module:
            other_modules.add(mod)

    # Score: fraction of neighbors in different modules
    return len(other_modules) / max(len(neighbors), 1)


def _bfs_distance_to_set(
    nodes: List[str],
    adj_out: Dict[str, Set[str]],
    adj_in: Dict[str, Set[str]],
    target_set: Set[str],
) -> Dict[str, int]:
    """BFS distance from each node to nearest node in target_set.

    Uses undirected traversal (both import directions).
    """
    if not target_set:
        return {n: 999 for n in nodes}

    dist = {}
    queue = deque()
    for t in target_set:
        if t in {n for n in nodes}:
            dist[t] = 0
            queue.append(t)

    while queue:
        v = queue.popleft()
        # Undirected: traverse both directions
        neighbors = adj_out.get(v, set()) | adj_in.get(v, set())
        for w in neighbors:
            if w not in dist:
                dist[w] = dist[v] + 1
                queue.append(w)

    return dist


# ── Helpers ───────────────────────────────────────────────────────

def _top_level_dir(path: str) -> str:
    """Extract the top-level directory from a relative path."""
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else ""


def _looks_like_config(path: str) -> bool:
    """Check if a file path looks like a config file."""
    base = os.path.basename(path).lower()
    return any(tok in base for tok in (
        "config", "settings", ".env", ".yaml", ".yml", ".toml",
        ".ini", ".cfg", "pyproject", "setup.cfg", "package.json",
    ))


def _looks_like_test(path: str) -> bool:
    """Check if a file path looks like a test file."""
    path_lower = path.lower()
    return any(tok in path_lower for tok in (
        "test_", "_test.", "tests/", "test/", "spec/", ".test.",
    ))


def _is_plausible_edge(src: str, dst: str, rel: Dict) -> bool:
    """Filter out noisy import-to-file matches.

    The codebase scanner's _import_matches() does substring matching,
    which produces false positives like `import re` matching any file
    with 're' in its path. We filter these by requiring:
    - The matched portion is at least 4 characters, OR
    - The import contains a path separator (dot/slash), OR
    - The destination is a .py/.js/.ts file (more likely a real module)
    """
    dst_ext = os.path.splitext(dst)[1].lower()
    # Code files are more likely real import targets
    if dst_ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java"):
        # Still filter very short stem matches
        stem = os.path.splitext(os.path.basename(dst))[0]
        return len(stem) >= 3
    # Non-code files matched by import are usually noise
    return False
