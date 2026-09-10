"""
matching.py — Ashtakoot Guna Milan, the classical 36-point system.

Eight kootas, weighted: Varna 1, Vashya 2, Tara 3, Yoni 4, Graha Maitri 5,
Gana 6, Bhakoot 7, Nadi 8. Total 36.

Everything here is computed from the two Moon positions. No randomness,
no guessing — the same two charts always score the same.
"""

from chart_engine import compute_chart, NAKSHATRAS, SIGNS

# ---------------------------------------------------------------- tables

VARNA = {  # by moon sign
    "Karka": "Brahmin", "Vrischika": "Brahmin", "Meena": "Brahmin",
    "Mesha": "Kshatriya", "Simha": "Kshatriya", "Dhanu": "Kshatriya",
    "Vrishabha": "Vaishya", "Kanya": "Vaishya", "Makara": "Vaishya",
    "Mithuna": "Shudra", "Tula": "Shudra", "Kumbha": "Shudra",
}
VARNA_RANK = {"Shudra": 1, "Vaishya": 2, "Kshatriya": 3, "Brahmin": 4}

VASHYA = {
    "Mesha": "Chatushpada", "Vrishabha": "Chatushpada", "Mithuna": "Manava",
    "Karka": "Jalachara", "Simha": "Vanachara", "Kanya": "Manava",
    "Tula": "Manava", "Vrischika": "Keeta", "Dhanu": "Manava",
    "Makara": "Jalachara", "Kumbha": "Manava", "Meena": "Jalachara",
}

YONI = [
    ("Horse", "M"), ("Elephant", "M"), ("Sheep", "F"), ("Serpent", "M"),
    ("Serpent", "F"), ("Dog", "F"), ("Cat", "F"), ("Goat", "M"), ("Cat", "M"),
    ("Rat", "M"), ("Rat", "F"), ("Cow", "M"), ("Buffalo", "F"), ("Tiger", "F"),
    ("Buffalo", "M"), ("Tiger", "M"), ("Deer", "F"), ("Deer", "M"), ("Dog", "M"),
    ("Monkey", "M"), ("Mongoose", "F"), ("Monkey", "F"), ("Lion", "F"),
    ("Horse", "F"), ("Lion", "M"), ("Cow", "F"), ("Elephant", "F"),
]

# Classical enemy pairs. Everything else is graded by distance from these.
YONI_ENEMY = {
    frozenset(["Cow", "Tiger"]), frozenset(["Elephant", "Lion"]),
    frozenset(["Horse", "Buffalo"]), frozenset(["Dog", "Deer"]),
    frozenset(["Serpent", "Mongoose"]), frozenset(["Monkey", "Sheep"]),
    frozenset(["Cat", "Rat"]), frozenset(["Lion", "Elephant"]),
}
YONI_FRIENDLY = {
    frozenset(["Horse", "Sheep"]), frozenset(["Elephant", "Cow"]),
    frozenset(["Serpent", "Rat"]), frozenset(["Dog", "Monkey"]),
    frozenset(["Cat", "Goat"]), frozenset(["Deer", "Tiger"]),
    frozenset(["Buffalo", "Cow"]), frozenset(["Lion", "Tiger"]),
}

GANA = {}
for _i, _n in enumerate(NAKSHATRAS):
    pass
_DEVA = {"Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta", "Swati",
         "Anuradha", "Shravana", "Revati"}
_MANUSHYA = {"Bharani", "Rohini", "Ardra", "Purva Phalguni", "Uttara Phalguni",
             "Purva Ashadha", "Uttara Ashadha", "Purva Bhadrapada",
             "Uttara Bhadrapada"}
for _n in NAKSHATRAS:
    GANA[_n] = "Deva" if _n in _DEVA else ("Manushya" if _n in _MANUSHYA else "Rakshasa")

_AADI = {"Ashwini", "Ardra", "Punarvasu", "Uttara Phalguni", "Hasta",
         "Jyeshtha", "Mula", "Shatabhisha", "Purva Bhadrapada"}
_MADHYA = {"Bharani", "Mrigashira", "Pushya", "Purva Phalguni", "Chitra",
           "Anuradha", "Purva Ashadha", "Dhanishta", "Uttara Bhadrapada"}
NADI = {n: ("Aadi" if n in _AADI else ("Madhya" if n in _MADHYA else "Antya"))
        for n in NAKSHATRAS}

SIGN_LORD = {
    "Mesha": "Mars", "Vrishabha": "Venus", "Mithuna": "Mercury", "Karka": "Moon",
    "Simha": "Sun", "Kanya": "Mercury", "Tula": "Venus", "Vrischika": "Mars",
    "Dhanu": "Jupiter", "Makara": "Saturn", "Kumbha": "Saturn", "Meena": "Jupiter",
}
FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"}, "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"}, "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"}, "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
ENEMIES = {
    "Sun": {"Venus", "Saturn"}, "Moon": set(), "Mars": {"Mercury"},
    "Mercury": {"Moon"}, "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"}, "Saturn": {"Sun", "Moon", "Mars"},
}


def _relation(a, b):
    if a == b:
        return "same"
    if b in FRIENDS.get(a, set()):
        return "friend"
    if b in ENEMIES.get(a, set()):
        return "enemy"
    return "neutral"


# ---------------------------------------------------------------- kootas

def _varna(b_sign, g_sign):
    b, g = VARNA[b_sign], VARNA[g_sign]
    got = 1 if VARNA_RANK[b] >= VARNA_RANK[g] else 0
    return got, 1, f"{b} and {g}", (
        "The groom's varna is equal or higher, which the classical rule asks for."
        if got else
        "The bride's varna ranks higher here. Traditionally scored zero, though "
        "it is the lightest of the eight kootas and rarely decides anything.")


def _vashya(b_sign, g_sign):
    b, g = VASHYA[b_sign], VASHYA[g_sign]
    if b == g:
        got = 2
    elif {b, g} == {"Manava", "Chatushpada"} or {b, g} == {"Jalachara", "Chatushpada"}:
        got = 1
    elif "Keeta" in (b, g) or "Vanachara" in (b, g):
        got = 0.5
    else:
        got = 1
    return got, 2, f"{b} and {g}", (
        "Same vashya group, so neither dominates the other."
        if b == g else
        "Different vashya groups. This koota measures mutual influence, "
        "not conflict.")


def _tara(b_idx, g_idx):
    def count(frm, to):
        return ((to - frm) % 27) + 1
    r1 = count(g_idx, b_idx) % 9
    r2 = count(b_idx, g_idx) % 9
    bad = {3, 5, 7}
    got = (0 if r1 in bad else 1.5) + (0 if r2 in bad else 1.5)
    return got, 3, f"counts {r1} and {r2}", (
        "Both directions fall on auspicious taras."
        if got == 3 else
        "One or both counts land on a difficult tara. This koota is about "
        "each person's wellbeing in the other's presence.")


def _yoni(b_idx, g_idx):
    ba, bs = YONI[b_idx]
    ga, gs = YONI[g_idx]
    pair = frozenset([ba, ga])
    if ba == ga:
        got = 4 if bs != gs else 3
    elif pair in YONI_ENEMY:
        got = 0
    elif pair in YONI_FRIENDLY:
        got = 3
    else:
        got = 2
    return got, 4, f"{ba} and {ga}", (
        "Same yoni, which is the strongest result for this koota."
        if ba == ga else
        "Classically opposed yonis. This koota speaks to physical and "
        "temperamental compatibility."
        if pair in YONI_ENEMY else
        "Compatible yonis.")


def _graha_maitri(b_sign, g_sign):
    bl, gl = SIGN_LORD[b_sign], SIGN_LORD[g_sign]
    r1, r2 = _relation(bl, gl), _relation(gl, bl)
    score = {("same", "same"): 5,
             ("friend", "friend"): 5, ("friend", "neutral"): 4,
             ("neutral", "friend"): 4, ("neutral", "neutral"): 3,
             ("friend", "enemy"): 1, ("enemy", "friend"): 1,
             ("neutral", "enemy"): 0.5, ("enemy", "neutral"): 0.5,
             ("enemy", "enemy"): 0}
    got = score.get((r1, r2), 3)
    return got, 5, f"{bl} and {gl}", (
        "The moon-sign lords are friendly, which supports mental affinity."
        if got >= 4 else
        "The moon-sign lords are not natural friends. This koota governs "
        "mental and emotional understanding, so it carries real weight.")


def _gana(b_nak, g_nak):
    b, g = GANA[b_nak], GANA[g_nak]
    if b == g:
        got = 6
    elif {b, g} == {"Deva", "Manushya"}:
        got = 5
    elif {b, g} == {"Manushya", "Rakshasa"}:
        got = 1 if b == "Rakshasa" else 0
    else:  # Deva - Rakshasa
        got = 0
    return got, 6, f"{b} and {g}", (
        "Same gana, so temperaments run in the same direction."
        if b == g else
        "Different ganas. This koota is about temperament, and a mismatch "
        "here shows up as friction in daily life rather than crisis.")


def _bhakoot(b_sign, g_sign):
    bi, gi = SIGNS.index(b_sign), SIGNS.index(g_sign)
    d1 = ((gi - bi) % 12) + 1
    d2 = ((bi - gi) % 12) + 1
    pair = {d1, d2}
    bad = pair in [{6, 9}, {2, 12}, {5, 9}]
    got = 0 if bad else 7
    return got, 7, f"{d1}/{d2} axis", (
        "No bhakoot dosha on this axis."
        if got else
        "A bhakoot dosha. Classically this is cancelled when graha maitri "
        "scores well or both moon signs share a lord — check that before "
        "treating it as final.")


def _nadi(b_nak, g_nak):
    b, g = NADI[b_nak], NADI[g_nak]
    got = 0 if b == g else 8
    return got, 8, f"{b} and {g}", (
        "Different nadis, which is what this koota asks for."
        if got else
        "Same nadi. This is the heaviest single koota. Classically it is "
        "cancelled if the two share a moon sign with different nakshatras, "
        "or the same nakshatra with different padas.")


# ---------------------------------------------------------------- mangal

def mangal_dosha(chart):
    """Mars in 1, 2, 4, 7, 8 or 12 from the lagna."""
    mars = next(p for p in chart["positions"] if p["name"] == "Mars")
    houses = {1, 2, 4, 7, 8, 12}
    present = mars["house"] in houses
    return {
        "present": present,
        "house": mars["house"],
        "note": (f"Mars sits in house {mars['house']}, which carries Mangal dosha "
                 "in the standard reckoning. It is commonly cancelled when both "
                 "charts carry it, and by several other classical exceptions."
                 if present else
                 f"Mars is in house {mars['house']}. No Mangal dosha.")
    }


# ---------------------------------------------------------------- entry

def match(boy_chart, girl_chart):
    bm = next(p for p in boy_chart["positions"] if p["name"] == "Moon")
    gm = next(p for p in girl_chart["positions"] if p["name"] == "Moon")
    b_nak, g_nak = bm["nakshatra"], gm["nakshatra"]
    b_idx, g_idx = NAKSHATRAS.index(b_nak), NAKSHATRAS.index(g_nak)
    b_sign, g_sign = bm["sign"], gm["sign"]

    kootas = []
    for name, (got, mx, detail, note) in [
        ("Varna", _varna(b_sign, g_sign)),
        ("Vashya", _vashya(b_sign, g_sign)),
        ("Tara", _tara(b_idx, g_idx)),
        ("Yoni", _yoni(b_idx, g_idx)),
        ("Graha Maitri", _graha_maitri(b_sign, g_sign)),
        ("Gana", _gana(b_nak, g_nak)),
        ("Bhakoot", _bhakoot(b_sign, g_sign)),
        ("Nadi", _nadi(b_nak, g_nak)),
    ]:
        kootas.append({"name": name, "score": round(got, 1), "max": mx,
                       "detail": detail, "note": note})

    total = round(sum(k["score"] for k in kootas), 1)

    if total >= 28:
        verdict = "Excellent"
        summary = "A strong match by the classical count."
    elif total >= 21:
        verdict = "Good"
        summary = "A workable match. Most families proceed at this score."
    elif total >= 18:
        verdict = "Acceptable"
        summary = ("Above the usual threshold of 18, but look at which kootas "
                   "scored low before deciding.")
    else:
        verdict = "Below threshold"
        summary = ("Below the customary threshold of 18. Worth reviewing with "
                   "an astrologer rather than treating as a verdict.")

    return {
        "boy": {"moon_sign": b_sign, "nakshatra": b_nak,
                "gana": GANA[b_nak], "nadi": NADI[b_nak],
                "yoni": YONI[b_idx][0], "varna": VARNA[b_sign]},
        "girl": {"moon_sign": g_sign, "nakshatra": g_nak,
                 "gana": GANA[g_nak], "nadi": NADI[g_nak],
                 "yoni": YONI[g_idx][0], "varna": VARNA[g_sign]},
        "kootas": kootas,
        "total": total,
        "out_of": 36,
        "verdict": verdict,
        "summary": summary,
        "mangal": {"boy": mangal_dosha(boy_chart), "girl": mangal_dosha(girl_chart)},
        "caveat": ("Guna milan is one layer. It reads the two Moons and nothing "
                   "else — not the dashas either person is running, not the "
                   "seventh house, not Venus. A number out of 36 is a starting "
                   "point for a conversation, not an answer."),
    }
