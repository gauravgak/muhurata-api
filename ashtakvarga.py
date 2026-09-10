"""
ashtakvarga.py — the Ashtakavarga benefic-point system.

For each of the seven planets (Sun..Saturn) plus the Ascendant, classical
texts give a table saying, from that planet's position, which houses (1-12
counted from it) receive a benefic point (bindu) contributed by each of the
eight reference points (the 7 planets + Ascendant).

Summed up, each planet gets a Bhinnashtakavarga (its own 12-sign score row),
and all seven planets' rows summed give the Sarvashtakavarga - the master
12-sign strength map.

The invariants that PROVE the tables are right:
  - Each planet's Bhinnashtakavarga sums to a fixed known total:
    Sun 48, Moon 49, Mars 39, Mercury 54, Jupiter 56, Venus 52, Saturn 39.
  - Those total 337, so the Sarvashtakavarga always sums to exactly 337.
If a table has a transcription error, these totals will not land. That is
the test - no need to eyeball 96 numbers.

Tables below are the standard Parashari benefic-point contributions, keyed
by contributor -> list of houses (1-based, from the planet being scored)
that get a bindu.
"""

# For each planet being scored (outer key), from each contributor (inner
# key), the list of house-positions (1..12, counted from the scored planet's
# sign) that receive a bindu. This is the canonical Parashari set.
BINDU_TABLES = {
    "Sun": {
        "Sun": [1, 2, 4, 7, 8, 9, 10, 11],
        "Moon": [3, 6, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [5, 6, 9, 11],
        "Venus": [6, 7, 12],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Ascendant": [3, 4, 6, 10, 11, 12],
    },
    "Moon": {
        "Sun": [3, 6, 7, 8, 10, 11],
        "Moon": [1, 3, 6, 7, 10, 11],
        "Mars": [2, 3, 5, 6, 9, 10, 11],
        "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
        "Jupiter": [1, 2, 4, 7, 8, 10, 11, 12],
        "Venus": [3, 4, 5, 7, 9, 10, 11],
        "Saturn": [3, 5, 6, 11],
        "Ascendant": [3, 6, 11],
    },
    "Mars": {
        "Sun": [3, 5, 6, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [3, 5, 6, 11],
        "Jupiter": [6, 10, 11, 12],
        "Venus": [6, 8, 11, 12],
        "Saturn": [1, 4, 7, 8, 9, 10, 11],
        "Ascendant": [1, 3, 6, 10, 11],
    },
    "Mercury": {
        "Sun": [5, 6, 9, 11, 12],
        "Moon": [2, 4, 6, 8, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [6, 8, 11, 12],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 11],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Ascendant": [1, 2, 4, 6, 8, 10, 11],
    },
    "Jupiter": {
        "Sun": [1, 2, 3, 4, 7, 8, 9, 10, 11],
        "Moon": [2, 5, 7, 9, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
        "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
        "Venus": [2, 5, 6, 9, 10, 11],
        "Saturn": [3, 5, 6, 12],
        "Ascendant": [1, 2, 4, 5, 6, 7, 9, 10, 11],
    },
    "Venus": {
        "Sun": [8, 11, 12],
        "Moon": [1, 2, 3, 4, 5, 8, 9, 11, 12],
        "Mars": [3, 5, 6, 9, 11, 12],
        "Mercury": [3, 5, 6, 9, 11],
        "Jupiter": [5, 8, 9, 10, 11],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "Saturn": [3, 4, 5, 8, 9, 10, 11],
        "Ascendant": [1, 2, 3, 4, 5, 8, 9, 11],
    },
    "Saturn": {
        "Sun": [1, 2, 4, 7, 8, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [3, 5, 6, 10, 11, 12],
        "Mercury": [6, 8, 9, 10, 11, 12],
        "Jupiter": [5, 6, 11, 12],
        "Venus": [6, 11, 12],
        "Saturn": [3, 5, 6, 11],
        "Ascendant": [1, 3, 4, 6, 10, 11],
    },
}

# Known correct row totals - the proof-of-correctness invariants.
EXPECTED_TOTALS = {
    "Sun": 48, "Moon": 49, "Mars": 39, "Mercury": 54,
    "Jupiter": 56, "Venus": 52, "Saturn": 39,
}
SARVA_TOTAL = 337

from chart_engine import SIGNS, _sign

CONTRIBUTORS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Ascendant"]


def _sign_of(chart, name):
    if name == "Ascendant":
        return _sign(chart["ascendant"]["longitude"])
    p = next(p for p in chart["positions"] if p["name"] == name)
    return _sign(p["longitude"])


def bhinnashtakavarga(chart: dict, planet: str) -> list:
    """The 12-sign bindu row for one planet. Index 0 = Aries ... 11 = Pisces.
    Each entry is 0-8 bindus."""
    row = [0] * 12
    table = BINDU_TABLES[planet]
    for contributor in CONTRIBUTORS:
        contrib_sign = _sign_of(chart, contributor)
        for house in table[contributor]:
            # house is 1-based counted from the contributor's sign
            target_sign = (contrib_sign + house - 1) % 12
            row[target_sign] += 1
    return row


def sarvashtakavarga(chart: dict) -> dict:
    """Every planet's Bhinnashtakavarga plus the summed Sarvashtakavarga."""
    bhinna = {}
    for planet in EXPECTED_TOTALS:
        bhinna[planet] = bhinnashtakavarga(chart, planet)

    sarva = [0] * 12
    for planet, row in bhinna.items():
        for i in range(12):
            sarva[i] += row[i]

    # attach sign labels for display
    labelled_bhinna = {
        planet: [{"sign": SIGNS[i], "bindus": row[i]} for i in range(12)]
        for planet, row in bhinna.items()
    }
    labelled_sarva = [{"sign": SIGNS[i], "bindus": sarva[i]} for i in range(12)]

    return {
        "bhinna": labelled_bhinna,
        "bhinna_raw": bhinna,          # unlabelled rows, for validation
        "sarva": labelled_sarva,
        "sarva_total": sum(sarva),
        "bhinna_totals": {p: sum(r) for p, r in bhinna.items()},
    }
