"""
dependency_parser.py - Scan a repository for dependency manifest files and
extract structured package information.

Supported manifests
-------------------
* requirements.txt   (Python)
* package.json       (Node.js)
* Gemfile            (Ruby)
* go.mod             (Go)
* pom.xml            (Java / Maven)
* Cargo.toml         (Rust)

Usage
-----
    from dependency_parser import DependencyParser

    # Scan a local directory
    parser = DependencyParser(local_path="/path/to/repo")
    result = parser.scan()

    # Scan a remote GitHub repository (requires a PyGithub token)
    parser = DependencyParser(github_repo=gh_repo_object)
    result = parser.scan()

The ``scan()`` method returns a dictionary with the shape::

    {
        "manifests": [
            {
                "type":         "requirements.txt",
                "path":         "requirements.txt",
                "dependencies": [
                    {"name": "requests", "version": "2.28.0"},
                    ...
                ]
            },
            ...
        ],
        "total_dependencies": 42,
        "scan_source": "local"    # or "github"
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual manifest parsers
# ---------------------------------------------------------------------------


def _parse_requirements_txt(content: str, path: str) -> dict:
    """Parse a ``requirements.txt`` file."""
    deps: list[dict[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        # Skip blank lines, comments, and options flags (e.g. -r, --index-url)
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip inline comments
        line = line.split("#")[0].strip()
        if not line:
            continue
        # Handle common specifiers: ==, >=, <=, ~=, !=, >
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)\s*([><=!~]{1,2})\s*([^\s,;]+)", line)
        if match:
            name, _op, version = match.group(1), match.group(2), match.group(3)
            # Normalise extras like package[extra] → package
            name = re.sub(r"\[.*\]", "", name)
            deps.append({"name": name.strip(), "version": version.strip()})
        else:
            # No version pinning – record the package with an empty version
            name = re.sub(r"\[.*\]", "", line.split()[0])
            deps.append({"name": name.strip(), "version": ""})
    return {"type": "requirements.txt", "path": path, "dependencies": deps}


def _parse_package_json(content: str, path: str) -> dict:
    """Parse a Node.js ``package.json`` file."""
    deps: list[dict[str, str]] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return {"type": "package.json", "path": path, "dependencies": deps}

    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name, version in data.get(section, {}).items():
            deps.append({"name": name, "version": version})
    return {"type": "package.json", "path": path, "dependencies": deps}


def _parse_gemfile(content: str, path: str) -> dict:
    """Parse a Ruby ``Gemfile``."""
    deps: list[dict[str, str]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # gem 'rails', '~> 6.1'  or  gem "rails", ">= 6.0"
        match = re.match(
            r"""gem\s+['"]([^'"]+)['"]\s*,?\s*['"]?([^'",\s]*)['"]?""", line
        )
        if match:
            name, version = match.group(1), match.group(2)
            deps.append({"name": name.strip(), "version": version.strip()})
    return {"type": "Gemfile", "path": path, "dependencies": deps}


def _parse_go_mod(content: str, path: str) -> dict:
    """Parse a Go ``go.mod`` file."""
    deps: list[dict[str, str]] = []
    in_require_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block:
            if stripped == ")":
                in_require_block = False
                continue
            # github.com/some/module v1.2.3
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append({"name": parts[0], "version": parts[1]})
        elif stripped.startswith("require "):
            # Single-line: require github.com/foo/bar v1.0.0
            parts = stripped[len("require "):].split()
            if len(parts) >= 2:
                deps.append({"name": parts[0], "version": parts[1]})
    return {"type": "go.mod", "path": path, "dependencies": deps}


def _parse_pom_xml(content: str, path: str) -> dict:
    """Parse a Maven ``pom.xml`` file."""
    deps: list[dict[str, str]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return {"type": "pom.xml", "path": path, "dependencies": deps}

    # Maven XML uses a default namespace; handle with or without it
    ns_match = re.match(r"\{[^}]+\}", root.tag)
    ns = ns_match.group(0) if ns_match else ""

    for dep in root.iter(f"{ns}dependency"):
        group_id = dep.findtext(f"{ns}groupId", "").strip()
        artifact_id = dep.findtext(f"{ns}artifactId", "").strip()
        version = dep.findtext(f"{ns}version", "").strip()
        name = f"{group_id}:{artifact_id}" if group_id else artifact_id
        deps.append({"name": name, "version": version})
    return {"type": "pom.xml", "path": path, "dependencies": deps}


def _parse_cargo_toml(content: str, path: str) -> dict:
    """Parse a Rust ``Cargo.toml`` file."""
    deps: list[dict[str, str]] = []
    try:
        import toml  # optional dependency

        data = toml.loads(content)
    except ImportError:
        logger.warning("toml package not installed; falling back to regex parsing.")
        data = _cargo_toml_regex_fallback(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse %s: %s", path, exc)
        return {"type": "Cargo.toml", "path": path, "dependencies": deps}

    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, value in data.get(section, {}).items():
            if isinstance(value, str):
                version = value
            elif isinstance(value, dict):
                version = value.get("version", "")
            else:
                version = str(value)
            deps.append({"name": name, "version": version})
    return {"type": "Cargo.toml", "path": path, "dependencies": deps}


def _cargo_toml_regex_fallback(content: str) -> dict:
    """Minimal TOML parser for Cargo.toml when the ``toml`` library is absent."""
    result: dict[str, Any] = {}
    current_section: str | None = None
    section_pattern = re.compile(r"^\[([^\]]+)\]")
    kv_pattern = re.compile(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]*)"')

    for line in content.splitlines():
        line = line.strip()
        sec = section_pattern.match(line)
        if sec:
            current_section = sec.group(1)
            result.setdefault(current_section, {})
            continue
        kv = kv_pattern.match(line)
        if kv and current_section:
            result[current_section][kv.group(1)] = kv.group(2)
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PARSERS: dict[str, Any] = {
    "requirements.txt": _parse_requirements_txt,
    "package.json": _parse_package_json,
    "Gemfile": _parse_gemfile,
    "go.mod": _parse_go_mod,
    "pom.xml": _parse_pom_xml,
    "Cargo.toml": _parse_cargo_toml,
}


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------


class DependencyParser:
    """
    Scan a repository for dependency manifest files and extract structured
    package information.

    Parameters
    ----------
    local_path:
        Absolute or relative path to the root of a locally cloned repository.
    github_repo:
        A :class:`github.Repository.Repository` object (PyGithub).  When
        provided, files are fetched through the GitHub API instead of the
        local filesystem.
    manifest_files:
        Override the default list of manifest file names to look for.
    """

    def __init__(
        self,
        local_path: str | None = None,
        github_repo: Any | None = None,
        manifest_files: list[str] | None = None,
    ) -> None:
        if local_path is None and github_repo is None:
            raise ValueError("Provide either local_path or github_repo.")
        self.local_path = local_path
        self.github_repo = github_repo
        self.manifest_files: list[str] = manifest_files or list(_PARSERS.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> dict:
        """
        Scan the repository and return structured dependency information.

        Returns
        -------
        dict
            ``{"manifests": [...], "total_dependencies": N, "scan_source": "local"|"github"}``
        """
        if self.github_repo is not None:
            manifests = self._scan_github()
            source = "github"
        else:
            manifests = self._scan_local()
            source = "local"

        total = sum(len(m["dependencies"]) for m in manifests)
        logger.info("Scan complete. Found %d manifest(s), %d dependencies.", len(manifests), total)
        return {
            "manifests": manifests,
            "total_dependencies": total,
            "scan_source": source,
        }

    # ------------------------------------------------------------------
    # Local scanning
    # ------------------------------------------------------------------

    def _scan_local(self) -> list[dict]:
        manifests: list[dict] = []
        for root, _dirs, files in os.walk(self.local_path):  # type: ignore[arg-type]
            for filename in files:
                if filename in self.manifest_files:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, self.local_path)
                    logger.info("Parsing local manifest: %s", rel_path)
                    try:
                        with open(full_path, encoding="utf-8") as fh:
                            content = fh.read()
                        parsed = _PARSERS[filename](content, rel_path)
                        manifests.append(parsed)
                    except OSError as exc:
                        logger.warning("Could not read %s: %s", full_path, exc)
        return manifests

    # ------------------------------------------------------------------
    # GitHub API scanning
    # ------------------------------------------------------------------

    def _scan_github(self) -> list[dict]:
        manifests: list[dict] = []
        self._walk_github_tree(self.github_repo.get_git_tree("HEAD", recursive=True), manifests)
        return manifests

    def _walk_github_tree(self, tree: Any, manifests: list[dict]) -> None:
        for item in tree.tree:
            filename = os.path.basename(item.path)
            if filename in self.manifest_files:
                logger.info("Parsing GitHub manifest: %s", item.path)
                try:
                    file_content = self.github_repo.get_contents(item.path)
                    content = file_content.decoded_content.decode("utf-8")
                    parsed = _PARSERS[filename](content, item.path)
                    manifests.append(parsed)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not fetch %s from GitHub: %s", item.path, exc)
