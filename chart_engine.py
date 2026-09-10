"""
chart_engine.py — the calculation layer for Anugraha.

Deterministic: same (birth_utc, lat, lon) always yields the same chart.
That is what makes it cacheable and what makes "accurate" a defensible claim.

Requires: pip install pyswisseph
Uses the built-in Moshier ephemeris, so there are no data files to ship.
Swap SEFLG_MOSEPH -> SEFLG_SWIEPH and ship the .se1 files if you want
sub-arcsecond precision later.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import threading
import swisseph as swe

# ---------------------------------------------------------------- constants

SIGNS = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
         "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# Vimshottari: lord of each nakshatra in order, and years allotted.
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
               "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
TOTAL_YEARS = 120

PLANETS = [
    ("Sun", swe.SUN), ("Moon", swe.MOON), ("Mars", swe.MARS),
    ("Mercury", swe.MERCURY), ("Jupiter", swe.JUPITER), ("Venus", swe.VENUS),
    ("Saturn", swe.SATURN), ("Rahu", swe.TRUE_NODE),
]

# Classical ishta-devata associations, keyed by planet.
DEVATA = {
    "Sun": "Surya / Shiva", "Moon": "Parvati / Gauri", "Mars": "Kartikeya / Hanuman",
    "Mercury": "Vishnu", "Jupiter": "Dakshinamurthy", "Venus": "Lakshmi",
    "Saturn": "Shani / Hanuman", "Rahu": "Durga", "Ketu": "Ganesha",
}

FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

# Swiss Ephemeris keeps the ayanamsa mode in state that does NOT reliably
# carry across threads. FastAPI runs sync endpoints in a worker threadpool,
# so setting this once at import silently fell back to Fagan-Bradley inside
# request threads — a 0.88 degree error, enough to move a planet into the
# wrong nakshatra. Set it on every call instead, under a lock, because the
# underlying C library is not thread-safe.
_swe_lock = threading.Lock()


def _use_lahiri():
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


# ---------------------------------------------------------------- helpers

def _norm(deg: float) -> float:
    return deg % 360.0


def _sign(lon: float) -> int:
    return int(lon // 30)


def _dms(lon: float) -> str:
    d = lon % 30
    deg = int(d)
    m = int((d - deg) * 60)
    s = int((((d - deg) * 60) - m) * 60)
    return f"{deg:02d}\u00b0{m:02d}'{s:02d}\""


def _navamsa_sign(lon: float) -> int:
    """Each sign splits into 9 padas of 3\u00b020'. Movable signs start from
    themselves, fixed from the 9th, dual from the 5th."""
    s = _sign(lon)
    pada = int((lon % 30) // (30 / 9))
    start = {0: s, 1: (s + 8) % 12, 2: (s + 4) % 12}[s % 3]
    return (start + pada) % 12


def _nakshatra(lon: float):
    span = 360 / 27
    idx = int(lon // span)
    frac = (lon % span) / span
    pada = int(frac * 4) + 1
    return idx, NAKSHATRAS[idx], pada, frac


# ---------------------------------------------------------------- model

@dataclass
class Position:
    name: str
    longitude: float
    sign: str
    degree_in_sign: str
    nakshatra: str
    pada: int
    navamsa_sign: str
    retrograde: bool
    house: int


# ---------------------------------------------------------------- core

def to_julian_day(local_dt: datetime, utc_offset_hours: float) -> float:
    """local_dt is naive wall-clock time at the birth place."""
    utc = local_dt - timedelta(hours=utc_offset_hours)
    return swe.julday(utc.year, utc.month, utc.day,
                      utc.hour + utc.minute / 60 + utc.second / 3600)


def compute_chart(local_dt: datetime, lat: float, lon: float,
                  utc_offset_hours: float = 5.5) -> dict:
    with _swe_lock:
        return _compute_chart_locked(local_dt, lat, lon, utc_offset_hours)


def _compute_chart_locked(local_dt: datetime, lat: float, lon: float,
                          utc_offset_hours: float) -> dict:
    _use_lahiri()
    jd = to_julian_day(local_dt, utc_offset_hours)

    # Ascendant and house cusps. 'W' = whole sign, the North Indian standard.
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b'W', FLAGS)
    asc = _norm(ascmc[0])
    asc_sign = _sign(asc)

    positions = []
    for name, pid in PLANETS:
        vals, _ = swe.calc_ut(jd, pid, FLAGS)
        plon, speed = _norm(vals[0]), vals[3]
        _, nak, pada, _ = _nakshatra(plon)
        positions.append(Position(
            name=name,
            longitude=round(plon, 4),
            sign=SIGNS[_sign(plon)],
            degree_in_sign=_dms(plon),
            nakshatra=nak,
            pada=pada,
            navamsa_sign=SIGNS[_navamsa_sign(plon)],
            retrograde=speed < 0,
            house=((_sign(plon) - asc_sign) % 12) + 1,
        ))

    # Ketu is always exactly opposite Rahu.
    rahu = next(p for p in positions if p.name == "Rahu")
    ketu_lon = _norm(rahu.longitude + 180)
    _, knak, kpada, _ = _nakshatra(ketu_lon)
    positions.append(Position(
        name="Ketu", longitude=round(ketu_lon, 4), sign=SIGNS[_sign(ketu_lon)],
        degree_in_sign=_dms(ketu_lon), nakshatra=knak, pada=kpada,
        navamsa_sign=SIGNS[_navamsa_sign(ketu_lon)], retrograde=True,
        house=((_sign(ketu_lon) - asc_sign) % 12) + 1,
    ))

    moon = next(p for p in positions if p.name == "Moon")

    return {
        "julian_day": jd,
        "ayanamsa": round(swe.get_ayanamsa_ut(jd), 6),
        "ascendant": {
            "longitude": round(asc, 4),
            "sign": SIGNS[asc_sign],
            "degree_in_sign": _dms(asc),
            "nakshatra": _nakshatra(asc)[1],
        },
        "positions": [asdict(p) for p in positions],
        "moon_sign": moon.sign,
        "birth_nakshatra": moon.nakshatra,
        "vimshottari": vimshottari(moon.longitude, local_dt, utc_offset_hours),
        "atmakaraka": atmakaraka(positions),
    }


def vimshottari(moon_lon: float, birth_local: datetime, utc_offset: float, depth: int = 2):
    """Mahadasha and antardasha sequence from the Moon's nakshatra."""
    span = 360 / 27
    idx = int(moon_lon // span)
    traversed = (moon_lon % span) / span

    lord = DASHA_ORDER[idx % 9]
    start_i = DASHA_ORDER.index(lord)

    # The first mahadasha is already partly spent at birth.
    balance = DASHA_YEARS[lord] * (1 - traversed)
    cursor = birth_local

    out = []
    for k in range(9):
        md = DASHA_ORDER[(start_i + k) % 9]
        years = balance if k == 0 else DASHA_YEARS[md]
        md_start, md_end = cursor, cursor + timedelta(days=years * 365.2425)

        entry = {"lord": md, "start": md_start.date().isoformat(),
                 "end": md_end.date().isoformat(), "years": round(years, 3)}

        if depth > 1:
            subs, c = [], md_start
            j0 = DASHA_ORDER.index(md)
            for j in range(9):
                ad = DASHA_ORDER[(j0 + j) % 9]
                ad_years = years * DASHA_YEARS[ad] / TOTAL_YEARS
                ad_end = c + timedelta(days=ad_years * 365.2425)
                subs.append({"lord": ad, "start": c.date().isoformat(),
                             "end": ad_end.date().isoformat()})
                c = ad_end
            entry["antardashas"] = subs

        out.append(entry)
        cursor = md_end
    return out


def running_dasha(chart: dict, when: datetime = None):
    when = when or datetime.now()
    d = when.date().isoformat()
    for md in chart["vimshottari"]:
        if md["start"] <= d < md["end"]:
            ad = next((a for a in md.get("antardashas", [])
                       if a["start"] <= d < a["end"]), None)
            return {"mahadasha": md["lord"], "antardasha": ad["lord"] if ad else None,
                    "mahadasha_ends": md["end"],
                    "antardasha_ends": ad["end"] if ad else None}
    return None


def atmakaraka(positions):
    """Highest degree within its sign among the seven charas.
    This is what the ishta devata is derived from."""
    charas = [p for p in positions if p.name != "Ketu"]
    ak = max(charas, key=lambda p: (p.longitude % 30))
    return {"planet": ak.name, "degree": ak.degree_in_sign,
            "navamsa_sign": ak.navamsa_sign}


def ishta_devata(chart: dict):
    """Classical route: the 12th house from the Atmakaraka in the navamsa.
    Whichever planet sits there (or its lord) points to the devata."""
    ak_nav = SIGNS.index(chart["atmakaraka"]["navamsa_sign"])
    twelfth = (ak_nav + 11) % 12
    occupants = [p["name"] for p in chart["positions"]
                 if p["navamsa_sign"] == SIGNS[twelfth]]
    LORDS = {0: "Mars", 1: "Venus", 2: "Mercury", 3: "Moon", 4: "Sun", 5: "Mercury",
             6: "Venus", 7: "Mars", 8: "Jupiter", 9: "Saturn", 10: "Saturn", 11: "Jupiter"}
    ruler = occupants[0] if occupants else LORDS[twelfth]
    return {"karakamsa_12th": SIGNS[twelfth], "occupants": occupants,
            "indicator": ruler, "devata": DEVATA.get(ruler, "\u2014")}


def cache_key(birth_utc_iso: str, lat: float, lon: float) -> str:
    """Charts are pure functions of these three. Round coords to ~1km so
    'Kandivali' and 'Kandivali West' hit the same cached chart."""
    return f"chart:{birth_utc_iso}:{lat:.2f}:{lon:.2f}"


if __name__ == "__main__":
    import json
    # Sample: 14 Aug 1994, 07:42 IST, Mumbai
    dt = datetime(1994, 8, 14, 7, 42)
    c = compute_chart(dt, lat=19.0760, lon=72.8777, utc_offset_hours=5.5)

    print(f"Ayanamsa (Lahiri)  {c['ayanamsa']:.4f}\u00b0")
    print(f"Lagna              {c['ascendant']['sign']} {c['ascendant']['degree_in_sign']}")
    print(f"Moon sign          {c['moon_sign']}")
    print(f"Birth nakshatra    {c['birth_nakshatra']}\n")

    print(f"{'Planet':<9}{'Sign':<12}{'Degree':<12}{'Nakshatra':<18}{'Nav':<12}{'Ho':>3}")
    for p in c["positions"]:
        r = " R" if p["retrograde"] else ""
        print(f"{p['name']:<9}{p['sign']:<12}{p['degree_in_sign']:<12}"
              f"{p['nakshatra'] + ' ' + str(p['pada']):<18}{p['navamsa_sign']:<12}{p['house']:>3}{r}")

    rd = running_dasha(c)
    print(f"\nRunning            {rd['mahadasha']} / {rd['antardasha']}"
          f"  (antardasha ends {rd['antardasha_ends']})")

    ak = c["atmakaraka"]
    idev = ishta_devata(c)
    print(f"Atmakaraka         {ak['planet']} at {ak['degree']}, navamsa {ak['navamsa_sign']}")
    print(f"Ishta devata       {idev['devata']}  (via {idev['indicator']}, "
          f"12th from karakamsa = {idev['karakamsa_12th']})")
    print(f"\nCache key          {cache_key('1994-08-14T02:12:00Z', 19.0760, 72.8777)}")
