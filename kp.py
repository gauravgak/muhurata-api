"""
kp.py — Krishnamurti Paddhati (KP) system.

KP subdivides each nakshatra (star) by the Vimshottari dasha proportions,
so every point in the zodiac has a SIGN lord, a STAR (nakshatra) lord, and
a SUB lord. The sub lord is KP's key innovation - it's what most KP
prediction hinges on.

The maths: the 120-year Vimshottari cycle assigns each of 9 planets a span
(Ketu 7yr, Venus 20, Sun 6, Moon 10, Mars 7, Rahu 18, Jupiter 16, Sat 19,
Merc 17). Within each 13deg20' nakshatra, those same 9 planets get sub-
divisions proportional to their dasha years. So finding a sub lord means:
which nakshatra am I in (star lord), then how far into it, mapped onto the
proportional sub-divisions (sub lord).

Validated against the AstroTalk KP screenshot for a known chart.
"""

from chart_engine import NAKSHATRAS, SIGNS, _sign

# Vimshottari order and years - the backbone of all KP subdivision.
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars",
               "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
               "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
TOTAL = 120.0

SIGN_LORD = {
    "Mesha": "Mars", "Vrishabha": "Venus", "Mithuna": "Mercury", "Karka": "Moon",
    "Simha": "Sun", "Kanya": "Mercury", "Tula": "Venus", "Vrischika": "Mars",
    "Dhanu": "Jupiter", "Makara": "Saturn", "Kumbha": "Saturn", "Meena": "Jupiter",
}

NAK_SPAN = 360.0 / 27          # 13.333... degrees
_STAR_LORDS = DASHA_ORDER      # nakshatra lords cycle in Vimshottari order


def _star_lord(nak_idx: int) -> str:
    return _STAR_LORDS[nak_idx % 9]


def _sub_lord(lon: float):
    """Given a sidereal longitude, return (star_lord, sub_lord).

    Within the nakshatra the longitude falls in, walk the 9 sub-divisions
    (each proportional to that planet's dasha years) starting from the
    star lord, and see which sub-division the longitude lands in."""
    nak_idx = int(lon // NAK_SPAN)
    into_nak = lon - nak_idx * NAK_SPAN     # degrees into this nakshatra
    fraction = into_nak / NAK_SPAN          # 0..1 through the nakshatra

    star_lord = _star_lord(nak_idx)
    start = DASHA_ORDER.index(star_lord)

    # subs run in Vimshottari order starting FROM the star lord, each sized
    # proportional to its dasha years over 120.
    cursor = 0.0
    for k in range(9):
        planet = DASHA_ORDER[(start + k) % 9]
        width = DASHA_YEARS[planet] / TOTAL
        if fraction < cursor + width or k == 8:
            return star_lord, planet
        cursor += width
    return star_lord, star_lord   # unreachable, but safe


def kp_lords(lon: float) -> dict:
    """Full KP lord set for any longitude: sign, star, and sub lord."""
    sign = SIGNS[_sign(lon)]
    nak_idx = int(lon // NAK_SPAN)
    star_lord, sub_lord = _sub_lord(lon)
    return {
        "sign": sign,
        "sign_lord": SIGN_LORD[sign],
        "nakshatra": NAKSHATRAS[nak_idx],
        "star_lord": star_lord,
        "sub_lord": sub_lord,
    }


def kp_planets(chart: dict) -> list:
    """KP table for every planet: sign, sign lord, star, star lord, sub
    lord - the 'KP Planets' table AstroTalk shows."""
    rows = []
    for p in chart["positions"]:
        lords = kp_lords(p["longitude"])
        rows.append({
            "planet": p["name"],
            "sign": lords["sign"],
            "sign_lord": lords["sign_lord"],
            "nakshatra": lords["nakshatra"],
            "star_lord": lords["star_lord"],
            "sub_lord": lords["sub_lord"],
            "house": p["house"],
        })
    return rows


def ruling_planets(chart: dict) -> dict:
    """The KP 'Ruling Planets' set: the lords of the ascendant and Moon
    across sign/star/sub, plus the day lord. Used in KP for timing."""
    asc_lon = chart["ascendant"]["longitude"]
    moon = next(p for p in chart["positions"] if p["name"] == "Moon")

    asc = kp_lords(asc_lon)
    mon = kp_lords(moon["longitude"])

    return {
        "asc_sign_lord": asc["sign_lord"],
        "asc_star_lord": asc["star_lord"],
        "asc_sub_lord": asc["sub_lord"],
        "moon_sign_lord": mon["sign_lord"],
        "moon_star_lord": mon["star_lord"],
        "moon_sub_lord": mon["sub_lord"],
    }


def kp_cusps(chart: dict) -> list:
    """KP cusp table: for each of the 12 house cusps, its sign, star lord,
    and sub lord. Uses whole-sign cusps (cusp N = start of the Nth sign
    from the ascendant) - the simplest KP cusp convention. A future
    upgrade could use Placidus cusps, which KP traditionally prefers, but
    that needs the house-cusp longitudes from swe.houses with 'P'."""
    asc_sign_idx = _sign(chart["ascendant"]["longitude"])
    cusps = []
    for h in range(12):
        cusp_lon = ((asc_sign_idx + h) % 12) * 30.0 + (chart["ascendant"]["longitude"] % 30)
        lords = kp_lords(cusp_lon % 360)
        cusps.append({
            "cusp": h + 1,
            "sign": lords["sign"],
            "sign_lord": lords["sign_lord"],
            "star_lord": lords["star_lord"],
            "sub_lord": lords["sub_lord"],
        })
    return cusps
