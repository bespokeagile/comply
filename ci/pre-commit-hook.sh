#!/usr/bin/env bash
# BespokeTracker Comply — Pre-commit hook
#
# Runs a quick compliance scan before each commit.
# Install: cp comply/ci/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#
# Configuration (environment variables):
#   COMPLY_FRAMEWORK   - Framework to scan (default: eu-ai-act)
#   COMPLY_DEPTH       - Scan depth: structure, content (default: structure)
#   COMPLY_FAIL_BELOW  - Score threshold (default: none, always passes)
#   COMPLY_MAX_FILES   - Max files to scan (default: 200)
#
# To skip: git commit --no-verify

set -e

FRAMEWORK="${COMPLY_FRAMEWORK:-eu-ai-act}"
DEPTH="${COMPLY_DEPTH:-structure}"
MAX_FILES="${COMPLY_MAX_FILES:-200}"
FAIL_BELOW="${COMPLY_FAIL_BELOW:-}"

# Check if comply is installed
if ! python -m comply --help >/dev/null 2>&1; then
    echo "comply: not installed (pip install bespoketracker-comply). Skipping."
    exit 0
fi

echo "comply: scanning against ${FRAMEWORK} (${DEPTH} depth)..."

ARGS=". --framework ${FRAMEWORK} --depth ${DEPTH} --max-files ${MAX_FILES} --no-cache"

if [ -n "${FAIL_BELOW}" ]; then
    ARGS="${ARGS} --fail-below ${FAIL_BELOW}"
fi

python -m comply scan ${ARGS}
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "comply: compliance check failed (exit ${EXIT_CODE})"
    echo "comply: fix issues above or skip with: git commit --no-verify"
    exit 1
fi

echo "comply: passed"
