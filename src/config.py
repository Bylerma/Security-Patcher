"""
config.py (src) - Configuration for the Security Vulnerability Patcher.

This module re-exports the root-level :class:`~config.Config` and extends it
with additional settings (e.g. NOTION_TOKEN) used by the ``src`` package.
"""

from __future__ import annotations

import os
import sys

# Ensure the project root is on sys.path so the root config.py is importable
# when this module is executed directly or from within the src/ package.
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import Config as _RootConfig  # noqa: E402


class Config(_RootConfig):
    """
    Extended configuration that adds Notion and packaging-related settings
    on top of the root :class:`~config.Config`.
    """

    # Notion integration (Phase 2)
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

    # Output defaults
    DEFAULT_OUTPUT_FORMAT: str = os.getenv("DEFAULT_OUTPUT_FORMAT", "json")

    @classmethod
    def validate(cls) -> None:
        """
        Validate required credentials.

        Raises
        ------
        ValueError
            If GITHUB_TOKEN is not set.
        """
        super().validate()

    @classmethod
    def as_dict(cls) -> dict:
        base = super().as_dict()
        base.update(
            {
                "NOTION_TOKEN": "***" if cls.NOTION_TOKEN else "(not set)",
                "NOTION_DATABASE_ID": cls.NOTION_DATABASE_ID or "(not set)",
                "DEFAULT_OUTPUT_FORMAT": cls.DEFAULT_OUTPUT_FORMAT,
            }
        )
        return base
