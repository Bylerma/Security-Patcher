"""
Tests for dependency_parser.py

Covers all six manifest parsers using in-memory content strings so no
file system or network access is required.
"""

import os
import sys
import json
import tempfile

import pytest

# Allow importing from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dependency_parser import (
    DependencyParser,
    _parse_requirements_txt,
    _parse_package_json,
    _parse_gemfile,
    _parse_go_mod,
    _parse_pom_xml,
    _parse_cargo_toml,
)


# ---------------------------------------------------------------------------
# Unit tests for individual parsers
# ---------------------------------------------------------------------------


class TestParseRequirementsTxt:
    def test_pinned_versions(self):
        content = "requests==2.28.0\nflask>=2.2.5\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert result["type"] == "requirements.txt"
        deps = {d["name"]: d["version"] for d in result["dependencies"]}
        assert deps["requests"] == "2.28.0"
        assert deps["flask"] == "2.2.5"

    def test_comments_and_blank_lines_skipped(self):
        content = "\n# this is a comment\nrequests==2.28.0\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert len(result["dependencies"]) == 1

    def test_options_flags_skipped(self):
        content = "-r other.txt\n--index-url https://example.com\nflask==2.0.0\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert len(result["dependencies"]) == 1
        assert result["dependencies"][0]["name"] == "flask"

    def test_extras_stripped(self):
        content = "requests[security]==2.28.0\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert result["dependencies"][0]["name"] == "requests"

    def test_no_version(self):
        content = "requests\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert result["dependencies"][0]["name"] == "requests"
        assert result["dependencies"][0]["version"] == ""

    def test_inline_comment_stripped(self):
        content = "requests==2.28.0  # CVE-2023-32681 vulnerable\n"
        result = _parse_requirements_txt(content, "requirements.txt")
        assert result["dependencies"][0]["version"] == "2.28.0"


class TestParsePackageJson:
    def test_dependencies_and_dev_dependencies(self):
        data = {
            "dependencies": {"express": "^4.18.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }
        result = _parse_package_json(json.dumps(data), "package.json")
        assert result["type"] == "package.json"
        deps = {d["name"]: d["version"] for d in result["dependencies"]}
        assert deps["express"] == "^4.18.0"
        assert deps["jest"] == "^29.0.0"

    def test_invalid_json_returns_empty(self):
        result = _parse_package_json("not json", "package.json")
        assert result["dependencies"] == []

    def test_peer_dependencies_included(self):
        data = {"peerDependencies": {"react": ">=17.0.0"}}
        result = _parse_package_json(json.dumps(data), "package.json")
        assert result["dependencies"][0]["name"] == "react"


class TestParseGemfile:
    def test_gem_with_version(self):
        content = "gem 'rails', '~> 6.1'\ngem \"devise\", \">= 4.7\"\n"
        result = _parse_gemfile(content, "Gemfile")
        assert result["type"] == "Gemfile"
        names = [d["name"] for d in result["dependencies"]]
        assert "rails" in names
        assert "devise" in names

    def test_comments_skipped(self):
        content = "# comment\ngem 'rails', '~> 6.1'\n"
        result = _parse_gemfile(content, "Gemfile")
        assert len(result["dependencies"]) == 1


class TestParseGoMod:
    def test_require_block(self):
        content = (
            "module example.com/mymod\n\n"
            "go 1.20\n\n"
            "require (\n"
            "\tgithub.com/gin-gonic/gin v1.9.1\n"
            "\tgolang.org/x/net v0.11.0\n"
            ")\n"
        )
        result = _parse_go_mod(content, "go.mod")
        assert result["type"] == "go.mod"
        deps = {d["name"]: d["version"] for d in result["dependencies"]}
        assert deps["github.com/gin-gonic/gin"] == "v1.9.1"
        assert deps["golang.org/x/net"] == "v0.11.0"

    def test_single_require_line(self):
        content = "require github.com/foo/bar v1.0.0\n"
        result = _parse_go_mod(content, "go.mod")
        assert result["dependencies"][0]["name"] == "github.com/foo/bar"
        assert result["dependencies"][0]["version"] == "v1.0.0"


class TestParsePomXml:
    def test_basic_dependencies(self):
        content = """<?xml version="1.0"?>
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-core</artifactId>
      <version>5.3.27</version>
    </dependency>
  </dependencies>
</project>"""
        result = _parse_pom_xml(content, "pom.xml")
        assert result["type"] == "pom.xml"
        assert result["dependencies"][0]["name"] == "org.springframework:spring-core"
        assert result["dependencies"][0]["version"] == "5.3.27"

    def test_invalid_xml_returns_empty(self):
        result = _parse_pom_xml("<broken", "pom.xml")
        assert result["dependencies"] == []


class TestParseCargoToml:
    def test_string_version(self):
        content = "[dependencies]\nserde = \"1.0\"\ntokio = \"1.28.0\"\n"
        result = _parse_cargo_toml(content, "Cargo.toml")
        assert result["type"] == "Cargo.toml"
        deps = {d["name"]: d["version"] for d in result["dependencies"]}
        assert deps["serde"] == "1.0"
        assert deps["tokio"] == "1.28.0"

    def test_dev_dependencies(self):
        content = "[dev-dependencies]\npretty_assertions = \"1.4.0\"\n"
        result = _parse_cargo_toml(content, "Cargo.toml")
        assert result["dependencies"][0]["name"] == "pretty_assertions"


# ---------------------------------------------------------------------------
# Integration test – DependencyParser local scan
# ---------------------------------------------------------------------------


class TestDependencyParserLocal:
    def test_scan_discovers_requirements_txt(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.28.0\nflask>=2.2.5\n")

        parser = DependencyParser(local_path=str(tmp_path))
        result = parser.scan()

        assert result["scan_source"] == "local"
        assert len(result["manifests"]) == 1
        assert result["total_dependencies"] == 2

    def test_scan_multiple_manifests(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        pkg = {"dependencies": {"express": "^4.18.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        parser = DependencyParser(local_path=str(tmp_path))
        result = parser.scan()

        assert result["total_dependencies"] == 2
        types = {m["type"] for m in result["manifests"]}
        assert "requirements.txt" in types
        assert "package.json" in types

    def test_scan_nested_directory(self, tmp_path):
        subdir = tmp_path / "subproject"
        subdir.mkdir()
        (subdir / "requirements.txt").write_text("django==4.2.0\n")

        parser = DependencyParser(local_path=str(tmp_path))
        result = parser.scan()

        assert result["total_dependencies"] == 1

    def test_scan_no_manifests_returns_empty(self, tmp_path):
        (tmp_path / "README.md").write_text("# Hello")

        parser = DependencyParser(local_path=str(tmp_path))
        result = parser.scan()

        assert result["manifests"] == []
        assert result["total_dependencies"] == 0

    def test_missing_local_and_github_raises(self):
        with pytest.raises(ValueError, match="Provide either"):
            DependencyParser()
