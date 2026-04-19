"""
main.py - Entry point for the Security Vulnerability Patcher.

Orchestrates:
1. Dependency scanning (DependencyParser)
2. Optional automated patching (GitAutomator)

Usage examples
--------------
List all dependencies in the current directory::

    python main.py scan --local .

List dependencies in a remote GitHub repo::

    python main.py scan --repo owner/repo

Apply a security patch to a remote repo::

    python main.py patch \\
        --repo owner/repo \\
        --cve CVE-2023-32681 \\
        --package requests \\
        --manifest requirements.txt \\
        --old-version 2.28.0 \\
        --new-version 2.31.0 \\
        --severity HIGH
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from config import Config
from dependency_parser import DependencyParser
from git_automator import GitAutomator

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("security_patcher")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    """Handle the ``scan`` sub-command."""
    if args.local:
        logger.info("Scanning local directory: %s", args.local)
        parser = DependencyParser(local_path=args.local)
    else:
        repo_name = args.repo or Config.TARGET_REPO
        logger.info("Scanning GitHub repository: %s", repo_name)
        try:
            Config.validate()
        except ValueError as exc:
            logger.error("%s", exc)
            return 1
        from github import Github  # noqa: PLC0415

        gh = Github(Config.GITHUB_TOKEN)
        try:
            repo = gh.get_repo(repo_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not access repository '%s': %s", repo_name, exc)
            return 1
        parser = DependencyParser(github_repo=repo)

    result = parser.scan()
    print(json.dumps(result, indent=2))
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    """Handle the ``patch`` sub-command."""
    try:
        Config.validate()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    from github import Github  # noqa: PLC0415

    repo_name = args.repo or Config.TARGET_REPO
    gh = Github(Config.GITHUB_TOKEN)
    try:
        repo = gh.get_repo(repo_name)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not access repository '%s': %s", repo_name, exc)
        return 1

    automator = GitAutomator(
        repo=repo,
        base_branch=args.base_branch or Config.DEFAULT_BASE_BRANCH,
        branch_prefix=Config.BRANCH_PREFIX,
    )

    try:
        pr = automator.apply_patch(
            cve_id=args.cve,
            package_name=args.package,
            manifest_path=args.manifest,
            old_version=args.old_version,
            new_version=args.new_version,
            severity=args.severity,
            cve_description=args.description or "",
            testing_notes=args.testing_notes or "",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Patching failed: %s", exc)
        return 1

    logger.info("Pull Request created successfully: %s", pr.html_url)
    print(json.dumps({"pull_request_url": pr.html_url, "number": pr.number}))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="security-patcher",
        description="Automated Security Vulnerability Patcher",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- scan ----
    scan_parser = subparsers.add_parser("scan", help="Scan a repository for dependencies.")
    scan_source = scan_parser.add_mutually_exclusive_group()
    scan_source.add_argument("--local", metavar="PATH", help="Path to a local repository clone.")
    scan_source.add_argument("--repo", metavar="OWNER/REPO", help="Remote GitHub repository.")

    # ---- patch ----
    patch_parser = subparsers.add_parser("patch", help="Apply a security patch via Pull Request.")
    patch_parser.add_argument("--repo", metavar="OWNER/REPO", help="Remote GitHub repository.")
    patch_parser.add_argument("--cve", required=True, metavar="CVE-XXXX-YYYY", help="CVE identifier.")
    patch_parser.add_argument("--package", required=True, help="Vulnerable package name.")
    patch_parser.add_argument("--manifest", required=True, help="Manifest file path (repo-relative).")
    patch_parser.add_argument("--old-version", required=True, dest="old_version", help="Current version.")
    patch_parser.add_argument("--new-version", required=True, dest="new_version", help="Patched version.")
    patch_parser.add_argument("--severity", default="UNKNOWN", help="Severity level (HIGH, CRITICAL, …).")
    patch_parser.add_argument("--base-branch", dest="base_branch", help="Base branch for the PR.")
    patch_parser.add_argument("--description", help="Human-readable CVE description.")
    patch_parser.add_argument("--testing-notes", dest="testing_notes", help="Testing recommendations.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "patch":
        return cmd_patch(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
