"""Team colours from real kits: the number colour must stay readable whatever the shirt."""
from __future__ import annotations

import pytest

from tms import theme

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("shirt", ["#ef0107", "#ffffff", "#f2c80f", "#034694", "#000000", "#7a263a", "#6cabdd"])
def test_numbers_stay_readable_on_real_shirts(shirt):
    fill, _ring, text = theme.kit_colours(shirt)
    assert fill == shirt and theme._contrast(fill, text) >= 4.5  # BR-03


def test_trim_becomes_the_ring():
    assert theme.kit_colours("#EF0107,#FFFFFF")[:2] == ("#ef0107", "#ffffff")


@pytest.mark.parametrize("bad", ["red", "#ef01", "#ef0107,#fff", "#ef0107,#ffffff,#000000"])
def test_bad_colours_are_refused(bad):
    with pytest.raises(ValueError):
        theme.kit_colours(bad)
