"""
Root conftest.py for pytest configuration
"""

import os
import sys

import django
import pytest  # type: ignore
from django.conf import settings
from django.db.backends.base.base import BaseDatabaseWrapper

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db: BaseDatabaseWrapper) -> None:
    """
    Global fixture that enables database access for all tests
    """
    pass
