"""
models.py - Data models for the Security Vulnerability Patcher.

Classes
-------
Dependency
    Represents a single parsed dependency with version, ecosystem type,
    source file location, and specifier information.

ScanResult
    Aggregates the results of scanning a repository: the list of discovered
    manifest files, all extracted dependencies, and any errors encountered.

Both classes provide serialisation helpers (to_dict, to_json, to_csv).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class Dependency:
    """
    A single dependency entry extracted from a manifest file.

    Attributes
    ----------
    name:
        Package name (e.g. ``"requests"``).
    version:
        Version string exactly as found in the manifest
        (e.g. ``"2.28.0"``).  Empty string when unpinned.
    type:
        Ecosystem identifier, e.g. ``"pip"``, ``"npm"``, ``"gem"``,
        ``"go"``, ``"maven"``, ``"cargo"``.
    source_file:
        Repository-relative path to the manifest file that contained
        this dependency.
    line_number:
        1-based line number in *source_file* where the dependency was
        found.  ``0`` when the line number is not tracked.
    specifier:
        Version specifier operator (e.g. ``"=="``, ``">="``, ``"~>"``).
        Empty string when absent.
    """

    name: str
    version: str
    type: str
    source_file: str
    line_number: int = 0
    specifier: str = ""

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain-dict representation of this dependency."""
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "specifier": self.specifier,
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Dependency":
        """Reconstruct a :class:`Dependency` from a plain dict."""
        return cls(
            name=data["name"],
            version=data.get("version", ""),
            type=data.get("type", ""),
            source_file=data.get("source_file", ""),
            line_number=int(data.get("line_number", 0)),
            specifier=data.get("specifier", ""),
        )


@dataclass
class ScanResult:
    """
    The output of scanning one repository.

    Attributes
    ----------
    repo_name:
        Human-readable identifier for the scanned repository
        (e.g. ``"owner/repo"`` or a local path).
    scan_time:
        UTC timestamp of when the scan was started.
    manifest_files:
        Paths of all manifest files discovered during the scan.
    dependencies:
        All :class:`Dependency` objects extracted across all manifests.
    errors:
        Human-readable error messages for files that could not be parsed.
    """

    repo_name: str
    scan_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    manifest_files: List[str] = field(default_factory=list)
    dependencies: List[Dependency] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def total_dependencies(self) -> int:
        """Total number of dependencies found."""
        return len(self.dependencies)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain-dict representation of this scan result."""
        return {
            "repo_name": self.repo_name,
            "scan_time": self.scan_time.isoformat(),
            "manifest_files": self.manifest_files,
            "total_dependencies": self.total_dependencies,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "errors": self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_csv(self) -> str:
        """
        Return a CSV string with one row per dependency.

        Columns: name, version, type, source_file, line_number, specifier
        """
        output = io.StringIO()
        fieldnames = ["name", "version", "type", "source_file", "line_number", "specifier"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for dep in self.dependencies:
            writer.writerow(dep.to_dict())
        return output.getvalue()

    @classmethod
    def from_dict(cls, data: dict) -> "ScanResult":
        """Reconstruct a :class:`ScanResult` from a plain dict."""
        return cls(
            repo_name=data["repo_name"],
            scan_time=datetime.fromisoformat(data["scan_time"]),
            manifest_files=data.get("manifest_files", []),
            dependencies=[Dependency.from_dict(d) for d in data.get("dependencies", [])],
            errors=data.get("errors", []),
        )
