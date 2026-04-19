"""
exporters.py - Export scan results to multiple output formats.

Public functions
----------------
to_json(scan_result, indent)   → JSON string
to_csv(scan_result)             → CSV string
to_dict(scan_result)            → plain Python dict

All functions accept either a :class:`~src.models.ScanResult` instance or
a raw dict (as returned by :func:`~dependency_parser.DependencyParser.scan`).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Union

from .models import ScanResult


def to_dict(scan_result: Union[ScanResult, dict]) -> dict:
    """
    Convert *scan_result* to a plain Python dictionary.

    Parameters
    ----------
    scan_result:
        Either a :class:`~src.models.ScanResult` instance or a raw dict
        as produced by :meth:`~dependency_parser.DependencyParser.scan`.

    Returns
    -------
    dict
        Plain dictionary representation.
    """
    if isinstance(scan_result, ScanResult):
        return scan_result.to_dict()
    # Assume it's already a dict (e.g. from DependencyParser.scan())
    return dict(scan_result)


def to_json(scan_result: Union[ScanResult, dict], indent: int = 2) -> str:
    """
    Serialise *scan_result* to a JSON string.

    Parameters
    ----------
    scan_result:
        Either a :class:`~src.models.ScanResult` or a raw dict.
    indent:
        JSON indentation level (default: ``2``).

    Returns
    -------
    str
        Pretty-printed JSON.
    """
    return json.dumps(to_dict(scan_result), indent=indent)


def to_csv(scan_result: Union[ScanResult, dict]) -> str:
    """
    Serialise *scan_result* dependencies to a CSV string.

    The CSV has the following columns::

        name, version, type, source_file, line_number, specifier

    When *scan_result* is a raw dict (from the legacy
    :class:`~dependency_parser.DependencyParser`), the ``type``,
    ``line_number``, and ``specifier`` columns will be empty unless
    already present in the raw dict entries.

    Parameters
    ----------
    scan_result:
        Either a :class:`~src.models.ScanResult` or a raw dict.

    Returns
    -------
    str
        CSV-formatted string including header row.
    """
    if isinstance(scan_result, ScanResult):
        return scan_result.to_csv()

    # Handle legacy dict format: {"manifests": [{type, path, dependencies}], ...}
    output = io.StringIO()
    fieldnames = ["name", "version", "type", "source_file", "line_number", "specifier"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    manifests = scan_result.get("manifests", [])
    for manifest in manifests:
        manifest_type = manifest.get("type", "")
        manifest_path = manifest.get("path", "")
        for dep in manifest.get("dependencies", []):
            writer.writerow(
                {
                    "name": dep.get("name", ""),
                    "version": dep.get("version", ""),
                    "type": dep.get("type", manifest_type),
                    "source_file": dep.get("source_file", manifest_path),
                    "line_number": dep.get("line_number", 0),
                    "specifier": dep.get("specifier", ""),
                }
            )
    return output.getvalue()


def write_to_file(content: str, path: str) -> None:
    """
    Write *content* to a file at *path*.

    Parameters
    ----------
    content:
        Text content to write.
    path:
        Destination file path.  Parent directories must already exist.
    """
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
