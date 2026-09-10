"""
avakhada.py — the classical birth attributes shown on a Basic kundli tab:
varna, vashya, yoni, gana, nadi, tatva, sign lord, nakshatra pada, plus
the panchang (tithi, yoga, karana) for the birth moment.

All derived from the Moon's position and the Sun-Moon relationship, using
tables already proven in matching.py so nothing here is a second, possibly
inconsistent source of truth.
"""

import threading
import swisseph as swe

from chart_engine import SIGNS, NAKSHATRAS, _use_lahiri, to_julian_day
from matching import (
    VASHYA, YONI, GANA, NADI, SIGN_LORD,
)

_lock = threading.Lock()

# Varna by NAKSHATRA (the consumer-app convention AstroTalk/AstroSage use),
# so a user cross-checking sees the same value. Distinct from the sign-based
# Parashari varna in matching.py, which is used there for guna milan scoring
# where the sign-based version is the matching-specific standard. Two uses,
# two conventions, on purpose - documented so future-me doesn't "fix" one
# into the other.
NAK_VARNA = {
    "Krittika": "Brahmin", "Purva Phalguni": "Brahmin", "Purva Ashadha": "Brahmin",
    "Vishakha": "Brahmin", "Anuradha": "Brahmin", "Purva Bhadrapada": "Brahmin",
    "Pushya": "Kshatriya", "Uttara Phalguni": "Kshatriya", "Uttara Ashadha": "Kshatriya",
    "Chitra": "Kshatriya", "Ashwini": "Kshatriya", "Uttara Bhadrapada": "Kshatriya",
    "Punarvasu": "Vaishya", "Hasta": "Vaishya", "Shravana": "Vaishya",
    "Bharani": "Vaishya", "Mula": "Vaishya", "Revati": "Vaishya",
    "Rohini": "Shudra", "Ardra": "Shudra", "Magha": "Shudra", "Swati": "Shudra",
    "Jyeshtha": "Shudra", "Shatabhisha": "Shudra", "Dhanishta": "Shudra",
    "Mrigashira": "Shudra", "Ashlesha": "Shudra",
}
FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL

# Element (tatva) by sign - fire/earth/air/water in the classical order.
TATVA = {
    "Mesha": "Fire", "Simha": "Fire", "Dhanu": "Fire",
    "Vrishabha": "Earth", "Kanya": "Earth", "Makara": "Earth",
    "Mithuna": "Air", "Tula": "Air", "Kumbha": "Air",
    "Karka": "Water", "Vrischika": "Water", "Meena": "Water",
}

# The 30 tithis, named by their paksha half. Index 0-14 = Shukla (waxing),
# 15-29 = Krishna (waning). Purnima and Amavasya close each half.
TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Purnima",
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Amavasya",
]

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti",
]

# Karana: 7 movable karanas repeat, plus 4 fixed. There are 11 in all
# across the 60 half-tithis of a lunar month; this returns the name for
# a given half-tithi index the standard way.
KARANA_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila",
                  "Gara", "Vanija", "Vishti"]


def _sidereal(jd, planet):
    _use_lahiri()
    v, _ = swe.calc_ut(jd, planet, FLAGS)
    return v[0] % 360


def _tithi(sun_lon, moon_lon):
    diff = (moon_lon - sun_lon) % 360
    idx = int(diff // 12)                      # 0..29
    paksha = "Shukla" if idx < 15 else "Krishna"
    return idx, f"{paksha} {TITHI_NAMES[idx]}"


def _yoga(sun_lon, moon_lon):
    total = (sun_lon + moon_lon) % 360
    idx = int(total // (360 / 27))
    return YOGA_NAMES[idx]


def _karana(sun_lon, moon_lon):
    diff = (moon_lon - sun_lon) % 360
    half = int(diff // 6)                       # 0..59
    if half == 0:
        return "Kimstughna"
    if half >= 57:
        return ["Shakuni", "Chatushpada", "Naga"][half - 57]
    return KARANA_MOVABLE[(half - 1) % 7]


def avakhada(chart: dict, local_dt, lat, lon, utc_offset=5.5) -> dict:
    """chart is the dict from compute_chart. Returns the Basic-tab data."""
    moon = next(p for p in chart["positions"] if p["name"] == "Moon")
    moon_sign = moon["sign"]
    nak = moon["nakshatra"]
    nak_idx = NAKSHATRAS.index(nak)

    with _lock:
        jd = to_julian_day(local_dt, utc_offset)
        sun_lon = _sidereal(jd, swe.SUN)
        moon_lon = _sidereal(jd, swe.MOON)

    tithi_idx, tithi_name = _tithi(sun_lon, moon_lon)

    return {
        "avakhada": {
            "varna": NAK_VARNA[nak],
            "vashya": VASHYA[moon_sign],
            "yoni": YONI[nak_idx][0],
            "gana": GANA[nak],
            "nadi": NADI[nak],
            "tatva": TATVA[moon_sign],
            "sign": moon_sign,
            "sign_lord": SIGN_LORD[moon_sign],
            "nakshatra": nak,
            "nakshatra_lord": _nak_lord(nak_idx),
            "nakshatra_pada": moon["pada"],
            "charan": moon["pada"],
        },
        "panchang": {
            "tithi": tithi_name,
            "yoga": _yoga(sun_lon, moon_lon),
            "karana": _karana(sun_lon, moon_lon),
            "nakshatra": nak,
        },
    }


# Vimshottari lord sequence maps onto nakshatras in a repeating 9-cycle.
_NAK_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter",
              "Saturn", "Mercury"]


def _nak_lord(nak_idx: int) -> str:
    return _NAK_LORDS[nak_idx % 9]
