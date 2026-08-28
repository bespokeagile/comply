"""Every intra-package `from comply.X import Y` must resolve -- INCLUDING
function-local imports.

WHY THIS EXISTS, AND WHY IT IS NOT REDUNDANT WITH CI's import check.

The standalone carve-out left five call sites importing names that `tiers.py`
no longer defines. They sat broken for five months. CI's `lint` job runs
`from comply.app import create_comply_app` and it SUCCEEDS -- because every one
of those imports is FUNCTION-LOCAL, so nothing resolves them until the endpoint
is actually called. An import check that only imports the package is blind to
this class by construction, and a green check over a broken product is worse
than no check.

So the load-bearing property here is not "imports resolve". It is "the checker
walks FUNCTION BODIES". `ast.walk` does; a scan of `tree.body` does not. That
distinction is what `test_checker_sees_function_local_imports` pins, because a
checker that silently only saw module-level imports would return clean and read
as a pass.

SHRINK-ONLY RATCHET. The 12 unresolved targets below are the live defect as of
s577, frozen verbatim rather than fixed here: fixing them is a separate change
with its own plan and its own ordering constraints. What this forbids is a
THIRTEENTH. Entries may only be removed.

Keyed on (file, module, name) with the LINE NUMBER DELIBERATELY STRIPPED. A
line-keyed baseline turns every edit above a site into a false red, which is how
a ratchet gets disabled by the first person it inconveniences.
"""
import ast
import os

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_NAME = "comply"

SKIP_DIRS = {
    ".git", "__pycache__", "_vendor", "dist", "build", "node_modules",
    "tests", ".venv", "venv", "ci", "dashboard", "docs", ".pytest_cache",
}

# The live defect at s577, frozen. SHRINK ONLY -- never add.
# Every entry is a real break behind a real route or CLI path; see
# design_comply_carveout_completion_s577.md for the repair sequence.
BASELINE = {
    # R3 (s577) repaid the config half: __main__.py and the two pure-config
    # routes now read comply.config. Those entries were REMOVED here rather
    # than left standing, which is what test_baseline_only_shrinks forces.
    ("app.py", "comply.mcp_server", "_handle_alice_message"),
    ("routes_scan.py", "comply.tiers", "_is_managed"),
    ("routes_scan.py", "comply.tiers", "_load_config"),
    ("scanner.py", "comply.tiers", "TIERS"),
}
BASELINE_OCCURRENCES = 6


def _module_files(root=PKG_ROOT):
    """Map importable module name -> path, for the package's own modules."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            rel = os.path.relpath(path, root)
            name = rel[:-3].replace(os.sep, ".")
            if name.endswith(".__init__"):
                name = name[:-len(".__init__")]
            found[name] = path
    return found


def _names_defined_in(path):
    """Names a module exposes: defs, classes, assignments, and re-exports.

    Returns None if the file does not parse, so an unparseable module is
    reported as its own failure rather than silently resolving nothing.
    """
    try:
        tree = ast.parse(open(path, encoding="utf8", errors="replace").read())
    except SyntaxError:
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def unresolved_imports(root=PKG_ROOT):
    """Every intra-package import target that does not exist.

    Returns a list of (relpath, lineno, module, name). Uses ast.walk, so
    FUNCTION-LOCAL imports are included -- that is the whole point.
    """
    modules = _module_files(root)
    exports = {}
    bad = []
    for name, path in sorted(modules.items()):
        try:
            tree = ast.parse(open(path, encoding="utf8", errors="replace").read())
        except SyntaxError as exc:
            bad.append((os.path.relpath(path, root), exc.lineno or 0,
                        "<unparseable>", str(exc.msg)))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level:
                continue
            module = node.module or ""
            target = module[len(PKG_NAME) + 1:] if module.startswith(PKG_NAME + ".") else module
            if target not in modules:
                continue  # third-party or stdlib; not ours to resolve
            if target not in exports:
                exports[target] = _names_defined_in(modules[target])
            available = exports[target]
            if available is None:
                continue
            for alias in node.names:
                if alias.name != "*" and alias.name not in available:
                    bad.append((os.path.relpath(path, root), node.lineno,
                                module, alias.name))
    return bad


def _keys(found):
    return {(f, m, n) for f, _line, m, n in found}


class TestImportResolution:

    def test_no_new_unresolved_imports(self):
        """A thirteenth broken import is a regression. The twelve are frozen."""
        found = unresolved_imports()
        new = _keys(found) - BASELINE
        assert not new, (
            "New unresolved intra-package imports:\n"
            + "\n".join(f"  {f}:{line}  from {m} import {n}"
                        for f, line, m, n in sorted(found)
                        if (f, m, n) in new)
        )

    def test_baseline_only_shrinks(self):
        """Repairs must shrink the ledger; nothing may quietly grow it."""
        found = unresolved_imports()
        assert len(found) <= BASELINE_OCCURRENCES, (
            f"unresolved import occurrences grew: {len(found)} > {BASELINE_OCCURRENCES}"
        )
        stale = BASELINE - _keys(found)
        assert not stale, (
            "These baseline entries no longer fail and MUST be removed from "
            "BASELINE, or the ledger records debt that is already repaid and "
            "the shrink-only check can never register it:\n"
            + "\n".join(f"  {s}" for s in sorted(stale))
        )

    def test_checker_sees_function_local_imports(self, tmp_path):
        """CALIBRATION, and the load-bearing one.

        This test exists because the defect class it guards is invisible to a
        module-level scan. A checker that only read `tree.body` would return
        clean on the real tree and pass every other test in this file. Here the
        bad import is placed ONLY inside a function body, so the test can be
        satisfied by nothing except walking into it.
        """
        (tmp_path / "victim.py").write_text("EXISTS = 1\n")
        (tmp_path / "caller.py").write_text(
            "def f():\n"
            "    from comply.victim import DOES_NOT_EXIST\n"
            "    return DOES_NOT_EXIST\n"
        )
        found = unresolved_imports(str(tmp_path))
        assert ("caller.py", 2, "comply.victim", "DOES_NOT_EXIST") in found

    def test_checker_does_not_false_positive(self, tmp_path):
        """The other half: a name that DOES exist must not be reported.

        Without this, a checker that reported every import would pass the
        calibration above while being useless.
        """
        (tmp_path / "victim.py").write_text("EXISTS = 1\n\ndef helper():\n    pass\n")
        (tmp_path / "caller.py").write_text(
            "from comply.victim import EXISTS\n"
            "def f():\n"
            "    from comply.victim import helper\n"
            "    return helper, EXISTS\n"
        )
        assert unresolved_imports(str(tmp_path)) == []

    def test_third_party_imports_are_not_resolved(self, tmp_path):
        """Only OUR modules are checkable. Reporting stdlib or third-party
        names would make the ratchet noisy and it would be turned off."""
        (tmp_path / "caller.py").write_text(
            "from os.path import definitely_not_a_real_name\n"
        )
        assert unresolved_imports(str(tmp_path)) == []
