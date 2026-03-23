"""URL normalization for rescan recognition."""

import re


def normalize_repo_url(url: str) -> str:
    """Canonicalize a repo URL for matching.

    Strips .git suffix, trailing slashes, lowercases, removes auth tokens.

    Examples:
        https://github.com/owner/repo.git -> https://github.com/owner/repo
        https://github.com/owner/repo/   -> https://github.com/owner/repo
        HTTPS://GitHub.com/Owner/Repo    -> https://github.com/owner/repo
        git@github.com:owner/repo.git    -> github.com/owner/repo
    """
    if not url:
        return ""

    s = url.strip()

    # Convert SSH URLs to a path form
    ssh_match = re.match(r'^git@([^:]+):(.+)$', s)
    if ssh_match:
        s = f"{ssh_match.group(1)}/{ssh_match.group(2)}"

    # Remove protocol
    s = re.sub(r'^https?://', '', s)

    # Remove auth tokens (user:token@)
    s = re.sub(r'^[^@]+@', '', s)

    # Lowercase
    s = s.lower()

    # Strip .git suffix
    if s.endswith('.git'):
        s = s[:-4]

    # Strip trailing slashes
    s = s.rstrip('/')

    return s
