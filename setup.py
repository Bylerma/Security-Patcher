"""
setup.py - Package configuration for Security-Patcher.

Install in development mode::

    pip install -e .

Or build a distribution::

    python setup.py sdist bdist_wheel
"""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="security-patcher",
    version="0.1.0",
    author="Bylerma",
    description=(
        "An autonomous Security Vulnerability Patcher that scans repositories "
        "for dependency manifests and opens automated fix Pull Requests."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Bylerma/Security-Patcher",
    packages=find_packages(exclude=["tests*", "examples*"]),
    python_requires=">=3.10",
    install_requires=[
        "PyGithub>=1.59.0",
        "GitPython>=3.1.40",
        "packaging>=23.0",
        "toml>=0.10.2",
        "pyyaml>=6.0.1",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "security-patcher=main:main",
            "security-patcher-src=src.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Security",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    keywords="security vulnerability patcher dependencies CVE GitHub",
)
