#!/bin/bash
# Comply MCP Server launcher
# Uses local venv (Python 3.12 + mcp package) and sets PYTHONPATH
# so comply modules are importable without the mcp/ directory collision.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

export PYTHONPATH="$REPO_DIR:${PYTHONPATH:-}"

# Use venv Python (mcp package requires Python 3.10+)
exec "$SCRIPT_DIR/.venv/bin/python" -m comply.mcp_server "$@"
