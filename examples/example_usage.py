"""
example_usage.py - Demonstrates how to use the Security Patcher modules.

Run from the project root:

    python examples/example_usage.py

The script demonstrates:
1. Local scanning with the root-level DependencyParser (dict output)
2. Using ScanResult / Dependency data models
3. Exporting results to JSON and CSV
4. Listing manifest paths with GitHubScanner (requires GITHUB_TOKEN)
"""

from __future__ import annotations

import json
import os
import sys

# Ensure the project root is importable when running this script directly.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from dependency_parser import DependencyParser
from src.exporters import to_csv, to_json
from src.models import Dependency, ScanResult

# ---------------------------------------------------------------------------
# Example 1: Local scan with the existing DependencyParser
# ---------------------------------------------------------------------------

print("=" * 60)
print("Example 1: Local scan (examples/ directory)")
print("=" * 60)

examples_dir = os.path.dirname(os.path.abspath(__file__))
parser = DependencyParser(local_path=examples_dir)
raw_result = parser.scan()

print(f"Manifests found : {len(raw_result['manifests'])}")
print(f"Total deps      : {raw_result['total_dependencies']}")
print()

# ---------------------------------------------------------------------------
# Example 2: Export raw result to JSON
# ---------------------------------------------------------------------------

print("=" * 60)
print("Example 2: Export raw scan result to JSON")
print("=" * 60)

json_output = to_json(raw_result)
print(json_output[:500])  # Print first 500 chars
print()

# ---------------------------------------------------------------------------
# Example 3: Export raw result to CSV
# ---------------------------------------------------------------------------

print("=" * 60)
print("Example 3: Export raw scan result to CSV")
print("=" * 60)

csv_output = to_csv(raw_result)
for line in csv_output.splitlines()[:6]:
    print(line)
print()

# ---------------------------------------------------------------------------
# Example 4: Build a ScanResult from scratch using data models
# ---------------------------------------------------------------------------

print("=" * 60)
print("Example 4: Build ScanResult with Dependency dataclasses")
print("=" * 60)

deps = [
    Dependency(
        name="requests",
        version="2.28.0",
        type="pip",
        source_file="requirements.txt",
        line_number=1,
        specifier="==",
    ),
    Dependency(
        name="flask",
        version="2.2.5",
        type="pip",
        source_file="requirements.txt",
        line_number=2,
        specifier=">=",
    ),
    Dependency(
        name="express",
        version="^4.18.0",
        type="npm",
        source_file="package.json",
    ),
]

result = ScanResult(
    repo_name="my-org/my-repo",
    manifest_files=["requirements.txt", "package.json"],
    dependencies=deps,
)

print(f"Repo          : {result.repo_name}")
print(f"Total deps    : {result.total_dependencies}")
print(f"Manifests     : {result.manifest_files}")
print()
print("JSON (first 400 chars):")
print(result.to_json()[:400])
print()
print("CSV:")
print(result.to_csv())

# ---------------------------------------------------------------------------
# Example 5: Remote GitHub scan (requires GITHUB_TOKEN env var)
# ---------------------------------------------------------------------------

print("=" * 60)
print("Example 5: Remote GitHub scan (skipped if no token)")
print("=" * 60)

github_token = os.getenv("GITHUB_TOKEN")
if not github_token:
    print("GITHUB_TOKEN not set – skipping remote scan example.")
    print("Set it and re-run to scan 'Bylerma/Security-Patcher' remotely.")
else:
    try:
        from github import Github

        from src.github_scanner import GitHubScanner

        gh = Github(github_token)
        repo = gh.get_repo("Bylerma/Security-Patcher")

        print(f"Listing manifests in {repo.full_name} …")
        scanner = GitHubScanner(repo)
        paths = scanner.list_manifest_paths()
        print(f"Manifest files: {paths}")

        if paths:
            print("Running full scan …")
            result = scanner.scan()
            print(f"Found {result.total_dependencies} dependencies across {len(result.manifest_files)} manifest(s).")
            if result.errors:
                print(f"Errors: {result.errors}")
    except Exception as exc:
        print(f"Remote scan failed (check token permissions): {type(exc).__name__}")
