"""The rules' track cache must never answer for a different document that reuses a freed one's id()."""
from __future__ import annotations

import gc
import weakref

import pytest

from tests.helpers import fixture
from tms.validate.choreo_rules import T

pytestmark = pytest.mark.fast


class Doc(dict):
    """A dict that can be weakly referenced."""


def test_the_cached_document_stays_alive_so_its_id_cannot_be_reused():
    doc = Doc(fixture("choreography"))
    ref = weakref.ref(doc)
    T(doc)
    del doc
    gc.collect()
    assert ref() is not None


def test_a_different_document_gets_its_own_tracks():
    a, b = Doc(fixture("choreography")), Doc(fixture("choreography"))
    assert T(a) is T(a)
    assert T(b) is not T(a)
