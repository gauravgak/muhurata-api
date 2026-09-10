"""
Chart engine: determinism + structural invariants + a golden snapshot.

We deliberately do NOT hand-assert "the lagna is Kanya" style values — the
point is to lock the output so a pyswisseph upgrade that shifts numbers is
caught, not to re-derive astrology in the test file.
"""

import datetime as dt
import json
import os

import pytest

from chart_engine import (
    NAKSHATRAS, SIGNS, atmakaraka, compute_chart, running_dasha, vimshottari,
)

BIRTH = dict(local_dt=dt.datetime(1994, 8, 14, 7, 42), lat=19.0760, lon=72.8777,
             utc_offset_hours=5.5)
GOLDEN = os.path.join(os.path.dirname(__file__), "golden_chart.json")


def test_deterministic():
    a = compute_chart(**BIRTH)
    b = compute_chart(**BIRTH)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_structural_invariants():
    c = compute_chart(**BIRTH)
    names = [p["name"] for p in c["positions"]]
    assert names[:8] == ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu"]
    assert "Ketu" in names

    by = {p["name"]: p for p in c["positions"]}
    # Ketu is exactly opposite Rahu.
    assert abs(((by["Ketu"]["longitude"] - by["Rahu"]["longitude"]) % 360) - 180) < 1e-6
    for p in c["positions"]:
        assert 1 <= p["house"] <= 12
        assert p["sign"] in SIGNS
        assert p["nakshatra"] in NAKSHATRAS
        assert p["navamsa_sign"] in SIGNS

    assert c["ascendant"]["sign"] in SIGNS
    assert c["atmakaraka"]["planet"] in {p["name"] for p in c["positions"] if p["name"] != "Ketu"}


def test_vimshottari_contiguous_and_rotation():
    from chart_engine import DASHA_ORDER, DASHA_YEARS

    c = compute_chart(**BIRTH)
    mds = c["vimshottari"]
    assert len(mds) == 9

    # No gaps, no overlaps between consecutive mahadashas.
    for prev, nxt in zip(mds, mds[1:]):
        assert prev["end"] == nxt["start"]

    # The 9 lords are the Vimshottari cycle rotated to start on the
    # birth lord — a permutation, consecutive in DASHA_ORDER.
    lords = [m["lord"] for m in mds]
    assert sorted(lords) == sorted(DASHA_ORDER)
    start = DASHA_ORDER.index(lords[0])
    assert lords == [DASHA_ORDER[(start + k) % 9] for k in range(9)]

    # Every mahadasha after the first runs its full allotted years; the
    # first is only the balance unspent at birth, so the total span is
    # 120y minus the elapsed part of the first period (never negative,
    # never more than 120).
    span_years = (dt.date.fromisoformat(mds[-1]["end"])
                  - dt.date.fromisoformat(mds[0]["start"])).days / 365.2425
    trailing = sum(DASHA_YEARS[l] for l in lords[1:])
    assert trailing < span_years <= 120.5
    assert span_years > 120 - DASHA_YEARS[lords[0]] - 0.5


def test_running_dasha_resolves():
    c = compute_chart(**BIRTH)
    rd = running_dasha(c, when=dt.datetime(2026, 1, 1))
    assert rd is not None
    assert rd["mahadasha"] in {
        "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"}


def test_golden_snapshot():
    """Locks the full chart. Generate once with WRITE_GOLDEN=1 (needs a
    working pyswisseph), commit tests/golden_chart.json, and every later
    run enforces it."""
    c = compute_chart(**BIRTH)
    if os.environ.get("WRITE_GOLDEN") == "1" or not os.path.exists(GOLDEN):
        with open(GOLDEN, "w") as fh:
            json.dump(c, fh, indent=2, sort_keys=True)
        pytest.skip("golden snapshot written; commit tests/golden_chart.json")
    with open(GOLDEN) as fh:
        expected = json.load(fh)
    assert json.loads(json.dumps(c, sort_keys=True)) == expected
