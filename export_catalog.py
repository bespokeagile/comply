"""Export pre-scanned demo results from SQLite into static JSON catalog files.

Usage:
    python3 -m comply.export_catalog

Reads from ~/.comply/scans.db and demo_repos.yaml, writes to
comply/dashboard/catalog/*.json.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import yaml


def _load_demo_repos() -> list:
    yaml_path = os.path.join(os.path.dirname(__file__), "demo_repos.yaml")
    if not os.path.isfile(yaml_path):
        return []
    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("repos", [])


def _make_catalog_id(slug: str, framework: str, depth: str) -> str:
    return f"catalog-{slug}-{framework}-{depth}"


def export():
    from comply.store import get_scan, list_scans

    repos = _load_demo_repos()
    if not repos:
        print("No repos found in demo_repos.yaml")
        return

    catalog_dir = os.path.join(os.path.dirname(__file__), "dashboard", "catalog")
    os.makedirs(catalog_dir, exist_ok=True)

    frameworks_index = {}
    total_exported = 0

    for repo in repos:
        slug = repo.get("slug", "")
        repo_url = repo.get("url", "")
        repo_name = repo.get("name", slug)
        frameworks = repo.get("frameworks", [])

        for fw in frameworks:
            scans = list_scans(framework=fw, limit=50)
            fw_scans = frameworks_index.setdefault(fw, [])

            for depth in ("structure", "semantic"):
                # Find best matching scan
                match = None
                for s in scans:
                    s_url = s.get("repo_url", "")
                    s_path = s.get("repo_path", "")
                    s_depth = s.get("scan_depth", "")
                    # Match depth: "content" maps to "structure"
                    effective = "semantic" if "semantic" in s_depth else "structure"
                    if effective != depth:
                        continue
                    if repo_url and (s_url == repo_url or slug in s_url or slug in s_path):
                        match = s
                        break

                if not match:
                    print(f"  SKIP {slug}/{fw}/{depth} -- no matching scan")
                    continue

                # Get full scan with report
                full = get_scan(match["id"])
                if not full or not full.get("report"):
                    print(f"  SKIP {slug}/{fw}/{depth} -- no report data")
                    continue

                report = full["report"]
                # Normalize scanDepth in report to match catalog depth
                report["scanDepth"] = depth
                catalog_id = _make_catalog_id(slug, fw, depth)
                score = (report.get("summary") or {}).get("score", 0)

                entry = {
                    "id": catalog_id,
                    "url": repo_url,
                    "repoSlug": slug,
                    "repoName": repo_name,
                    "framework": fw,
                    "score": score,
                    "depth": depth,
                    "timestamp": report.get("generatedAt", ""),
                    "source": "demo",
                    "report": report,
                }
                fw_scans.append(entry)
                total_exported += 1
                print(f"  OK   {slug}/{fw}/{depth} -> {catalog_id} (score={score:.1f})")

    # Write per-framework JSON files
    for fw, scans in frameworks_index.items():
        if not scans:
            continue
        fw_file = f"{fw}.json"
        path = os.path.join(catalog_dir, fw_file)
        with open(path, "w") as f:
            json.dump({
                "framework": fw,
                "version": "1.0.0",
                "scans": scans,
            }, f, indent=2)
        print(f"Wrote {path} ({len(scans)} scans)")

    # Write catalog index
    index = {
        "version": "1.0.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "frameworks": {},
    }
    for fw in sorted(frameworks_index.keys()):
        if frameworks_index[fw]:
            index["frameworks"][fw] = {
                "file": f"{fw}.json",
                "version": "1.0.0",
            }

    index_path = os.path.join(catalog_dir, "catalog_index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"\nWrote {index_path}")
    print(f"Total: {total_exported} scans exported across {len(frameworks_index)} frameworks")


if __name__ == "__main__":
    export()
