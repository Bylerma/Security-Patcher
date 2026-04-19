"""
Tests for git_automator.py

Uses unittest.mock to stub out PyGithub calls so no real GitHub credentials
or network access are required.
"""

import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from git_automator import GitAutomator


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_repo(
    file_content: str = "requests==2.28.0\n",
    base_branch: str = "main",
    base_sha: str = "abc123",
) -> MagicMock:
    """Return a mock PyGithub Repository object."""
    repo = MagicMock()

    # get_branch returns a branch mock with .commit.sha
    branch_mock = MagicMock()
    branch_mock.commit.sha = base_sha
    repo.get_branch.return_value = branch_mock

    # get_contents returns a file mock with decoded_content and sha
    file_mock = MagicMock()
    file_mock.decoded_content = file_content.encode("utf-8")
    file_mock.sha = "file_sha_001"
    repo.get_contents.return_value = file_mock

    # update_file returns a dict with a commit
    commit_mock = MagicMock()
    commit_mock.sha = "new_commit_sha"
    repo.update_file.return_value = {"commit": commit_mock}

    # create_pull returns a PR mock
    pr_mock = MagicMock()
    pr_mock.html_url = "https://github.com/owner/repo/pull/42"
    pr_mock.number = 42
    repo.create_pull.return_value = pr_mock

    return repo


# ---------------------------------------------------------------------------
# GitAutomator._branch_name
# ---------------------------------------------------------------------------


class TestBranchName:
    def test_standard_cve(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        assert automator._branch_name("CVE-2023-32681") == "fix/security-CVE-2023-32681"

    def test_special_chars_replaced(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        name = automator._branch_name("CVE_2023/32681")
        assert "/" not in name.split("fix/security-", 1)[1]

    def test_custom_prefix(self):
        repo = _make_repo()
        automator = GitAutomator(repo, branch_prefix="patch/")
        assert automator._branch_name("CVE-2023-1234").startswith("patch/")


# ---------------------------------------------------------------------------
# GitAutomator._build_commit_message
# ---------------------------------------------------------------------------


class TestBuildCommitMessage:
    def test_contains_cve(self):
        msg = GitAutomator._build_commit_message(
            cve_id="CVE-2023-32681",
            package_name="requests",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        assert "CVE-2023-32681" in msg
        assert "requests" in msg
        assert "2.28.0" in msg
        assert "2.31.0" in msg
        assert "HIGH" in msg

    def test_nvd_link_included(self):
        msg = GitAutomator._build_commit_message(
            cve_id="CVE-2023-32681",
            package_name="requests",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        assert "https://nvd.nist.gov/vuln/detail/CVE-2023-32681" in msg


# ---------------------------------------------------------------------------
# GitAutomator._replace_version
# ---------------------------------------------------------------------------


class TestReplaceVersion:
    def test_requirements_txt_pinned(self):
        content = "requests==2.28.0\nflask>=2.2.5\n"
        result = GitAutomator._replace_version(
            content, "requirements.txt", "requests", "2.28.0", "2.31.0"
        )
        assert "requests==2.31.0" in result
        assert "flask>=2.2.5" in result

    def test_package_json(self):
        content = '{"dependencies": {"express": "^4.17.0"}}'
        result = GitAutomator._replace_version(
            content, "package.json", "express", "^4.17.0", "^4.18.2"
        )
        assert "^4.18.2" in result
        assert "^4.17.0" not in result

    def test_go_mod(self):
        content = "require github.com/foo/bar v1.0.0\n"
        result = GitAutomator._replace_version(
            content, "go.mod", "github.com/foo/bar", "v1.0.0", "v1.2.0"
        )
        assert "v1.2.0" in result

    def test_cargo_toml(self):
        content = '[dependencies]\nserde = "1.0"\n'
        result = GitAutomator._replace_version(
            content, "Cargo.toml", "serde", "1.0", "1.0.160"
        )
        assert "1.0.160" in result

    def test_pom_xml(self):
        content = "<version>5.3.27</version>"
        result = GitAutomator._replace_version(
            content, "pom.xml", "spring-core", "5.3.27", "5.3.28"
        )
        assert "<version>5.3.28</version>" in result

    def test_fallback_plain_replace(self):
        content = "version: 1.0.0"
        result = GitAutomator._replace_version(
            content, "unknown.txt", "pkg", "1.0.0", "2.0.0"
        )
        assert "2.0.0" in result


# ---------------------------------------------------------------------------
# GitAutomator.apply_patch (integration, mocked)
# ---------------------------------------------------------------------------


class TestApplyPatch:
    def test_creates_branch(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        automator.apply_patch(
            cve_id="CVE-2023-32681",
            package_name="requests",
            manifest_path="requirements.txt",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        repo.create_git_ref.assert_called_once()
        # Handle both positional and keyword call styles
        args, kwargs = repo.create_git_ref.call_args
        created_ref = kwargs.get("ref") or args[0]
        assert "CVE-2023-32681" in created_ref

    def test_updates_file(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        automator.apply_patch(
            cve_id="CVE-2023-32681",
            package_name="requests",
            manifest_path="requirements.txt",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        repo.update_file.assert_called_once()
        _, kwargs = repo.update_file.call_args
        assert "2.31.0" in kwargs.get("content", "")

    def test_creates_pull_request(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        pr = automator.apply_patch(
            cve_id="CVE-2023-32681",
            package_name="requests",
            manifest_path="requirements.txt",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        repo.create_pull.assert_called_once()
        assert pr.number == 42

    def test_pr_title_includes_cve(self):
        repo = _make_repo()
        automator = GitAutomator(repo)
        automator.apply_patch(
            cve_id="CVE-2023-99999",
            package_name="flask",
            manifest_path="requirements.txt",
            old_version="2.2.5",
            new_version="2.3.3",
            severity="CRITICAL",
        )
        _, kwargs = repo.create_pull.call_args
        assert "CVE-2023-99999" in kwargs["title"]
        assert "flask" in kwargs["title"]

    def test_pr_body_includes_severity(self):
        repo = _make_repo("flask==2.2.5\n")
        automator = GitAutomator(repo)
        automator.apply_patch(
            cve_id="CVE-2023-99999",
            package_name="flask",
            manifest_path="requirements.txt",
            old_version="2.2.5",
            new_version="2.3.3",
            severity="CRITICAL",
        )
        _, kwargs = repo.create_pull.call_args
        assert "CRITICAL" in kwargs["body"]

    def test_branch_creation_error_continues(self):
        """If branch already exists, apply_patch should still proceed."""
        repo = _make_repo()
        repo.create_git_ref.side_effect = Exception("Branch already exists")
        # Should not raise
        automator = GitAutomator(repo)
        automator.apply_patch(
            cve_id="CVE-2023-32681",
            package_name="requests",
            manifest_path="requirements.txt",
            old_version="2.28.0",
            new_version="2.31.0",
            severity="HIGH",
        )
        repo.update_file.assert_called_once()
