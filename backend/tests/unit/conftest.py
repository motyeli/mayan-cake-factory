"""Pytest fixtures for the unit suite.

The catalog data itself lives in `catalog_fixture.py` so test modules can
import the item IDs directly; a conftest is not importable by name.
"""

import pytest
from app.schemas.catalog import Catalog
from catalog_fixture import build_catalog


@pytest.fixture
def catalog() -> Catalog:
    # Rebuilt per test: several tests deactivate or expire rules, and a shared
    # instance would leak that into every test that followed.
    return build_catalog()
