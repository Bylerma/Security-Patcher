"""
main.py (src) - Enhanced CLI entry point for the Security Vulnerability Patcher.

Command-line arguments
----------------------
--repo-path PATH        Scan a local repository at PATH.
--github-url OWNER/REPO Scan a remote GitHub repository.
--branch BRANCH         Branch to scan (default: HEAD).
--output-format FORMAT  Output format: json | csv | dict (default: json).
--output-file FILE      Write output to FILE instead of stdout.
--log-level LEVEL       Logging verbosity (DEBUG|INFO|WARNING|ERROR).

Examples
--------
Scan a local repo and print JSON::

    python -m src.main --repo-path /path/to/repo

Scan a remote repo and save CSV::

    python -m src.main --github-url owner/repo \\
                       --output-format csv \\
                       --output-file deps.csv

Scan a specific branch::

    python -m src.main --github-url owner/repo --branch develop
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure the project root is importable (needed when running as __main__)
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dependency_parser import DependencyParser  # root-level parser
from src.config import Config
from src.exporters import to_csv, to_json, write_to_file
from src.github_scanner import GitHubScanner
from src.models import Dependency, ScanResult

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("security_patcher.src")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_output(result: object, fmt: str) -> str:
    """Render *result* in the requested *fmt* (json | csv | dict)."""
    if fmt == "csv":
        return to_csv(result)  # type: ignore[arg-type]
    if fmt == "dict":
        from src.exporters import to_dict

        return repr(to_dict(result))  # type: ignore[arg-type]
    # Default: JSON
    return to_json(result)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_scan_local(repo_path: str, output_format: str, output_file: str | None) -> int:
    """Scan a local repository."""
    logger.info("Scanning local repository: %s", repo_path)
    parser = DependencyParser(local_path=repo_path)
    raw_result = parser.scan()

    output = _format_output(raw_result, output_format)
    if output_file:
        write_to_file(output, output_file)
        logger.info("Results written to %s", output_file)
    else:
        print(output)
    return 0


def cmd_scan_github(
    github_url: str,
    branch: str,
    output_format: str,
    output_file: str | None,
) -> int:
    """Scan a remote GitHub repository."""
    try:
        Config.validate()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    try:
        from github import Github  # noqa: PLC0415
    except ImportError:
        logger.error("PyGithub is required for remote scanning. Install it with: pip install PyGithub")
        return 1

    gh = Github(Config.GITHUB_TOKEN)
    try:
        repo = gh.get_repo(github_url)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not access repository '%s': %s", github_url, exc)
        return 1

    logger.info("Scanning GitHub repository: %s (branch: %s)", github_url, branch)
    scanner = GitHubScanner(repo, branch=branch)
    result = scanner.scan()

    if result.errors:
        for err in result.errors:
            logger.warning("Scan error: %s", err)

    output = _format_output(result, output_format)
    if output_file:
        write_to_file(output, output_file)
        logger.info("Results written to %s", output_file)
    else:
        print(output)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="security-patcher-src",
        description="Security Vulnerability Patcher – enhanced dependency scanner.",
    )

    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--repo-path",
        metavar="PATH",
        help="Path to a local repository clone.",
    )
    source.add_argument(
        "--github-url",
        metavar="OWNER/REPO",
        help="Remote GitHub repository in 'owner/repo' format.",
    )

    p.add_argument(
        "--branch",
        default="HEAD",
        metavar="BRANCH",
        help="Branch or commit SHA to scan (remote only, default: HEAD).",
    )
    p.add_argument(
        "--output-format",
        choices=["json", "csv", "dict"],
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    p.add_argument(
        "--output-file",
        metavar="FILE",
        dest="output_file",
        help="Write output to FILE instead of stdout.",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        dest="log_level",
        help="Logging verbosity (default: INFO).",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    arg_parser = build_parser()
    args = arg_parser.parse_args(argv)

    logging.getLogger().setLevel(args.log_level)

    if args.repo_path:
        return cmd_scan_local(
            repo_path=args.repo_path,
            output_format=args.output_format,
            output_file=args.output_file,
        )

    return cmd_scan_github(
        github_url=args.github_url,
        branch=args.branch,
        output_format=args.output_format,
        output_file=args.output_file,
    )


if __name__ == "__main__":
    sys.exit(main())
