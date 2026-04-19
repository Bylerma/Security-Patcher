# Dependency Parser – Full API Documentation

A production-ready dependency parser that scans repositories and extracts all
dependencies from multiple manifest file formats. This module serves as the
"Sensory Input" for the Security Vulnerability Patcher agent.

---

## Table of Contents

- [Supported Manifest Formats](#supported-manifest-formats)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Data Models](#data-models)
  - [Dependency](#dependency)
  - [ScanResult](#scanresult)
- [Local Scanning](#local-scanning)
- [Remote GitHub Scanning](#remote-github-scanning)
- [Output Formats](#output-formats)
  - [JSON](#json)
  - [CSV](#csv)
  - [Python dict](#python-dict)
- [CLI Interface](#cli-interface)
- [Configuration](#configuration)
- [Error Handling Guide](#error-handling-guide)
- [Extending the Parser](#extending-the-parser)

---

## Supported Manifest Formats

| File | Ecosystem | Specifier tracking | Line numbers |
|------|-----------|--------------------|--------------|
| `requirements.txt` | Python / pip | ✅ | ✅ |
| `package.json` | Node.js / npm | — | — |
| `Gemfile` | Ruby / gem | ✅ | ✅ |
| `go.mod` | Go | — | ✅ |
| `pom.xml` | Java / Maven | — | — |
| `Cargo.toml` | Rust / cargo | — | — |

---

## Project Structure

```
Security-Patcher/
├── src/
│   ├── __init__.py          # Public API re-exports
│   ├── config.py            # Extended configuration (adds NOTION_TOKEN)
│   ├── models.py            # Dependency & ScanResult dataclasses
│   ├── dependency_parser.py # (root) Core manifest parsers
│   ├── github_scanner.py    # Remote GitHub API scanner
│   ├── exporters.py         # JSON / CSV / dict export helpers
│   └── main.py              # Enhanced CLI entry point
├── tests/
│   ├── __init__.py
│   ├── test_dependency_parser.py
│   ├── test_models.py
│   └── test_github_scanner.py
├── examples/
│   ├── sample_requirements.txt
│   ├── sample_package.json
│   └── example_usage.py
├── requirements.txt
├── .env.example
├── setup.py
└── README_PARSER.md         # ← this file
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Bylerma/Security-Patcher.git
cd Security-Patcher

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# Or install the package in development mode
pip install -e .
```

---

## Quick Start

```python
from dependency_parser import DependencyParser
from src.exporters import to_json, to_csv

# ── Local scan ──────────────────────────────────────────────────────────────
parser = DependencyParser(local_path="/path/to/repo")
raw = parser.scan()
print(to_json(raw))          # Pretty-printed JSON
print(to_csv(raw))           # CSV with header row

# ── Remote GitHub scan ───────────────────────────────────────────────────────
from github import Github
from src.github_scanner import GitHubScanner

gh = Github("ghp_token")
repo = gh.get_repo("owner/repo")

scanner = GitHubScanner(repo, branch="main")
result = scanner.scan()
print(result.to_json())
```

---

## Data Models

### Dependency

```python
@dataclass
class Dependency:
    name: str          # Package name, e.g. "requests"
    version: str       # Version string, e.g. "2.28.0"; empty when unpinned
    type: str          # Ecosystem: "pip" | "npm" | "gem" | "go" | "maven" | "cargo"
    source_file: str   # Repo-relative path to the manifest file
    line_number: int   # 1-based line in source_file; 0 when not tracked
    specifier: str     # Operator: "==" | ">=" | "~>" | …; empty when absent
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Plain dict representation |
| `to_json(indent=2)` | `str` | JSON string |
| `from_dict(data)` | `Dependency` | Reconstruct from dict (classmethod) |

#### Example

```python
from src.models import Dependency

dep = Dependency(
    name="requests",
    version="2.28.0",
    type="pip",
    source_file="requirements.txt",
    line_number=1,
    specifier="==",
)

print(dep.to_dict())
# {'name': 'requests', 'version': '2.28.0', 'type': 'pip',
#  'source_file': 'requirements.txt', 'line_number': 1, 'specifier': '=='}
```

---

### ScanResult

```python
@dataclass
class ScanResult:
    repo_name: str              # Repository identifier or local path
    scan_time: datetime         # UTC timestamp (auto-set)
    manifest_files: list[str]   # Discovered manifest file paths
    dependencies: list[Dependency]
    errors: list[str]           # Non-fatal parse errors
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `total_dependencies` | `int` | `len(dependencies)` |

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Plain dict representation |
| `to_json(indent=2)` | `str` | JSON string |
| `to_csv()` | `str` | CSV string (header + one row per dependency) |
| `from_dict(data)` | `ScanResult` | Reconstruct from dict (classmethod) |

---

## Local Scanning

Use the root-level `DependencyParser` for local file-system scanning.

```python
from dependency_parser import DependencyParser

parser = DependencyParser(local_path="/path/to/repo")
result = parser.scan()
# Returns: {"manifests": [...], "total_dependencies": N, "scan_source": "local"}
```

The result is a plain dict compatible with all exporter functions.

### Scanning a nested monorepo

```python
# Will recursively walk all sub-directories
parser = DependencyParser(local_path="/path/to/monorepo")
result = parser.scan()
```

### Limiting manifest types

```python
# Only look for Python manifests
parser = DependencyParser(
    local_path="/path/to/repo",
    manifest_files=["requirements.txt"],
)
result = parser.scan()
```

---

## Remote GitHub Scanning

Use `GitHubScanner` to scan a repository without a local clone.

```python
from github import Github
from src.github_scanner import GitHubScanner
from src.models import ScanResult

gh = Github("ghp_your_token")
repo = gh.get_repo("owner/repo")

# Default branch
scanner = GitHubScanner(repo)
result: ScanResult = scanner.scan()

# Specific branch
scanner = GitHubScanner(repo, branch="develop")
result = scanner.scan()

# Specific commit SHA
scanner = GitHubScanner(repo, branch="abc1234")
result = scanner.scan()

# Only list manifest paths (no content parsing)
paths = scanner.list_manifest_paths()
print(paths)  # ['requirements.txt', 'subproject/package.json']
```

### Commit history tracking

For each manifest file, `GitHubScanner` attempts to fetch the date of the most
recent commit that touched that file.  When available, it is stored on each
`Dependency` instance as `dep.last_updated` (a `datetime` object).

---

## Output Formats

### JSON

```python
from src.exporters import to_json

# From a ScanResult
json_str = to_json(scan_result)

# From a raw dict (legacy DependencyParser output)
json_str = to_json(raw_dict)

# Write to file
from src.exporters import write_to_file
write_to_file(json_str, "deps.json")
```

**Example output:**

```json
{
  "repo_name": "owner/repo",
  "scan_time": "2024-01-15T10:00:00+00:00",
  "manifest_files": ["requirements.txt"],
  "total_dependencies": 2,
  "dependencies": [
    {
      "name": "requests",
      "version": "2.28.0",
      "type": "pip",
      "source_file": "requirements.txt",
      "line_number": 1,
      "specifier": "=="
    }
  ],
  "errors": []
}
```

### CSV

```python
from src.exporters import to_csv

csv_str = to_csv(scan_result)
# name,version,type,source_file,line_number,specifier
# requests,2.28.0,pip,requirements.txt,1,==
# flask,2.2.5,pip,requirements.txt,2,>=
```

### Python dict

```python
from src.exporters import to_dict

d = to_dict(scan_result)
# Plain Python dict – useful for programmatic access
```

---

## CLI Interface

The enhanced CLI is in `src/main.py`.

```
usage: security-patcher-src [-h]
                             (--repo-path PATH | --github-url OWNER/REPO)
                             [--branch BRANCH]
                             [--output-format {json,csv,dict}]
                             [--output-file FILE]
                             [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

### Examples

**Scan a local repository and print JSON:**

```bash
python -m src.main --repo-path /path/to/repo
```

**Scan a remote repo and save to CSV:**

```bash
export GITHUB_TOKEN=ghp_...
python -m src.main --github-url owner/repo --output-format csv --output-file deps.csv
```

**Scan a specific branch with verbose logging:**

```bash
python -m src.main --github-url owner/repo --branch develop --log-level DEBUG
```

The original CLI (`main.py`) provides `scan` and `patch` sub-commands and
remains fully functional alongside the new interface.

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes (remote ops) | — | Personal Access Token with `repo` scope |
| `GITHUB_USERNAME` | No | — | Your GitHub username |
| `TARGET_REPO` | No | `Bylerma/Security-Patcher` | Default `owner/repo` |
| `DEFAULT_BASE_BRANCH` | No | `main` | Branch the PR targets |
| `LOCAL_REPO_PATH` | No | `.` | Local repo path for scanning |
| `DEFAULT_OUTPUT_FORMAT` | No | `json` | CLI output format |
| `NOTION_TOKEN` | No | — | Notion integration token (Phase 2) |
| `NOTION_DATABASE_ID` | No | — | Notion database ID (Phase 2) |

---

## Error Handling Guide

### Common issues and solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| `ValueError: Provide either local_path or github_repo.` | Neither argument was passed to `DependencyParser` | Pass `local_path=` or `github_repo=` |
| `ValueError: GITHUB_TOKEN is not set.` | Environment variable missing | Set `GITHUB_TOKEN` or add to `.env` |
| `Could not access repository 'owner/repo'` | Wrong repo name or no access | Check the repo name and token scopes |
| `toml package not installed; using regex fallback` | `toml` not in environment | `pip install toml` |
| Dependency version is empty string | Package is unpinned in manifest | Expected – unpinned packages have `version=""` |
| Malformed `pom.xml` / `package.json` | Parse error in manifest | Check the parser warning log; the manifest is skipped gracefully |

### Graceful degradation

All parsers handle malformed files without raising exceptions:
- A warning is logged.
- The manifest is recorded in `ScanResult.errors`.
- Parsing continues with remaining manifests.

---

## Extending the Parser

### Add a new manifest type to GitHubScanner

```python
import re
from src.github_scanner import _PARSERS
from src.models import Dependency

def _parse_poetry_lock(content: str, path: str) -> list:
    """Parse a poetry.lock file."""
    deps = []
    # ... your parsing logic ...
    return deps

# Register the parser
_PARSERS["poetry.lock"] = _parse_poetry_lock
```

Then pass the new filename to `GitHubScanner`:

```python
scanner = GitHubScanner(repo, manifest_files=["requirements.txt", "poetry.lock"])
```

### Add a new manifest type to the root DependencyParser

See [Extending the Parser](README.md#extending-the-parser) in the main README.
