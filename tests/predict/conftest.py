"""Shared fixtures for the prediction tests (factories live in tests/predict/_util.py)."""
from __future__ import annotations

import pytest

from tests.helpers import fixture
from tests.predict._util import full_dossier


@pytest.fixture
def dossier() -> dict:
    return full_dossier()


@pytest.fixture
def analysis() -> dict:
    return fixture("match_analysis")
