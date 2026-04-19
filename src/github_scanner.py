"""
github_scanner.py - Scan a remote GitHub repository for dependencies via the
GitHub API without requiring a local clone.

Features
--------
* Discover all manifest files in a target repository.
* Parse manifest content fetched via the GitHub API.
* Track the last-commit date for each manifest file.
* Support scanning a specific branch or commit SHA.

Usage
-----
    from github import Github
    from src.github_scanner import GitHubScanner

    gh = Github("ghp_token")
    repo = gh.get_repo("owner/repo")

    scanner = GitHubScanner(repo, branch="main")
    result = scanner.scan()

    print(result.to_json())

The returned :class:`~src.models.ScanResult` object contains a flat list of
:class:`~src.models.Dependency` objects with ecosystem ``type``, the manifest
``source_file``, and – where possible – a ``line_number``.
"""

from __future__ import annotations

import logging
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from .models import Dependency, ScanResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Manifest → ecosystem type mapping
# ---------------------------------------------------------------------------

_MANIFEST_ECOSYSTEM: dict[str, str] = {
    "requirements.txt": "pip",
    "package.json": "npm",
    "Gemfile": "gem",
    "go.mod": "go",
    "pom.xml": "maven",
    "Cargo.toml": "cargo",
}

_SUPPORTED_MANIFESTS: frozenset[str] = frozenset(_MANIFEST_ECOSYSTEM.keys())


# ---------------------------------------------------------------------------
# Individual manifest parsers (return list[Dependency])
# ---------------------------------------------------------------------------


def _parse_requirements_txt(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        line = line.split("#")[0].strip()
        if not line:
            continue
        match = re.match(
            r"^([A-Za-z0-9_.\-\[\]]+)\s*([><=!~]{1,2})\s*([^\s,;]+)", line
        )
        if match:
            name = re.sub(r"\[.*\]", "", match.group(1)).strip()
            specifier = match.group(2)
            version = match.group(3).strip()
        else:
            name = re.sub(r"\[.*\]", "", line.split()[0]).strip()
            specifier = ""
            version = ""
        deps.append(
            Dependency(
                name=name,
                version=version,
                type="pip",
                source_file=path,
                line_number=line_no,
                specifier=specifier,
            )
        )
    return deps


def _parse_package_json(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return deps
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name, version in data.get(section, {}).items():
            deps.append(
                Dependency(
                    name=name,
                    version=str(version),
                    type="npm",
                    source_file=path,
                )
            )
    return deps


def _parse_gemfile(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Capture gem name and optional version string (both between quotes)
        match = re.match(
            r"""gem\s+['"]([^'"]+)['"]\s*(?:,\s*['"]([^'"]*)['"])?\s*""", line
        )
        if match:
            name = match.group(1).strip()
            version_str = (match.group(2) or "").strip()
            # Extract specifier operator (e.g. "~>", ">=") from version string
            spec_match = re.match(r"([~><=!]{1,2})\s*(.*)", version_str)
            if spec_match:
                specifier = spec_match.group(1)
                version = spec_match.group(2).strip()
            else:
                specifier = ""
                version = version_str
            deps.append(
                Dependency(
                    name=name,
                    version=version,
                    type="gem",
                    source_file=path,
                    line_number=line_no,
                    specifier=specifier,
                )
            )
    return deps


def _parse_go_mod(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    in_require_block = False
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block:
            if stripped == ")":
                in_require_block = False
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append(
                    Dependency(
                        name=parts[0],
                        version=parts[1],
                        type="go",
                        source_file=path,
                        line_number=line_no,
                    )
                )
        elif stripped.startswith("require "):
            parts = stripped[len("require "):].split()
            if len(parts) >= 2:
                deps.append(
                    Dependency(
                        name=parts[0],
                        version=parts[1],
                        type="go",
                        source_file=path,
                        line_number=line_no,
                    )
                )
    return deps


def _parse_pom_xml(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return deps
    ns_match = re.match(r"\{[^}]+\}", root.tag)
    ns = ns_match.group(0) if ns_match else ""
    for dep in root.iter(f"{ns}dependency"):
        group_id = dep.findtext(f"{ns}groupId", "").strip()
        artifact_id = dep.findtext(f"{ns}artifactId", "").strip()
        version = dep.findtext(f"{ns}version", "").strip()
        name = f"{group_id}:{artifact_id}" if group_id else artifact_id
        deps.append(
            Dependency(
                name=name,
                version=version,
                type="maven",
                source_file=path,
            )
        )
    return deps


def _parse_cargo_toml(content: str, path: str) -> List[Dependency]:
    deps: list[Dependency] = []
    try:
        import toml  # optional dependency

        data = toml.loads(content)
    except ImportError:
        logger.warning("toml package not installed; using regex fallback for Cargo.toml.")
        data = _cargo_toml_regex_fallback(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse %s: %s", path, exc)
        return deps

    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, value in data.get(section, {}).items():
            if isinstance(value, str):
                version = value
            elif isinstance(value, dict):
                version = value.get("version", "")
            else:
                version = str(value)
            deps.append(
                Dependency(
                    name=name,
                    version=version,
                    type="cargo",
                    source_file=path,
                )
            )
    return deps


def _cargo_toml_regex_fallback(content: str) -> dict:
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
# GitHubScanner
# ---------------------------------------------------------------------------


class GitHubScanner:
    """
    Scan a remote GitHub repository for dependency manifests using the
    GitHub API (PyGithub).  No local clone is required.

    Parameters
    ----------
    repo:
        A :class:`github.Repository.Repository` object obtained from
        ``PyGithub``.
    branch:
        Branch name or commit SHA to scan.  Defaults to ``"HEAD"``
        (the repository's default branch).
    manifest_files:
        Override the set of manifest file names to look for.
    """

    def __init__(
        self,
        repo: Any,
        branch: str = "HEAD",
        manifest_files: Optional[List[str]] = None,
    ) -> None:
        self.repo = repo
        self.branch = branch
        self.manifest_files: frozenset[str] = frozenset(
            manifest_files if manifest_files is not None else _SUPPORTED_MANIFESTS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> ScanResult:
        """
        Scan the remote repository and return a :class:`~src.models.ScanResult`.

        The result contains a flat list of :class:`~src.models.Dependency`
        objects with their source file path, line number (where tracked),
        and ecosystem type populated.
        """
        result = ScanResult(repo_name=self.repo.full_name)

        try:
            tree = self.repo.get_git_tree(self.branch, recursive=True)
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to fetch git tree for branch '{self.branch}': {exc}"
            logger.error(msg)
            result.errors.append(msg)
            return result

        for item in tree.tree:
            filename = os.path.basename(item.path)
            if filename not in self.manifest_files:
                continue

            logger.info("Fetching manifest: %s", item.path)
            result.manifest_files.append(item.path)

            try:
                file_obj = self.repo.get_contents(item.path, ref=self.branch)
                content = file_obj.decoded_content.decode("utf-8")
            except Exception as exc:  # noqa: BLE001
                msg = f"Could not fetch '{item.path}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)
                continue

            # Parse
            parser_fn = _PARSERS.get(filename)
            if parser_fn is None:
                continue
            try:
                deps = parser_fn(content, item.path)
            except Exception as exc:  # noqa: BLE001
                msg = f"Error parsing '{item.path}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)
                continue

            # Optionally enrich with last-commit date
            last_updated = self._get_last_commit_date(item.path)
            for dep in deps:
                if last_updated:
                    dep.last_updated = last_updated

            result.dependencies.extend(deps)

        logger.info(
            "GitHub scan complete for '%s': %d manifest(s), %d dependencies.",
            self.repo.full_name,
            len(result.manifest_files),
            result.total_dependencies,
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_last_commit_date(self, path: str) -> Optional[datetime]:
        """
        Return the UTC datetime of the most recent commit that touched *path*.

        Returns ``None`` if the commit history cannot be retrieved.
        """
        try:
            commits = self.repo.get_commits(path=path, sha=self.branch)
            first = commits[0]
            return first.commit.author.date.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            return None

    def list_manifest_paths(self) -> List[str]:
        """
        Return the paths of all manifest files present in the repository
        at *self.branch* without parsing their contents.

        Useful for a quick inventory before a full scan.
        """
        paths: list[str] = []
        try:
            tree = self.repo.get_git_tree(self.branch, recursive=True)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch git tree: %s", exc)
            return paths

        for item in tree.tree:
            if os.path.basename(item.path) in self.manifest_files:
                paths.append(item.path)
        return paths
