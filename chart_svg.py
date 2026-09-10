"""
chart_svg.py — draws the kundli people actually expect to see.

Two styles, because India does not agree on one:

  North Indian  — diamond. Houses are FIXED (house 1 always top centre),
                  signs rotate. Standard across the Hindi belt.
  South Indian  — 4x4 grid. Signs are FIXED (Mesha always same box),
                  houses rotate. Standard in TN, KL, AP, KA.

Output is inline SVG, so it scales, themes with the site, and costs
nothing to generate. No image library, no rasterising, no file storage.
"""

ABBR = {
    "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
    "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke",
}

SIGN_NUM = {
    "Mesha": 1, "Vrishabha": 2, "Mithuna": 3, "Karka": 4, "Simha": 5, "Kanya": 6,
    "Tula": 7, "Vrischika": 8, "Dhanu": 9, "Makara": 10, "Kumbha": 11, "Meena": 12,
}

INK = "#3D2514"
BRASS = "#A9801F"
KUM = "#8F221C"
LINE = "#B9963F"
BG = "#FFFCF3"

# Where the sign number and planet list sit in each of the 12 North Indian houses.
NORTH_POS = {
    1:  (150, 62),  2:  (74, 34),   3:  (34, 74),   4:  (66, 150),
    5:  (34, 226),  6:  (74, 266),  7:  (150, 238), 8:  (226, 266),
    9:  (266, 226), 10: (234, 150), 11: (266, 74),  12: (226, 34),
}

# South Indian: fixed 4x4 grid, sign -> (col, row). Mesha top-left-ish,
# running clockwise. Centre four cells are empty.
SOUTH_CELL = {
    1: (1, 0), 2: (2, 0), 3: (3, 0), 4: (3, 1),
    5: (3, 2), 6: (3, 3), 7: (2, 3), 8: (1, 3),
    9: (0, 3), 10: (0, 2), 11: (0, 1), 12: (0, 0),
}


def _group(chart):
    """house -> list of planet abbreviations, plus the sign in each house."""
    asc_sign = SIGN_NUM[chart["ascendant"]["sign"]]
    by_house = {h: [] for h in range(1, 13)}
    for p in chart["positions"]:
        by_house[p["house"]].append(
            ABBR[p["name"]] + ("\u1d3f" if p["retrograde"] else "")
        )
    # house n holds the sign (asc_sign + n - 1)
    sign_of = {h: ((asc_sign + h - 2) % 12) + 1 for h in range(1, 13)}
    return by_house, sign_of, asc_sign


def north_indian(chart, size=320):
    by_house, sign_of, _ = _group(chart)
    S = 300  # internal coordinate space

    parts = [
        f'<svg viewBox="0 0 {S} {S}" width="{size}" height="{size}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="North Indian birth chart">',
        f'<rect width="{S}" height="{S}" fill="{BG}"/>',
        f'<g fill="none" stroke="{LINE}" stroke-width="1.4">',
        f'<rect x="1" y="1" width="{S-2}" height="{S-2}"/>',
        f'<path d="M1,1 L{S-1},{S-1} M{S-1},1 L1,{S-1}"/>',
        f'<path d="M{S/2},1 L{S-1},{S/2} L{S/2},{S-1} L1,{S/2} Z"/>',
        '</g>',
    ]

    for h in range(1, 13):
        x, y = NORTH_POS[h]
        parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Karla,sans-serif" '
            f'font-size="11" fill="{BRASS}" font-weight="600">{sign_of[h]}</text>'
        )
        planets = by_house[h]
        if not planets:
            continue
        # wrap at two per line so nothing overflows a triangle
        lines = [planets[i:i + 2] for i in range(0, len(planets), 2)]
        for i, row in enumerate(lines):
            parts.append(
                f'<text x="{x}" y="{y + 15 + i * 13}" text-anchor="middle" '
                f'font-family="Karla,sans-serif" font-size="12.5" fill="{INK}" '
                f'font-weight="600">{" ".join(row)}</text>'
            )

    # mark the lagna
    ax, ay = NORTH_POS[1]
    parts.append(
        f'<text x="{ax}" y="{ay - 14}" text-anchor="middle" font-family="Karla,sans-serif" '
        f'font-size="10" fill="{KUM}" font-weight="700" letter-spacing="1">LAGNA</text>'
    )
    parts.append('</svg>')
    return "".join(parts)


def south_indian(chart, size=320):
    by_house, sign_of, asc_sign = _group(chart)
    house_of_sign = {s: h for h, s in sign_of.items()}
    S, cell = 300, 75

    parts = [
        f'<svg viewBox="0 0 {S} {S}" width="{size}" height="{size}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="South Indian birth chart">',
        f'<rect width="{S}" height="{S}" fill="{BG}"/>',
    ]

    for sign, (col, row) in SOUTH_CELL.items():
        x, y = col * cell, row * cell
        h = house_of_sign[sign]
        is_lagna = sign == asc_sign
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="none" '
            f'stroke="{LINE}" stroke-width="1.4"/>'
        )
        if is_lagna:
            parts.append(
                f'<path d="M{x+3},{y+3} L{x+cell-3},{y+3} L{x+3},{y+cell-3} Z" '
                f'fill="{KUM}" opacity="0.13"/>'
            )
        parts.append(
            f'<text x="{x+6}" y="{y+15}" font-family="Karla,sans-serif" font-size="10" '
            f'fill="{BRASS}" font-weight="600">{sign}</text>'
        )
        planets = by_house[h]
        lines = [planets[i:i + 2] for i in range(0, len(planets), 2)]
        for i, r in enumerate(lines):
            parts.append(
                f'<text x="{x+cell/2}" y="{y+38+i*14}" text-anchor="middle" '
                f'font-family="Karla,sans-serif" font-size="12.5" fill="{INK}" '
                f'font-weight="600">{" ".join(r)}</text>'
            )

    parts.append(
        f'<text x="{S/2}" y="{S/2-6}" text-anchor="middle" font-family="Karla,sans-serif" '
        f'font-size="12" fill="{BRASS}" letter-spacing="2">RASI</text>'
    )
    parts.append(
        f'<text x="{S/2}" y="{S/2+14}" text-anchor="middle" '
        f'font-family="Karla,sans-serif" font-size="10" fill="{BRASS}" '
        f'opacity="0.75">Lagna: {chart["ascendant"]["sign"]}</text>'
    )
    parts.append('</svg>')
    return "".join(parts)


def navamsa_north(chart, size=320):
    """D9. Same drawing, but houses are counted from the navamsa lagna."""
    nav_asc = SIGN_NUM[_navamsa_of(chart["ascendant"]["longitude"])]
    shifted = {
        "ascendant": {"sign": _navamsa_of(chart["ascendant"]["longitude"]),
                      "degree_in_sign": "", "longitude": 0, "nakshatra": ""},
        "positions": [
            {**p,
             "house": ((SIGN_NUM[p["navamsa_sign"]] - nav_asc) % 12) + 1}
            for p in chart["positions"]
        ],
    }
    return north_indian(shifted, size)


def _navamsa_of(lon):
    from chart_engine import SIGNS, _navamsa_sign
    return SIGNS[_navamsa_sign(lon)]
