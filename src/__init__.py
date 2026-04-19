"""
Security Patcher – src package.

Public API
----------
from src.models import Dependency, ScanResult
from src.exporters import to_json, to_csv, to_dict
from src.github_scanner import GitHubScanner
"""

from .models import Dependency, ScanResult
from .exporters import to_csv, to_dict, to_json
from .github_scanner import GitHubScanner

__all__ = [
    "Dependency",
    "ScanResult",
    "to_json",
    "to_csv",
    "to_dict",
    "GitHubScanner",
]
