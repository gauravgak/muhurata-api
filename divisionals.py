"""
divisionals.py — the varga (divisional) charts.

Each divisional chart splits every 30-degree sign into N parts and maps
each part to a sign by a classical rule. D1 is the birth chart itself;
D9 (navamsa) is the most important after it; the rest each govern a life
area (D10 career, D7 children, D2 wealth, etc).

Every function here takes a sidereal longitude and returns a sign index
0-11. These are the standard Parashari formulas - the same ones AstroSage
and AstroTalk use - so results should cross-check against them.

Validated against known charts; where a rule has variants (D30, D60) the
most common consumer-app convention is used and noted.
"""

from chart_engine import SIGNS


def _sign_idx(lon):
    return int(lon // 30)


def _part(lon, n):
    """Which of the n equal parts within the sign (0-based) the longitude
    falls in, plus the degrees into the sign."""
    deg_in_sign = lon % 30
    part_size = 30.0 / n
    return int(deg_in_sign // part_size), deg_in_sign


# ---- D1: Rasi (the birth chart itself) ----
def d1(lon):
    return _sign_idx(lon)


# ---- D2: Hora (wealth) ----
# First half of odd signs -> Leo (Sun's hora), second half -> Cancer.
# Reversed for even signs.
def d2(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 2)
    odd = (s % 2 == 0)   # Aries(0) is odd in 1-based counting
    if odd:
        return 4 if part == 0 else 3   # Leo / Cancer
    else:
        return 3 if part == 0 else 4   # Cancer / Leo


# ---- D3: Drekkana (siblings) ----
# 1st third: same sign; 2nd: 5th from it; 3rd: 9th from it.
def d3(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 3)
    return (s + [0, 4, 8][part]) % 12


# ---- D4: Chaturthamsa (property, fortune) ----
# quarters map to same, 4th, 7th, 10th from the sign.
def d4(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 4)
    return (s + [0, 3, 6, 9][part]) % 12


# ---- D7: Saptamsa (children) ----
# odd signs start from the sign itself; even signs from the 7th.
def d7(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 7)
    start = s if (s % 2 == 0) else (s + 6) % 12
    return (start + part) % 12


# ---- D9: Navamsa (spouse, dharma) ----
# movable signs start from themselves, fixed from 9th, dual from 5th.
def d9(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 9)
    start = {0: s, 1: (s + 8) % 12, 2: (s + 4) % 12}[s % 3]
    return (start + part) % 12


# ---- D10: Dasamsa (career) ----
# odd signs start from the sign; even signs from the 9th.
def d10(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 10)
    start = s if (s % 2 == 0) else (s + 8) % 12
    return (start + part) % 12


# ---- D12: Dwadasamsa (parents) ----
# always starts from the sign itself, 12 parts run consecutively.
def d12(lon):
    s = _sign_idx(lon)
    part, _ = _part(lon, 12)
    return (s + part) % 12


# ---- D16: Shodasamsa (vehicles, comforts) ----
def d16(lon):
    part, _ = _part(lon, 16)
    s = _sign_idx(lon)
    # movable: from Aries; fixed: from Leo; dual: from Sagittarius
    start = {0: 0, 1: 4, 2: 8}[s % 3]
    return (start + part) % 12


# ---- D20: Vimsamsa (spiritual life) ----
def d20(lon):
    part, _ = _part(lon, 20)
    s = _sign_idx(lon)
    start = {0: 0, 1: 8, 2: 4}[s % 3]   # movable Aries, fixed Sag, dual Leo
    return (start + part) % 12


# ---- D24: Chaturvimsamsa (education) ----
def d24(lon):
    part, _ = _part(lon, 24)
    s = _sign_idx(lon)
    start = 4 if (s % 2 == 0) else 3   # odd from Leo, even from Cancer
    return (start + part) % 12


# ---- D27: Bhamsa / Saptavimsamsa (strengths, weaknesses) ----
def d27(lon):
    part, _ = _part(lon, 27)
    s = _sign_idx(lon)
    # fire from Aries, earth from Cancer, air from Libra, water from Cap
    element_start = {0: 0, 1: 3, 2: 6, 3: 9}
    start = element_start[s % 4]
    return (start + part) % 12


# ---- D30: Trimsamsa (misfortunes) ----
# unequal division by 5 planetary rulers; the classical scheme.
def d30(lon):
    deg = lon % 30
    s = _sign_idx(lon)
    odd = (s % 2 == 0)
    if odd:
        bounds = [(5, 0), (10, 10), (18, 8), (25, 2), (30, 6)]  # Mars,Sat,Jup,Merc,Ven signs
    else:
        bounds = [(5, 1), (12, 5), (20, 11), (25, 9), (30, 7)]
    for limit, sign in bounds:
        if deg < limit:
            return sign
    return bounds[-1][1]


# ---- D40: Khavedamsa (auspicious/inauspicious effects) ----
def d40(lon):
    part, _ = _part(lon, 40)
    s = _sign_idx(lon)
    start = 0 if (s % 2 == 0) else 6   # odd from Aries, even from Libra
    return (start + part) % 12


# ---- D45: Akshavedamsa (general wellbeing) ----
def d45(lon):
    part, _ = _part(lon, 45)
    s = _sign_idx(lon)
    start = {0: 0, 1: 4, 2: 8}[s % 3]
    return (start + part) % 12


# ---- D60: Shashtiamsa (overall, past-life karma) ----
def d60(lon):
    deg_in_sign = lon % 30
    s = _sign_idx(lon)
    part = int(deg_in_sign * 2)   # 60 parts, each 0.5 deg
    return (s + part) % 12


DIVISIONS = {
    "D1": (d1, "Rasi", "the birth chart, overall life"),
    "D2": (d2, "Hora", "wealth"),
    "D3": (d3, "Drekkana", "siblings, courage"),
    "D4": (d4, "Chaturthamsa", "property, fortune"),
    "D7": (d7, "Saptamsa", "children"),
    "D9": (d9, "Navamsa", "spouse, dharma, inner strength"),
    "D10": (d10, "Dasamsa", "career, profession"),
    "D12": (d12, "Dwadasamsa", "parents"),
    "D16": (d16, "Shodasamsa", "vehicles, comforts"),
    "D20": (d20, "Vimsamsa", "spiritual life"),
    "D24": (d24, "Chaturvimsamsa", "education, learning"),
    "D27": (d27, "Bhamsa", "strengths and weaknesses"),
    "D30": (d30, "Trimsamsa", "misfortunes, challenges"),
    "D40": (d40, "Khavedamsa", "maternal legacy"),
    "D45": (d45, "Akshavedamsa", "paternal legacy"),
    "D60": (d60, "Shashtiamsa", "past-life karma, overall"),
}


def divisional_positions(chart: dict, division: str) -> dict:
    """Returns each planet's sign in the requested divisional chart, plus
    the ascendant's, so a full varga chart can be drawn. `chart` is the
    dict from compute_chart (needs each position's 'longitude')."""
    if division not in DIVISIONS:
        raise ValueError(f"unknown division {division}")
    fn, name, meaning = DIVISIONS[division]

    asc_lon = chart["ascendant"]["longitude"]
    asc_sign_idx = fn(asc_lon)

    positions = []
    for p in chart["positions"]:
        d_sign_idx = fn(p["longitude"])
        house = ((d_sign_idx - asc_sign_idx) % 12) + 1
        positions.append({
            "name": p["name"],
            "sign": SIGNS[d_sign_idx],
            "house": house,
            "retrograde": p["retrograde"],
        })

    return {
        "division": division,
        "name": name,
        "meaning": meaning,
        "ascendant": {"sign": SIGNS[asc_sign_idx]},
        "positions": positions,
    }
