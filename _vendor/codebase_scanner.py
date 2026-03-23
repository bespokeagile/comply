"""Standalone codebase scanner — reimplements essential parts of
connectors/codebase_connector.py without Kuzu dependency.

Returns a CodebaseModel dict compatible with the compliance evaluator.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Default exclude patterns
_DEFAULT_EXCLUDES = [
    "node_modules/**", ".git/**", "__pycache__/**", "*.pyc",
    ".env", "*.min.js", "*.min.css", "dist/**", "build/**",
    ".next/**", "vendor/**", "*.lock", "*.whl", "*.egg-info/**",
]

# Language detection by extension
_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
    ".scala": "scala", ".r": "r", ".R": "r",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    ".toml": "toml", ".md": "markdown", ".html": "html",
    ".css": "css", ".sql": "sql", ".sh": "shell",
    ".dockerfile": "docker", ".tf": "terraform",
}

# Regex patterns for content-depth extraction
_PATTERNS = {
    "route": re.compile(r'(?:@(?:app|router|api)\.(get|post|put|delete|patch)|(?:app|router)\.(get|post|put|delete|patch)\()', re.I),
    "class": re.compile(r'^\s*(?:class|interface|struct|enum)\s+(\w+)', re.M),
    "function": re.compile(r'^\s*(?:def|function|func|fn|fun|async\s+def|async\s+function)\s+(\w+)', re.M),
    "import": re.compile(r'^\s*(?:import|from|require|use|include|#include)\s+(.+)', re.M),
    "todo": re.compile(r'(?:TODO|FIXME|HACK|XXX)\s*[:\-]?\s*(.+)', re.I),
    "test": re.compile(r'^\s*(?:def test_|it\(|describe\(|test\(|#\[test\])', re.M),
    "config": re.compile(r'(?:\.env|config\.|settings\.|\.yaml|\.yml|\.toml|\.json)', re.I),
}


def scan_codebase(
    repo_path: str,
    scan_depth: str = "content",
    max_files: int = 500,
    max_file_size_kb: int = 100,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    llm_provider: str = "anthropic",
    llm_api_key: str = "",
    llm_model: str = "",
) -> Dict[str, Any]:
    """Scan a codebase and return a CodebaseModel dict.

    Parameters
    ----------
    repo_path : str
        Absolute path to the repo root.
    scan_depth : str
        "structure", "content", or "semantic".
    max_files : int
        Maximum files to process.
    max_file_size_kb : int
        Skip files larger than this.
    include_patterns, exclude_patterns : list or None
        Glob include/exclude filters.
    llm_provider, llm_api_key, llm_model : str
        For semantic depth: LLM config.

    Returns
    -------
    dict
        CodebaseModel with files, features, relationships, stats.
    """
    excludes = (exclude_patterns or []) + _DEFAULT_EXCLUDES
    includes = include_patterns or []

    # Walk and collect files
    files = _walk_files(repo_path, includes, excludes, max_files, max_file_size_kb)
    log.info("Collected %d files from %s", len(files), repo_path)

    # Extract per-file metadata
    file_infos = []
    lang_counts: Dict[str, int] = {}
    features: List[Dict] = []
    relationships: List[Dict] = []

    for fpath, rel_path in files:
        ext = os.path.splitext(fpath)[1].lower()
        lang = _LANG_MAP.get(ext, "other")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

        info: Dict[str, Any] = {
            "path": rel_path,
            "language": lang,
            "size_bytes": os.path.getsize(fpath),
        }

        if scan_depth in ("content", "semantic"):
            try:
                with open(fpath, "r", errors="replace") as f:
                    content = f.read(max_file_size_kb * 1024)
                extracted = _extract_content(content, rel_path)
                info.update(extracted)

                # Generate features from significant files
                if extracted.get("classes") or extracted.get("functions") or extracted.get("routes"):
                    feature = {
                        "code": f"F-{len(features)+1:03d}",
                        "label": _feature_label(rel_path, extracted),
                        "source_file": rel_path,
                        "language": lang,
                        "type": "code",
                    }
                    features.append(feature)
            except Exception as exc:
                log.debug("Failed to read %s: %s", fpath, exc)
        elif scan_depth == "structure":
            # Lightweight extraction: read first ~8KB for imports,
            # function defs, and test indicators. This unlocks
            # import-based evidence counting for the free tier
            # without full content parsing.
            try:
                with open(fpath, "r", errors="replace") as f:
                    head = f.read(8192)
                extracted = _extract_lightweight(head, rel_path)
                if extracted:
                    info.update(extracted)
            except Exception as exc:
                log.debug("Failed to read head of %s: %s", fpath, exc)

        file_infos.append(info)

    # Semantic depth: LLM analysis of top files
    if scan_depth == "semantic" and llm_api_key:
        _enrich_semantic(file_infos, features, repo_path, llm_provider, llm_api_key, llm_model)

    # Build relationships from imports
    for info in file_infos:
        for imp in info.get("imports", []):
            for other in file_infos:
                if _import_matches(imp, other["path"]):
                    relationships.append({
                        "from": info["path"],
                        "to": other["path"],
                        "type": "imports",
                    })

    # Extract dependency information from manifest files
    dependencies = _extract_dependencies(files, repo_path)

    return {
        "files": file_infos,
        "features": features,
        "relationships": relationships,
        "dependencies": dependencies,
        "file_count": len(file_infos),
        "feature_count": len(features),
        "language_breakdown": lang_counts,
        "scan_depth": scan_depth,
    }


def _walk_files(
    root: str,
    includes: List[str],
    excludes: List[str],
    max_files: int,
    max_file_size_kb: int,
) -> List[Tuple[str, str]]:
    """Walk directory tree, returning (absolute_path, relative_path) tuples."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [
            d for d in dirnames
            if not any(fnmatch.fnmatch(os.path.join(rel_dir, d) + "/", pat) for pat in excludes)
            and not d.startswith(".")
        ]

        for fname in filenames:
            if len(result) >= max_files:
                return result

            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, root)

            # Exclude check
            if any(fnmatch.fnmatch(rel_path, pat) for pat in excludes):
                continue

            # Include check (if specified)
            if includes and not any(fnmatch.fnmatch(rel_path, pat) for pat in includes):
                continue

            # Size check
            try:
                size = os.path.getsize(fpath)
                if size > max_file_size_kb * 1024:
                    continue
                if size == 0:
                    continue
            except OSError:
                continue

            # Skip binary files
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".whl",
                        ".tar", ".gz", ".zip", ".png", ".jpg", ".gif", ".ico",
                        ".woff", ".woff2", ".ttf", ".eot", ".pdf"):
                continue

            result.append((fpath, rel_path))

    return result


def _extract_content(content: str, rel_path: str) -> Dict[str, Any]:
    """Extract structural metadata from file content."""
    result: Dict[str, Any] = {"line_count": content.count("\n") + 1}

    # Routes
    routes = _PATTERNS["route"].findall(content)
    if routes:
        result["routes"] = [r[0] or r[1] for r in routes[:20]]

    # Classes
    classes = _PATTERNS["class"].findall(content)
    if classes:
        result["classes"] = classes[:20]

    # Functions
    functions = _PATTERNS["function"].findall(content)
    if functions:
        result["functions"] = functions[:30]

    # Imports
    imports = _PATTERNS["import"].findall(content)
    if imports:
        result["imports"] = [i.strip().split()[0].rstrip(";") for i in imports[:50]]

    # TODOs
    todos = _PATTERNS["todo"].findall(content)
    if todos:
        result["todos"] = [t.strip()[:100] for t in todos[:10]]

    # Test indicators
    tests = _PATTERNS["test"].findall(content)
    if tests:
        result["has_tests"] = True
        result["test_count"] = len(tests)

    # Config indicators
    if _PATTERNS["config"].search(rel_path):
        result["is_config"] = True

    return result


def _extract_lightweight(head: str, rel_path: str) -> Dict[str, Any]:
    """Extract imports, function names, and test indicators from the first ~8KB.

    This is the structure-depth counterpart to _extract_content(). It reads
    only the file head (imports cluster at the top) and applies a subset of
    patterns: imports, function defs, and test markers. This unlocks
    import-based evidence counting (e.g., _count_files_importing) for
    structure scans without the cost of full content parsing.
    """
    result: Dict[str, Any] = {}

    # Imports — almost always in the first 100 lines
    imports = _PATTERNS["import"].findall(head)
    if imports:
        result["imports"] = [i.strip().split()[0].rstrip(";") for i in imports[:50]]

    # Function definitions — captures module-level functions from the head
    functions = _PATTERNS["function"].findall(head)
    if functions:
        result["functions"] = functions[:30]

    # Test indicators — test_ defs in the head are strong signals
    tests = _PATTERNS["test"].findall(head)
    if tests:
        result["has_tests"] = True
        result["test_count"] = len(tests)

    return result


def _feature_label(rel_path: str, extracted: Dict) -> str:
    """Generate a human-readable feature label from file metadata."""
    parts = os.path.splitext(os.path.basename(rel_path))[0]
    # Convert snake_case or camelCase to words
    words = re.sub(r'[_\-]', ' ', parts)
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', words)
    classes = extracted.get("classes", [])
    if classes:
        return f"{words.title()} ({classes[0]})"
    return words.title()


def _import_matches(imp: str, file_path: str) -> bool:
    """Check if an import string could refer to a file path."""
    # Normalise both
    imp_norm = imp.replace(".", "/").replace("\\", "/").strip("'\"")
    path_norm = file_path.replace("\\", "/")
    stem = os.path.splitext(path_norm)[0]
    return imp_norm.endswith(stem) or stem.endswith(imp_norm)


# ── Dependency extraction ─────────────────────────────────────────

_DEP_FILES = {"requirements.txt", "requirements-dev.txt", "requirements_dev.txt",
              "pyproject.toml", "setup.cfg", "Pipfile", "package.json"}

_RE_REQUIREMENTS = re.compile(
    r'^([a-zA-Z0-9_\-\.]+)\s*(?:(\[.*?\])\s*)?(?:([=<>!~]+)\s*([0-9][0-9a-zA-Z.\-*]*))?',
)


def _extract_dependencies(
    walked_files: List[Tuple[str, str]],
    root: str,
) -> List[Dict[str, Any]]:
    """Parse dependency manifest files and return a list of dependency dicts.

    Each dict: {name, version, ecosystem, source, pinned}.
    """
    deps: List[Dict[str, Any]] = []
    seen_files: set = set()

    for fpath, rel_path in walked_files:
        basename = os.path.basename(rel_path)
        # Match requirements*.txt files
        if basename.startswith("requirements") and basename.endswith(".txt"):
            if rel_path not in seen_files:
                seen_files.add(rel_path)
                deps.extend(_parse_requirements_txt(fpath, rel_path))
        elif basename in _DEP_FILES:
            if rel_path not in seen_files:
                seen_files.add(rel_path)
                if basename == "pyproject.toml":
                    deps.extend(_parse_pyproject_toml(fpath, rel_path))
                elif basename == "setup.cfg":
                    deps.extend(_parse_setup_cfg(fpath, rel_path))
                elif basename == "package.json":
                    deps.extend(_parse_package_json(fpath, rel_path))
                elif basename == "Pipfile":
                    deps.extend(_parse_requirements_txt(fpath, rel_path))

    return deps


def _parse_requirements_txt(fpath: str, rel_path: str) -> List[Dict[str, Any]]:
    """Parse requirements.txt-style files."""
    results = []
    try:
        with open(fpath, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                m = _RE_REQUIREMENTS.match(line)
                if m:
                    name = m.group(1)
                    operator = m.group(3) or ""
                    version = m.group(4) or ""
                    results.append({
                        "name": name,
                        "version": version,
                        "ecosystem": "PyPI",
                        "source": rel_path,
                        "pinned": operator == "==",
                    })
    except OSError as exc:
        log.debug("Failed to read requirements file %s: %s", rel_path, exc)
    return results


def _parse_pyproject_toml(fpath: str, rel_path: str) -> List[Dict[str, Any]]:
    """Parse pyproject.toml dependencies using regex (no tomllib needed)."""
    results = []
    try:
        with open(fpath, "r", errors="replace") as f:
            content = f.read()
        # Find dependencies = [...] block
        m = re.search(r'dependencies\s*=\s*\[([^\]]*)\]', content, re.DOTALL)
        if m:
            block = m.group(1)
            for item in re.findall(r'"([^"]+)"|\'([^\']+)\'', block):
                dep_str = item[0] or item[1]
                dm = _RE_REQUIREMENTS.match(dep_str.strip())
                if dm:
                    results.append({
                        "name": dm.group(1),
                        "version": dm.group(4) or "",
                        "ecosystem": "PyPI",
                        "source": rel_path,
                        "pinned": (dm.group(3) or "") == "==",
                    })
    except (OSError, ValueError) as exc:
        log.debug("Failed to parse pyproject.toml %s: %s", rel_path, exc)
    return results


def _parse_setup_cfg(fpath: str, rel_path: str) -> List[Dict[str, Any]]:
    """Parse setup.cfg install_requires."""
    results = []
    try:
        with open(fpath, "r", errors="replace") as f:
            content = f.read()
        # Find install_requires block
        m = re.search(r'install_requires\s*=\s*\n((?:\s+.+\n)*)', content)
        if m:
            for line in m.group(1).strip().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                dm = _RE_REQUIREMENTS.match(line)
                if dm:
                    results.append({
                        "name": dm.group(1),
                        "version": dm.group(4) or "",
                        "ecosystem": "PyPI",
                        "source": rel_path,
                        "pinned": (dm.group(3) or "") == "==",
                    })
    except (OSError, ValueError) as exc:
        log.debug("Failed to parse setup.cfg %s: %s", rel_path, exc)
    return results


def _parse_package_json(fpath: str, rel_path: str) -> List[Dict[str, Any]]:
    """Parse package.json dependencies + devDependencies."""
    results = []
    try:
        with open(fpath, "r", errors="replace") as f:
            data = json.load(f)
        for section in ("dependencies", "devDependencies"):
            deps = data.get(section, {})
            if not isinstance(deps, dict):
                continue
            for name, ver_spec in deps.items():
                ver = ver_spec.lstrip("^~>=<! ")
                pinned = not any(c in ver_spec for c in ("^", "~", ">", "<", "*", "x"))
                results.append({
                    "name": name,
                    "version": ver,
                    "ecosystem": "npm",
                    "source": rel_path,
                    "pinned": pinned,
                })
    except (OSError, ValueError) as exc:
        log.debug("Failed to parse package.json %s: %s", rel_path, exc)
    return results


def _enrich_semantic(
    file_infos: List[Dict],
    features: List[Dict],
    repo_path: str,
    provider: str,
    api_key: str,
    model: str,
) -> None:
    """Use LLM to enrich top files with semantic analysis."""
    from comply._vendor.llm_client import call_llm

    # Score files by "density" (classes + functions + routes)
    scored = []
    for info in file_infos:
        score = (
            len(info.get("classes", [])) * 3
            + len(info.get("functions", []))
            + len(info.get("routes", [])) * 2
        )
        scored.append((score, info))
    scored.sort(key=lambda x: -x[0])

    # Analyse top 5 files in full
    for score, info in scored[:5]:
        fpath = os.path.join(repo_path, info["path"])
        try:
            with open(fpath, "r", errors="replace") as f:
                content = f.read(50000)
        except Exception:
            continue

        prompt = (
            f"Analyze this source file and describe:\n"
            f"1. Its primary purpose (1 sentence)\n"
            f"2. Key features/capabilities it provides\n"
            f"3. Compliance-relevant aspects (logging, auth, data handling)\n"
            f"4. Risk indicators (hardcoded secrets, missing validation, etc.)\n\n"
            f"File: {info['path']}\n```\n{content[:30000]}\n```"
        )
        response = call_llm(prompt, provider=provider, api_key=api_key, model=model)
        if response:
            info["semantic_analysis"] = response
            # Add as enriched feature
            features.append({
                "code": f"F-{len(features)+1:03d}",
                "label": f"[Semantic] {info['path']}",
                "source_file": info["path"],
                "analysis": response,
                "type": "semantic",
            })
