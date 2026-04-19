"""
Tests for src/github_scanner.py

Uses unittest.mock to simulate PyGithub API calls so no real GitHub
credentials or network access are required.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.github_scanner import (
    GitHubScanner,
    _parse_cargo_toml,
    _parse_gemfile,
    _parse_go_mod,
    _parse_package_json,
    _parse_pom_xml,
    _parse_requirements_txt,
)
from src.models import Dependency, ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tree_item(path: str) -> SimpleNamespace:
    """Return a mock git-tree item."""
    return SimpleNamespace(path=path)


def _make_repo(
    tree_paths: list[str] | None = None,
    file_contents: dict[str, str] | None = None,
) -> MagicMock:
    """
    Return a mock PyGithub Repository.

    Parameters
    ----------
    tree_paths:
        Paths to include in the git tree (simulating repo file listing).
    file_contents:
        Mapping of path → raw text content returned by get_contents().
    """
    repo = MagicMock()
    repo.full_name = "owner/repo"

    # Git tree
    items = [_make_tree_item(p) for p in (tree_paths or [])]
    tree_mock = MagicMock()
    tree_mock.tree = items
    repo.get_git_tree.return_value = tree_mock

    # File contents
    contents = file_contents or {}

    def _get_contents(path, ref=None):
        if path in contents:
            file_mock = MagicMock()
            file_mock.decoded_content = contents[path].encode("utf-8")
            return file_mock
        raise Exception(f"File not found: {path}")

    repo.get_contents.side_effect = _get_contents

    # Commit history (return a single commit with a fixed date)
    commit_mock = MagicMock()
    commit_mock.commit.author.date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    repo.get_commits.return_value = [commit_mock]

    return repo


# ---------------------------------------------------------------------------
# Unit tests for individual parsers (with Dependency output)
# ---------------------------------------------------------------------------


class TestParseRequirementsTxtDeps:
    def test_pinned_version(self):
        content = "requests==2.28.0\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert len(deps) == 1
        assert deps[0].name == "requests"
        assert deps[0].version == "2.28.0"
        assert deps[0].specifier == "=="
        assert deps[0].type == "pip"
        assert deps[0].line_number == 1

    def test_greater_equal_version(self):
        content = "flask>=2.2.5\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert deps[0].specifier == ">="
        assert deps[0].version == "2.2.5"

    def test_no_version(self):
        content = "requests\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert deps[0].name == "requests"
        assert deps[0].version == ""

    def test_comments_skipped(self):
        content = "# comment\nrequests==2.28.0\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert len(deps) == 1

    def test_extras_stripped(self):
        content = "requests[security]==2.28.0\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert deps[0].name == "requests"

    def test_line_numbers(self):
        content = "# comment\n\nrequests==2.28.0\nflask>=2.2.5\n"
        deps = _parse_requirements_txt(content, "requirements.txt")
        assert deps[0].line_number == 3
        assert deps[1].line_number == 4


class TestParsePackageJsonDeps:
    def test_dependencies(self):
        data = {"dependencies": {"express": "^4.18.0"}}
        deps = _parse_package_json(json.dumps(data), "package.json")
        assert deps[0].name == "express"
        assert deps[0].version == "^4.18.0"
        assert deps[0].type == "npm"

    def test_dev_dependencies(self):
        data = {"devDependencies": {"jest": "^29.0.0"}}
        deps = _parse_package_json(json.dumps(data), "package.json")
        assert deps[0].name == "jest"

    def test_invalid_json_returns_empty(self):
        deps = _parse_package_json("not json", "package.json")
        assert deps == []


class TestParseGemfileDeps:
    def test_gem_with_specifier(self):
        content = "gem 'rails', '~> 6.1'\n"
        deps = _parse_gemfile(content, "Gemfile")
        assert deps[0].name == "rails"
        assert deps[0].specifier == "~>"
        assert deps[0].version == "6.1"
        assert deps[0].type == "gem"

    def test_gem_no_version(self):
        content = "gem 'rake'\n"
        deps = _parse_gemfile(content, "Gemfile")
        assert deps[0].name == "rake"

    def test_comments_skipped(self):
        content = "# comment\ngem 'rails', '~> 6.1'\n"
        deps = _parse_gemfile(content, "Gemfile")
        assert len(deps) == 1


class TestParseGoModDeps:
    def test_require_block(self):
        content = "require (\n\tgithub.com/gin-gonic/gin v1.9.1\n)\n"
        deps = _parse_go_mod(content, "go.mod")
        assert deps[0].name == "github.com/gin-gonic/gin"
        assert deps[0].version == "v1.9.1"
        assert deps[0].type == "go"

    def test_single_require(self):
        content = "require github.com/foo/bar v1.0.0\n"
        deps = _parse_go_mod(content, "go.mod")
        assert deps[0].name == "github.com/foo/bar"


class TestParsePomXmlDeps:
    def test_basic_dependency(self):
        content = """<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-core</artifactId>
      <version>5.3.27</version>
    </dependency>
  </dependencies>
</project>"""
        deps = _parse_pom_xml(content, "pom.xml")
        assert deps[0].name == "org.springframework:spring-core"
        assert deps[0].version == "5.3.27"
        assert deps[0].type == "maven"

    def test_invalid_xml_returns_empty(self):
        deps = _parse_pom_xml("<broken", "pom.xml")
        assert deps == []


class TestParseCargoTomlDeps:
    def test_string_version(self):
        content = "[dependencies]\nserde = \"1.0\"\n"
        deps = _parse_cargo_toml(content, "Cargo.toml")
        assert deps[0].name == "serde"
        assert deps[0].version == "1.0"
        assert deps[0].type == "cargo"

    def test_dev_dependencies(self):
        content = "[dev-dependencies]\npretty_assertions = \"1.4.0\"\n"
        deps = _parse_cargo_toml(content, "Cargo.toml")
        assert deps[0].name == "pretty_assertions"


# ---------------------------------------------------------------------------
# GitHubScanner integration tests (mocked)
# ---------------------------------------------------------------------------


class TestGitHubScannerScan:
    def test_scan_returns_scan_result(self):
        repo = _make_repo(
            tree_paths=["requirements.txt"],
            file_contents={"requirements.txt": "requests==2.28.0\n"},
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert isinstance(result, ScanResult)
        assert result.repo_name == "owner/repo"

    def test_scan_discovers_requirements_txt(self):
        repo = _make_repo(
            tree_paths=["requirements.txt"],
            file_contents={"requirements.txt": "requests==2.28.0\nflask>=2.2.5\n"},
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert "requirements.txt" in result.manifest_files
        assert result.total_dependencies == 2

    def test_scan_multiple_manifests(self):
        repo = _make_repo(
            tree_paths=["requirements.txt", "package.json"],
            file_contents={
                "requirements.txt": "requests==2.28.0\n",
                "package.json": json.dumps({"dependencies": {"express": "^4.18.0"}}),
            },
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert result.total_dependencies == 2
        types = {d.type for d in result.dependencies}
        assert "pip" in types
        assert "npm" in types

    def test_scan_nested_manifest(self):
        repo = _make_repo(
            tree_paths=["subproject/requirements.txt"],
            file_contents={"subproject/requirements.txt": "django==4.2.0\n"},
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert result.total_dependencies == 1
        assert result.dependencies[0].source_file == "subproject/requirements.txt"

    def test_scan_ignores_unknown_files(self):
        repo = _make_repo(
            tree_paths=["README.md", "src/main.py"],
            file_contents={},
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert result.total_dependencies == 0
        assert result.manifest_files == []

    def test_scan_records_error_on_fetch_failure(self):
        repo = _make_repo(
            tree_paths=["requirements.txt"],
            file_contents={},  # get_contents will raise
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert len(result.errors) >= 1
        assert "requirements.txt" in result.errors[0]

    def test_scan_records_error_on_tree_failure(self):
        repo = MagicMock()
        repo.full_name = "owner/repo"
        repo.get_git_tree.side_effect = Exception("API error")
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert len(result.errors) == 1

    def test_scan_with_custom_branch(self):
        repo = _make_repo(
            tree_paths=["requirements.txt"],
            file_contents={"requirements.txt": "requests==2.28.0\n"},
        )
        scanner = GitHubScanner(repo, branch="develop")
        scanner.scan()
        repo.get_git_tree.assert_called_with("develop", recursive=True)

    def test_scan_custom_manifest_files(self):
        repo = _make_repo(
            tree_paths=["requirements.txt", "package.json"],
            file_contents={"requirements.txt": "requests==2.28.0\n"},
        )
        scanner = GitHubScanner(repo, manifest_files=["requirements.txt"])
        result = scanner.scan()
        assert len(result.manifest_files) == 1
        assert "requirements.txt" in result.manifest_files

    def test_dependency_source_file_set(self):
        repo = _make_repo(
            tree_paths=["requirements.txt"],
            file_contents={"requirements.txt": "requests==2.28.0\n"},
        )
        scanner = GitHubScanner(repo)
        result = scanner.scan()
        assert result.dependencies[0].source_file == "requirements.txt"


class TestGitHubScannerListManifestPaths:
    def test_list_returns_paths(self):
        repo = _make_repo(
            tree_paths=["requirements.txt", "README.md", "package.json"],
            file_contents={},
        )
        scanner = GitHubScanner(repo)
        paths = scanner.list_manifest_paths()
        assert "requirements.txt" in paths
        assert "package.json" in paths
        assert "README.md" not in paths

    def test_list_empty_on_tree_error(self):
        repo = MagicMock()
        repo.full_name = "owner/repo"
        repo.get_git_tree.side_effect = Exception("error")
        scanner = GitHubScanner(repo)
        assert scanner.list_manifest_paths() == []
