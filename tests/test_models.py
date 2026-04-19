"""
Tests for src/models.py

Covers Dependency and ScanResult dataclasses: construction, properties,
and all serialisation methods (to_dict, to_json, to_csv, from_dict).
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models import Dependency, ScanResult


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


class TestDependency:
    def test_basic_construction(self):
        dep = Dependency(name="requests", version="2.28.0", type="pip", source_file="requirements.txt")
        assert dep.name == "requests"
        assert dep.version == "2.28.0"
        assert dep.type == "pip"
        assert dep.source_file == "requirements.txt"
        assert dep.line_number == 0
        assert dep.specifier == ""

    def test_construction_with_optional_fields(self):
        dep = Dependency(
            name="flask",
            version="2.2.5",
            type="pip",
            source_file="requirements.txt",
            line_number=5,
            specifier=">=",
        )
        assert dep.line_number == 5
        assert dep.specifier == ">="

    def test_to_dict(self):
        dep = Dependency(
            name="express",
            version="^4.18.0",
            type="npm",
            source_file="package.json",
            line_number=3,
            specifier="^",
        )
        d = dep.to_dict()
        assert d["name"] == "express"
        assert d["version"] == "^4.18.0"
        assert d["type"] == "npm"
        assert d["source_file"] == "package.json"
        assert d["line_number"] == 3
        assert d["specifier"] == "^"

    def test_to_json_is_valid(self):
        dep = Dependency(name="serde", version="1.0", type="cargo", source_file="Cargo.toml")
        raw = dep.to_json()
        parsed = json.loads(raw)
        assert parsed["name"] == "serde"
        assert parsed["version"] == "1.0"

    def test_from_dict_roundtrip(self):
        dep = Dependency(
            name="rails",
            version="6.1.0",
            type="gem",
            source_file="Gemfile",
            line_number=2,
            specifier="~>",
        )
        restored = Dependency.from_dict(dep.to_dict())
        assert restored.name == dep.name
        assert restored.version == dep.version
        assert restored.type == dep.type
        assert restored.source_file == dep.source_file
        assert restored.line_number == dep.line_number
        assert restored.specifier == dep.specifier

    def test_from_dict_missing_optional_fields(self):
        dep = Dependency.from_dict({"name": "pkg", "version": "1.0", "type": "pip", "source_file": "req.txt"})
        assert dep.line_number == 0
        assert dep.specifier == ""


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------


class TestScanResult:
    def _make_result(self) -> ScanResult:
        deps = [
            Dependency(name="requests", version="2.28.0", type="pip", source_file="requirements.txt", line_number=1, specifier="=="),
            Dependency(name="flask", version="2.2.5", type="pip", source_file="requirements.txt", line_number=2, specifier=">="),
            Dependency(name="express", version="^4.18.0", type="npm", source_file="package.json"),
        ]
        return ScanResult(
            repo_name="owner/repo",
            manifest_files=["requirements.txt", "package.json"],
            dependencies=deps,
            errors=["could not read Cargo.toml"],
        )

    def test_total_dependencies(self):
        result = self._make_result()
        assert result.total_dependencies == 3

    def test_to_dict_keys(self):
        result = self._make_result()
        d = result.to_dict()
        assert "repo_name" in d
        assert "scan_time" in d
        assert "manifest_files" in d
        assert "total_dependencies" in d
        assert "dependencies" in d
        assert "errors" in d

    def test_to_dict_values(self):
        result = self._make_result()
        d = result.to_dict()
        assert d["repo_name"] == "owner/repo"
        assert d["total_dependencies"] == 3
        assert len(d["dependencies"]) == 3
        assert d["errors"] == ["could not read Cargo.toml"]

    def test_to_json_is_valid(self):
        result = self._make_result()
        raw = result.to_json()
        parsed = json.loads(raw)
        assert parsed["repo_name"] == "owner/repo"
        assert len(parsed["dependencies"]) == 3

    def test_to_csv_has_header(self):
        result = self._make_result()
        csv_text = result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 3
        assert "name" in reader.fieldnames
        assert "version" in reader.fieldnames
        assert "type" in reader.fieldnames

    def test_to_csv_values(self):
        result = self._make_result()
        csv_text = result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        names = [r["name"] for r in rows]
        assert "requests" in names
        assert "flask" in names
        assert "express" in names

    def test_from_dict_roundtrip(self):
        result = self._make_result()
        restored = ScanResult.from_dict(result.to_dict())
        assert restored.repo_name == result.repo_name
        assert restored.total_dependencies == result.total_dependencies
        assert restored.manifest_files == result.manifest_files
        assert restored.errors == result.errors

    def test_default_scan_time_is_utc(self):
        result = ScanResult(repo_name="test")
        assert result.scan_time.tzinfo is not None

    def test_empty_result(self):
        result = ScanResult(repo_name="empty/repo")
        assert result.total_dependencies == 0
        assert result.to_csv().startswith("name,")
        d = result.to_dict()
        assert d["dependencies"] == []
