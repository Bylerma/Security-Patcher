"""
git_automator.py - Automate Git operations for security vulnerability patches.

Responsibilities
----------------
* Create a dedicated branch for the security fix.
* Update the manifest file (e.g. requirements.txt) with the patched version.
* Commit the change with a detailed, CVE-specific commit message.
* Open a Pull Request with a comprehensive description.

Usage
-----
    from github import Github
    from git_automator import GitAutomator

    gh = Github(token)
    repo = gh.get_repo("owner/repo")

    automator = GitAutomator(repo)
    pr = automator.apply_patch(
        cve_id="CVE-2023-32681",
        package_name="requests",
        manifest_path="requirements.txt",
        old_version="2.28.0",
        new_version="2.31.0",
        severity="HIGH",
    )
    print(pr.html_url)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class GitAutomator:
    """
    Automate branch creation, commits, and Pull Request creation for a
    security vulnerability fix.

    Parameters
    ----------
    repo:
        A :class:`github.Repository.Repository` object (PyGithub).
    base_branch:
        The branch that the fix branch will be created from and the PR will
        target.  Defaults to ``"main"``.
    branch_prefix:
        Prefix used when naming the fix branch.  Defaults to
        ``"fix/security-"``.
    """

    def __init__(
        self,
        repo: Any,
        base_branch: str = "main",
        branch_prefix: str = "fix/security-",
    ) -> None:
        self.repo = repo
        self.base_branch = base_branch
        self.branch_prefix = branch_prefix

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_patch(
        self,
        cve_id: str,
        package_name: str,
        manifest_path: str,
        old_version: str,
        new_version: str,
        severity: str = "UNKNOWN",
        cve_description: str = "",
        testing_notes: str = "",
    ) -> Any:
        """
        Apply a security patch to a manifest file and create a Pull Request.

        Parameters
        ----------
        cve_id:
            The CVE identifier (e.g. ``"CVE-2023-32681"``).
        package_name:
            Name of the vulnerable package (e.g. ``"requests"``).
        manifest_path:
            Repository-relative path to the manifest file
            (e.g. ``"requirements.txt"``).
        old_version:
            The current (vulnerable) version string.
        new_version:
            The patched version string to apply.
        severity:
            Risk level (e.g. ``"CRITICAL"``, ``"HIGH"``, ``"MEDIUM"``,
            ``"LOW"``).  Used in the commit message and PR description.
        cve_description:
            Optional human-readable description of the vulnerability.
        testing_notes:
            Optional testing recommendations to include in the PR body.

        Returns
        -------
        github.PullRequest.PullRequest
            The newly created Pull Request object.
        """
        branch_name = self._branch_name(cve_id)
        logger.info("Creating branch '%s' from '%s'.", branch_name, self.base_branch)
        self._create_branch(branch_name)

        logger.info(
            "Patching %s: %s %s → %s.",
            manifest_path, package_name, old_version, new_version,
        )
        commit = self._commit_patch(
            branch_name=branch_name,
            manifest_path=manifest_path,
            package_name=package_name,
            old_version=old_version,
            new_version=new_version,
            cve_id=cve_id,
            severity=severity,
        )
        logger.info("Committed patch as %s.", commit.sha)

        pr = self._open_pull_request(
            branch_name=branch_name,
            cve_id=cve_id,
            package_name=package_name,
            manifest_path=manifest_path,
            old_version=old_version,
            new_version=new_version,
            severity=severity,
            cve_description=cve_description,
            testing_notes=testing_notes,
        )
        logger.info("Pull Request opened: %s", pr.html_url)
        return pr

    # ------------------------------------------------------------------
    # Branch helpers
    # ------------------------------------------------------------------

    def _branch_name(self, cve_id: str) -> str:
        """Return a sanitised branch name for the given CVE."""
        safe_cve = re.sub(r"[^A-Za-z0-9\-]", "-", cve_id)
        return f"{self.branch_prefix}{safe_cve}"

    def _create_branch(self, branch_name: str) -> None:
        """Create *branch_name* off the tip of ``self.base_branch``."""
        base_ref = self.repo.get_branch(self.base_branch)
        sha = base_ref.commit.sha
        try:
            self.repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=sha)
            logger.debug("Branch '%s' created at %s.", branch_name, sha)
        except Exception as exc:  # noqa: BLE001
            # Branch may already exist if re-running; log and continue
            logger.warning("Could not create branch '%s': %s", branch_name, exc)

    # ------------------------------------------------------------------
    # Commit helpers
    # ------------------------------------------------------------------

    def _commit_patch(
        self,
        branch_name: str,
        manifest_path: str,
        package_name: str,
        old_version: str,
        new_version: str,
        cve_id: str,
        severity: str,
    ) -> Any:
        """
        Fetch the manifest, replace the version string, and push a commit.
        """
        file_obj = self.repo.get_contents(manifest_path, ref=branch_name)
        original_content = file_obj.decoded_content.decode("utf-8")

        updated_content = self._replace_version(
            content=original_content,
            manifest_name=manifest_path.split("/")[-1],
            package_name=package_name,
            old_version=old_version,
            new_version=new_version,
        )

        if updated_content == original_content:
            logger.warning(
                "No version string changed in %s. Double-check package name and version.",
                manifest_path,
            )

        commit_message = self._build_commit_message(
            cve_id=cve_id,
            package_name=package_name,
            old_version=old_version,
            new_version=new_version,
            severity=severity,
        )

        result = self.repo.update_file(
            path=manifest_path,
            message=commit_message,
            content=updated_content,
            sha=file_obj.sha,
            branch=branch_name,
        )
        return result["commit"]

    @staticmethod
    def _replace_version(
        content: str,
        manifest_name: str,
        package_name: str,
        old_version: str,
        new_version: str,
    ) -> str:
        """
        Replace *old_version* with *new_version* for *package_name* in the
        manifest content string.

        Supports the following manifest formats:
        * requirements.txt  – ``package==version``
        * package.json      – ``"package": "version"``
        * Gemfile           – ``gem 'package', '~> version'``
        * go.mod            – ``module v version``
        * Cargo.toml        – ``package = "version"``
        * pom.xml           – ``<version>version</version>`` (best-effort)
        """
        safe_pkg = re.escape(package_name)
        safe_old = re.escape(old_version)

        if manifest_name == "requirements.txt":
            pattern = rf"({safe_pkg}\s*[><=!~]{{1,2}}\s*){safe_old}"
            return re.sub(pattern, rf"\g<1>{new_version}", content, flags=re.IGNORECASE)

        if manifest_name == "package.json":
            pattern = rf'("{safe_pkg}"\s*:\s*")[^"]*(")'
            return re.sub(pattern, rf"\g<1>{new_version}\g<2>", content)

        if manifest_name == "Gemfile":
            pattern = rf"(gem\s+['\"]{{safe_pkg}}['\"].*?['\"])[^'\"]*(['\"])"
            pattern = rf"""(gem\s+['\"]{safe_pkg}['\"].*?['\""]){safe_old}(['\""])"""
            return re.sub(pattern, rf"\g<1>{new_version}\g<2>", content)

        if manifest_name == "go.mod":
            pattern = rf"({safe_pkg}\s+v?){safe_old}"
            return re.sub(pattern, rf"\g<1>{new_version}", content)

        if manifest_name in ("Cargo.toml", "pyproject.toml"):
            # key = "old_version"  →  key = "new_version"
            pattern = rf'({safe_pkg}\s*=\s*["\']?(?:version\s*=\s*)?["\']?){safe_old}(["\']?)'
            return re.sub(pattern, rf"\g<1>{new_version}\g<2>", content)

        if manifest_name == "pom.xml":
            # Best-effort: replace bare version tag adjacent to the package name
            return content.replace(f"<version>{old_version}</version>",
                                   f"<version>{new_version}</version>", 1)

        # Fallback: plain string substitution
        return content.replace(old_version, new_version)

    # ------------------------------------------------------------------
    # Commit message
    # ------------------------------------------------------------------

    @staticmethod
    def _build_commit_message(
        cve_id: str,
        package_name: str,
        old_version: str,
        new_version: str,
        severity: str,
    ) -> str:
        return (
            f"fix({package_name}): patch {cve_id} [{severity}]\n\n"
            f"Bump {package_name} from {old_version} to {new_version} to remediate\n"
            f"{cve_id} (severity: {severity}).\n\n"
            f"See https://nvd.nist.gov/vuln/detail/{cve_id} for details."
        )

    # ------------------------------------------------------------------
    # Pull Request
    # ------------------------------------------------------------------

    def _open_pull_request(
        self,
        branch_name: str,
        cve_id: str,
        package_name: str,
        manifest_path: str,
        old_version: str,
        new_version: str,
        severity: str,
        cve_description: str,
        testing_notes: str,
    ) -> Any:
        title = f"[Security] {cve_id} – Bump {package_name} {old_version} → {new_version}"
        body = self._build_pr_body(
            cve_id=cve_id,
            package_name=package_name,
            manifest_path=manifest_path,
            old_version=old_version,
            new_version=new_version,
            severity=severity,
            cve_description=cve_description,
            testing_notes=testing_notes,
        )
        return self.repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=self.base_branch,
        )

    @staticmethod
    def _build_pr_body(
        cve_id: str,
        package_name: str,
        manifest_path: str,
        old_version: str,
        new_version: str,
        severity: str,
        cve_description: str,
        testing_notes: str,
    ) -> str:
        description_section = (
            f"\n{cve_description}\n" if cve_description else ""
        )
        testing_section = (
            f"\n{testing_notes}\n"
            if testing_notes
            else (
                "- Run the full test suite to verify no breaking changes.\n"
                "- Check changelogs between the two versions for API changes.\n"
            )
        )
        return f"""\
## 🔒 Security Patch: {cve_id}

**Severity:** {severity}
**Package:** `{package_name}`
**Manifest:** `{manifest_path}`
**CVE Details:** https://nvd.nist.gov/vuln/detail/{cve_id}
{description_section}
---

## Version Change

| | Version |
|---|---|
| **Before (vulnerable)** | `{old_version}` |
| **After  (patched)**    | `{new_version}` |

---

## What Changed

This pull request bumps `{package_name}` from `{old_version}` to `{new_version}` in \
`{manifest_path}` to address **{cve_id}**.

---

## Testing Recommendations

{testing_section}
---

## References

- [NVD Advisory](https://nvd.nist.gov/vuln/detail/{cve_id})
- [OSV.dev](https://osv.dev/vulnerability/{cve_id})

---

*This PR was created automatically by the Security Vulnerability Patcher.*
"""
