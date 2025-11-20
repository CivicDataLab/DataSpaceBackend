"""Setup configuration for DataSpace Python SDK."""

import os
from typing import Any, Dict

from setuptools import find_packages, setup

# Read version from __version__.py
version: Dict[str, Any] = {}
version_file = os.path.join(os.path.dirname(__file__), "dataspace_sdk", "__version__.py")
with open(version_file, "r", encoding="utf-8") as f:
    exec(f.read(), version)

with open("docs/sdk/README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="dataspace-sdk",
    version=version["__version__"],
    author="CivicDataLab",
    author_email="tech@civicdatalab.in",
    description="Python SDK for DataSpace API - programmatic access to datasets, AI models, and use cases",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CivicDataLab/DataExchange",
    packages=find_packages(include=["dataspace_sdk", "dataspace_sdk.*"]),
    license="AGPL-3.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "types-requests>=2.28.0",
        ],
    },
    keywords="dataspace api sdk datasets aimodels usecases",
    project_urls={
        "Bug Reports": "https://github.com/CivicDataLab/DataExchange/issues",
        "Source": "https://github.com/CivicDataLab/DataExchange",
        "Documentation": "https://github.com/CivicDataLab/DataExchange/blob/main/docs/sdk/README.md",
    },
)
