"""
config.py - Configuration management for the Security Vulnerability Patcher.

Loads GitHub API credentials and other settings from environment variables
or a .env file using python-dotenv.
"""

import os
from dotenv import load_dotenv

# Load variables from a .env file if present (ignored in CI/production)
load_dotenv()


class Config:
    """Central configuration object for the Security Patcher system."""

    # ---------------------------------------------------------------------------
    # GitHub credentials
    # ---------------------------------------------------------------------------
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_USERNAME: str = os.getenv("GITHUB_USERNAME", "")

    # ---------------------------------------------------------------------------
    # Default target repository (owner/repo format)
    # ---------------------------------------------------------------------------
    TARGET_REPO: str = os.getenv("TARGET_REPO", "Bylerma/Security-Patcher")

    # ---------------------------------------------------------------------------
    # Paths
    # ---------------------------------------------------------------------------
    # Root directory of the local clone being scanned
    LOCAL_REPO_PATH: str = os.getenv("LOCAL_REPO_PATH", ".")

    # ---------------------------------------------------------------------------
    # Branch / PR settings
    # ---------------------------------------------------------------------------
    DEFAULT_BASE_BRANCH: str = os.getenv("DEFAULT_BASE_BRANCH", "main")
    BRANCH_PREFIX: str = os.getenv("BRANCH_PREFIX", "fix/security-")

    # ---------------------------------------------------------------------------
    # Supported manifest file names (used by DependencyParser)
    # ---------------------------------------------------------------------------
    MANIFEST_FILES: list = [
        "requirements.txt",
        "package.json",
        "Gemfile",
        "go.mod",
        "pom.xml",
        "Cargo.toml",
    ]

    @classmethod
    def validate(cls) -> None:
        """Raise a ValueError if required credentials are missing."""
        if not cls.GITHUB_TOKEN:
            raise ValueError(
                "GITHUB_TOKEN is not set. "
                "Export it as an environment variable or add it to your .env file."
            )

    @classmethod
    def as_dict(cls) -> dict:
        """Return a sanitized snapshot of the current configuration."""
        return {
            "GITHUB_USERNAME": cls.GITHUB_USERNAME,
            "TARGET_REPO": cls.TARGET_REPO,
            "LOCAL_REPO_PATH": cls.LOCAL_REPO_PATH,
            "DEFAULT_BASE_BRANCH": cls.DEFAULT_BASE_BRANCH,
            "BRANCH_PREFIX": cls.BRANCH_PREFIX,
            "MANIFEST_FILES": cls.MANIFEST_FILES,
            # Token intentionally omitted from the snapshot
            "GITHUB_TOKEN": "***" if cls.GITHUB_TOKEN else "(not set)",
        }
