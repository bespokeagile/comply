"""Git clone helper — resolve URL or local path to a scannable directory."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

_GIT_URL_RE = re.compile(
    r"^(?:https?://|git@|ssh://)"  # protocol prefixes
    r"|\.git$"                      # bare .git suffix
)


def is_git_url(target: str) -> bool:
    return bool(_GIT_URL_RE.search(target))


def clone_or_resolve(target: str, work_dir: str) -> str:
    """Return an absolute local path to the codebase.

    If *target* looks like a git URL, shallow-clone into *work_dir*/repo.
    If *target* is a local path, validate it exists and return it.
    """
    if is_git_url(target):
        dest = os.path.join(work_dir, "repo")
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        log.info("Cloning %s → %s", target, dest)
        try:
            subprocess.run(
                ["git", "clone", "--depth=1", "--single-branch", target, dest],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if "Authentication" in stderr or "Permission denied" in stderr:
                raise RuntimeError(
                    f"Authentication failed for {target}. "
                    "Clone the repo locally and pass the path instead."
                ) from exc
            raise RuntimeError(f"git clone failed: {stderr.strip()}") from exc
        except FileNotFoundError:
            raise RuntimeError("git is not installed or not on PATH")
        return dest

    # Local path
    path = os.path.abspath(target)
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Path not found: {path}")
    return path
