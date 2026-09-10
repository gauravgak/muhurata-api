"""
horoscope.py — horoscopes for all twelve signs, computed from real transits.

The honest version of this feature. Most horoscope APIs return text from a
pool that has nothing to do with the sky. Here, each prediction is keyed to
where the Moon, Sun, Jupiter and Saturn actually are on the requested date,
relative to each moon sign.

  daily / tomorrow  -> Moon's house from the sign (changes ~every 2.25 days)
  monthly           -> Sun's house from the sign
  yearly            -> Jupiter's house, with Saturn noted

Same date always gives the same text. Nothing is invented at runtime.
"""

from datetime import datetime, timedelta
import threading
import swisseph as swe

from chart_engine import SIGNS

_lock = threading.Lock()
FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL

# What the Moon transiting each house from your sign traditionally indicates.
MOON_HOUSE = {
    1:  ("Restless", "The Moon is on your sign. You will feel everything a "
         "little more sharply today. Good for anything that needs your presence, "
         "poor for decisions you cannot reverse."),
    2:  ("Steady", "Attention turns to money, food and family. A good day to "
         "settle a small account or eat with people you like."),
    3:  ("Forward", "Energy for effort and short journeys. Say the thing you "
         "have been putting off saying — it lands better today."),
    4:  ("Inward", "Home pulls harder than work. Rest is not laziness today. "
         "Comfort, mother, and the place you sleep."),
    5:  ("Bright", "Intelligence and play are available. Good for study, "
         "for children, and for anything creative you keep deferring."),
    6:  ("Effortful", "Obstacles surface — work, health, small debts. Nothing "
         "dramatic, but push through rather than start something new."),
    7:  ("Relational", "The day comes to you through other people. Partnerships, "
         "negotiations, and the person across the table."),
    8:  ("Unsettled", "A day of undercurrents. Avoid confrontation and large "
         "transactions. Useful for research and for finishing old things."),
    9:  ("Expansive", "Fortune, teachers, travel, belief. Ask for what you want "
         "today — the asking goes further than usual."),
    10: ("Visible", "You are seen at work. Do the thing that needs a witness. "
         "Authority responds to you now."),
    11: ("Gainful", "Networks and elder siblings. Income and the people who "
         "bring it. A good day to reconnect deliberately."),
    12: ("Quiet", "Expenditure, sleep, foreign matters, release. Conserve. "
         "This is the closing of a cycle, not the opening of one."),
}

SUN_HOUSE = {
    1:  "A month about you — health, appearance, how you are read by others. Start things.",
    2:  "Income and family matters take the month. Speech carries more weight than usual.",
    3:  "Effort pays. Short travel, siblings, and the courage to push a project forward.",
    4:  "The month turns domestic. Property, vehicles, mother, and the peace of your own house.",
    5:  "Study, children and creative work. A good month to learn something properly.",
    6:  "Competition and service. Health needs attention. You win by grinding, not by luck.",
    7:  "Partnership dominates — business or marriage. Others set the pace this month.",
    8:  "A month of change beneath the surface. Slow down on money. Good for research.",
    9:  "Fortune opens. Travel, teachers, and matters of belief. Long-range decisions favour you.",
    10: "Career is centre stage. Visibility is high, so is scrutiny. Deliver.",
    11: "Gains arrive through networks. Income improves. Old contacts become useful.",
    12: "A closing month. Spend less, rest more, finish what is trailing. Foreign matters open.",
}

JUP_HOUSE = {
    1:  "Jupiter on your sign — a year of expansion in how you are seen. Weight gain is the standing joke, but the real theme is growth you can feel.",
    2:  "Wealth and family expand. A good year for savings, and for speaking with authority.",
    3:  "Effort multiplies. Siblings and short journeys feature. Less comfortable than it sounds.",
    4:  "Home, property and mother. A year to build the base rather than climb.",
    5:  "Children, learning and creative output. One of the better placements for study.",
    6:  "A grinding year. Jupiter here is weak. Health and debts want attention.",
    7:  "Partnership year — marriage, business alliance, or a significant collaboration.",
    8:  "Slow, internal. Inheritance and hidden matters. Not the year for large risk.",
    9:  "Jupiter in its own territory. Fortune, travel, teachers. Among the best years available.",
    10: "Career expansion. Recognition arrives, and with it more responsibility.",
    11: "The gains house. Income, networks, fulfilment of things long wanted.",
    12: "Expenditure, foreign lands, spiritual turn. A year of release rather than acquisition.",
}


def _sidereal_lon(jd, planet):
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    v, _ = swe.calc_ut(jd, planet, FLAGS)
    return v[0] % 360


def _jd(d: datetime):
    return swe.julday(d.year, d.month, d.day, 12.0 - 5.5)  # noon IST


def _house_from(sign_index, planet_lon):
    return ((int(planet_lon // 30) - sign_index) % 12) + 1


def horoscope(period: str = "today", when: datetime = None):
    """period: today | tomorrow | monthly | yearly"""
    base = when or datetime.now()
    if period == "tomorrow":
        base = base + timedelta(days=1)

    with _lock:
        jd = _jd(base)
        moon = _sidereal_lon(jd, swe.MOON)
        sun = _sidereal_lon(jd, swe.SUN)
        jup = _sidereal_lon(jd, swe.JUPITER)
        sat = _sidereal_lon(jd, swe.SATURN)

    out = []
    for i, sign in enumerate(SIGNS):
        if period in ("today", "tomorrow"):
            h = _house_from(i, moon)
            mood, text = MOON_HOUSE[h]
            out.append({
                "sign": sign, "house": h, "mood": mood, "text": text,
                "driver": f"Moon in {SIGNS[int(moon // 30)]}, house {h} from {sign}",
            })
        elif period == "monthly":
            h = _house_from(i, sun)
            out.append({
                "sign": sign, "house": h, "mood": "", "text": SUN_HOUSE[h],
                "driver": f"Sun in {SIGNS[int(sun // 30)]}, house {h} from {sign}",
            })
        else:  # yearly
            h = _house_from(i, jup)
            sh = _house_from(i, sat)
            out.append({
                "sign": sign, "house": h, "mood": "",
                "text": JUP_HOUSE[h] + f" Saturn sits in your {sh}th, which is "
                        "where the year asks for patience.",
                "driver": f"Jupiter in {SIGNS[int(jup // 30)]}, Saturn in "
                          f"{SIGNS[int(sat // 30)]}",
            })

    label = {"today": "Today", "tomorrow": "Tomorrow",
             "monthly": "This month", "yearly": "This year"}[period]

    return {
        "period": period,
        "label": label,
        "date": base.date().isoformat(),
        "transits": {
            "moon": SIGNS[int(moon // 30)],
            "sun": SIGNS[int(sun // 30)],
            "jupiter": SIGNS[int(jup // 30)],
            "saturn": SIGNS[int(sat // 30)],
        },
        "signs": out,
        "note": ("These are read from where the planets actually are on this "
                 "date, relative to each moon sign. They are general by nature — "
                 "your own chart will always say more than your sign alone."),
    }
