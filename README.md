# Security-Patcher

An autonomous **Security Vulnerability Patcher** that scans repositories for
dependency manifests, identifies vulnerable packages, and opens Pull Requests
with automated fixes.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Scan Dependencies](#scan-dependencies)
  - [Apply a Security Patch](#apply-a-security-patch)
- [Module API](#module-api)
  - [DependencyParser](#dependencyparser)
  - [GitAutomator](#gitautomator)
  - [Config](#config)
- [Sample CVE Patching Workflow](#sample-cve-patching-workflow)
- [Extending the Parser](#extending-the-parser)

---

## Overview

| Milestone | Module | Deliverable |
|-----------|--------|-------------|
| Dependency discovery | `dependency_parser.py` | JSON map of all repo dependencies |
| Automated patching   | `git_automator.py`     | PR with version bump commit        |
| Configuration        | `config.py`            | Env-var-driven settings            |
| Orchestration        | `main.py`              | CLI entry point                    |

---

## Project Structure

```
Security-Patcher/
├── config.py             # Configuration management
├── dependency_parser.py  # Manifest scanning and parsing
├── git_automator.py      # Branch / commit / PR automation
├── main.py               # CLI entry point
├── requirements.txt      # Python dependencies
├── tests/
│   ├── test_dependency_parser.py
│   └── test_git_automator.py
└── README.md
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Bylerma/Security-Patcher.git
cd Security-Patcher

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root (never commit this file):

```dotenv
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_USERNAME=your_github_username
TARGET_REPO=owner/repo
DEFAULT_BASE_BRANCH=main
```

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | **Yes** (for remote ops) | Personal Access Token with `repo` scope |
| `GITHUB_USERNAME` | No | Your GitHub username |
| `TARGET_REPO` | No | Default `owner/repo` target |
| `DEFAULT_BASE_BRANCH` | No | Branch the PR targets (default: `main`) |
| `LOCAL_REPO_PATH` | No | Path to local clone for scanning |

---

## Usage

### Scan Dependencies

**Local repository:**

```bash
python main.py scan --local /path/to/repo
```

**Remote GitHub repository:**

```bash
python main.py scan --repo owner/repo
```

**Example output:**

```json
{
  "manifests": [
    {
      "type": "requirements.txt",
      "path": "requirements.txt",
      "dependencies": [
        {"name": "requests", "version": "2.28.0"},
        {"name": "flask",    "version": "2.2.5"}
      ]
    }
  ],
  "total_dependencies": 2,
  "scan_source": "local"
}
```

### Apply a Security Patch

```bash
python main.py patch \
  --repo owner/repo \
  --cve CVE-2023-32681 \
  --package requests \
  --manifest requirements.txt \
  --old-version 2.28.0 \
  --new-version 2.31.0 \
  --severity HIGH \
  --description "SSRF vulnerability in requests proxy handling."
```

This will:
1. Create branch `fix/security-CVE-2023-32681`
2. Bump `requests` in `requirements.txt`
3. Commit with a detailed message
4. Open a Pull Request with full CVE context

---

## Module API

### DependencyParser

```python
from dependency_parser import DependencyParser

# Local scan
parser = DependencyParser(local_path="/path/to/repo")
result = parser.scan()
# result = {"manifests": [...], "total_dependencies": N, "scan_source": "local"}

# GitHub scan
from github import Github
gh = Github("ghp_token")
repo = gh.get_repo("owner/repo")
parser = DependencyParser(github_repo=repo)
result = parser.scan()
```

**Supported manifest files:**

| File | Ecosystem |
|------|-----------|
| `requirements.txt` | Python |
| `package.json` | Node.js |
| `Gemfile` | Ruby |
| `go.mod` | Go |
| `pom.xml` | Java / Maven |
| `Cargo.toml` | Rust |

### GitAutomator

```python
from github import Github
from git_automator import GitAutomator

gh = Github("ghp_token")
repo = gh.get_repo("owner/repo")

automator = GitAutomator(repo, base_branch="main")
pr = automator.apply_patch(
    cve_id="CVE-2023-32681",
    package_name="requests",
    manifest_path="requirements.txt",
    old_version="2.28.0",
    new_version="2.31.0",
    severity="HIGH",
    cve_description="SSRF vulnerability in proxy handling.",
    testing_notes="Run `pytest tests/` after upgrading.",
)
print(pr.html_url)
```

### Config

```python
from config import Config

Config.validate()          # raises ValueError if GITHUB_TOKEN is missing
print(Config.as_dict())    # sanitized config snapshot (token hidden)
```

---

## Sample CVE Patching Workflow

```
┌─────────────────────────────────────────────────────┐
│  python main.py scan --local .                      │
│  → Identify: requests==2.28.0 (vulnerable)          │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  python main.py patch                               │
│    --cve CVE-2023-32681                             │
│    --package requests                               │
│    --manifest requirements.txt                      │
│    --old-version 2.28.0                             │
│    --new-version 2.31.0                             │
│    --severity HIGH                                  │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
    Branch created:  fix/security-CVE-2023-32681
    Commit message:  fix(requests): patch CVE-2023-32681 [HIGH]
    PR opened:       [Security] CVE-2023-32681 – Bump requests 2.28.0 → 2.31.0
```

---

## Extending the Parser

To add support for a new manifest format, register a parser function in
`dependency_parser.py`:

```python
def _parse_my_manifest(content: str, path: str) -> dict:
    deps = []
    # ... parsing logic ...
    return {"type": "my-manifest", "path": path, "dependencies": deps}

# Register it:
_PARSERS["my-manifest-filename"] = _parse_my_manifest
```

Then add the filename to `Config.MANIFEST_FILES`.