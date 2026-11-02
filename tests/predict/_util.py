"""Factories for the prediction tests."""
from __future__ import annotations

from tests.helpers import fixture


def fact(value, status: str = "single_source") -> dict:
    return {"value": value, "unit": None, "claim_ids": ["C-001"], "status": status, "as_of": None}


def full_dossier() -> dict:
    """The dossier fixture plus the goals-against facts the model requires."""
    d = fixture("match_dossier")
    d["facts"]["H.goals_against_avg"] = fact(0.9)
    d["facts"]["A.goals_against_avg"] = fact(1.1)
    return d
