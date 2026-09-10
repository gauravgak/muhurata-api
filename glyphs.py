"""
glyphs.py — the astrological symbols (planet and sign glyphs) as inline
SVG paths, so the charts and tables can show real symbols like a proper
astrology site instead of plain text names.

These are drawn as simple, legible strokes that hold up small. Returned
as <symbol>-ready path data plus a lookup, so the frontend can render
any planet or sign glyph at any size in the brand colours.

Unicode astrological characters exist (☉☽♈ etc.) but render
inconsistently across devices and fonts - drawing them as SVG guarantees
they look the same everywhere, which is the whole point of using them.
"""

# Planet glyphs — traditional Western astrological symbols, universally
# recognised alongside Vedic charts. viewBox is 0 0 24 24 for all.
PLANET_GLYPHS = {
    "Sun":     '<circle cx="12" cy="12" r="8" fill="none"/><circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none"/>',
    "Moon":    '<path d="M15.5 4a9 9 0 1 0 0 16 7 7 0 0 1 0-16z"/>',
    "Mars":    '<circle cx="10" cy="14" r="6" fill="none"/><path d="M14.2 9.8 20 4m-4 0h4v4"/>',
    "Mercury": '<circle cx="12" cy="11" r="5" fill="none"/><path d="M8.5 4.5a3.5 3.5 0 0 0 7 0M12 16v5m-2.5-2.5h5"/>',
    "Jupiter": '<path d="M6 8h9m-4-4v13c0 2 1.5 3 3.5 3M18 20c-3 0-4-2-4-4"/>',
    "Venus":   '<circle cx="12" cy="8" r="5.5" fill="none"/><path d="M12 13.5V21m-3.5-3.5h7"/>',
    "Saturn":  '<path d="M10 5h5M12.5 5v9c0 2 1.2 3 3 3s2.5-1.2 2.5-3-1-3-2.5-3"/>',
    "Rahu":    '<path d="M5 19c0-7 3-12 7-12s7 5 7 12M9 19a3 3 0 0 0 6 0"/>',
    "Ketu":    '<path d="M5 5c0 7 3 12 7 12s7-5 7-12M9 5a3 3 0 0 1 6 0"/>',
    "Uranus":  '<circle cx="12" cy="17" r="2.5" fill="none"/><path d="M12 4v10M7 8v4m10-4v4M7 8h10"/>',
    "Neptune": '<path d="M8 5v6a4 4 0 0 0 8 0V5M12 5v16m-3-2h6"/>',
    "Pluto":   '<circle cx="12" cy="8" r="3.5" fill="none"/><path d="M8.5 8H6M12 11.5V21m-3 -3h6M8 5.5a4 4 0 0 1 8 0"/>',
    "Ascendant": '<circle cx="12" cy="12" r="8" fill="none"/><path d="M12 4v16"/>',
}

# Sign glyphs — the twelve zodiac symbols. Keyed by Sanskrit sign name.
SIGN_GLYPHS = {
    "Mesha":     '<path d="M12 20V9M12 9c0-3-2-5-4.5-5S4 6 5 8m7 1c0-3 2-5 4.5-5S19 6 18 8"/>',
    "Vrishabha": '<circle cx="12" cy="15" r="5.5" fill="none"/><path d="M5 5a7 6 0 0 0 14 0"/>',
    "Mithuna":   '<path d="M6 5h12M6 19h12M9 5v14m6-14v14"/>',
    "Karka":     '<path d="M4 9c0-1.5 1.3-2.5 3-2.5S10 7.5 10 9M4 9a2.2 2.2 0 1 0 4 0M20 15c0 1.5-1.3 2.5-3 2.5S14 16.5 14 15m6 0a2.2 2.2 0 1 0-4 0M6 9.5c3-2.5 9-2.5 12 0.5"/>',
    "Simha":     '<circle cx="7.5" cy="15" r="3" fill="none"/><path d="M10.2 13.5C9 10 10 6.5 13 6c2.5-.4 4.5 1.8 4 4.2-.4 2-2 2.8-3 2M14.8 12c1.5 1 2.5 2.5 2.5 4"/>',
    "Kanya":     '<path d="M4 6v10M6.5 6v9m0-9c0-1.2 1.5-1.5 2.2 0v8m0-8c0-1.2 1.5-1.5 2.2 0v8m0-6c1.8-1 3.5 0 3.5 2.5 0 3-2 4.5-4 5.5m4-6c1.8 0 2.5 2 2 4"/>',
    "Tula":      '<path d="M4 18h16M4 14h16M8 14a4 4 0 0 1 8 0"/>',
    "Vrischika": '<path d="M4 7v9M6 7v9M6 8c1-1.2 2-1.2 3 0v8M9 8c1-1.2 2-1.2 3 0v9c0 1.5 1 2.5 2.5 2.5H18l-1.5-2M18 19.5l-1.5 2"/>',
    "Dhanu":     '<path d="M6 18 18 6m0 0h-5m5 0v5M9 9l6 6"/>',
    "Makara":    '<path d="M4 7v8M6 7v8M6 9c2-2.5 4.5-2.5 5.5 0 .8 2-.3 4-2 4.5M11 11c1.5-2 4-2 5 0 1.2 2.3-.3 5-2.8 5.2-1.5.1-2.5-1-2.2-2.2"/>',
    "Kumbha":    '<path d="M4 9c1.5-1.5 3-1.5 4 0s2.5 1.5 4 0 3-1.5 4 0M4 14c1.5-1.5 3-1.5 4 0s2.5 1.5 4 0 3-1.5 4 0"/>',
    "Meena":     '<path d="M6 5C3.5 8 3.5 16 6 19M18 5c2.5 3 2.5 11 0 14M4.5 12h15"/>',
}

# For the frontend: a compact map of short-name -> full name, since charts
# label planets as Su/Mo/Ma etc. and need to resolve to a glyph.
ABBR_TO_NAME = {
    "Su": "Sun", "Mo": "Moon", "Ma": "Mars", "Me": "Mercury",
    "Ju": "Jupiter", "Ve": "Venus", "Sa": "Saturn", "Ra": "Rahu",
    "Ke": "Ketu", "Ur": "Uranus", "Ne": "Neptune", "Pl": "Pluto",
    "Asc": "Ascendant",
}


def all_glyphs_svg_defs() -> str:
    """Returns a single <svg> containing every glyph as a <symbol>, to
    drop once into the page. The frontend then references any glyph with
    <use href="#g-Sun"/> etc. - defined once, used many times, tiny."""
    symbols = []
    for name, path in PLANET_GLYPHS.items():
        symbols.append(
            f'<symbol id="g-{name}" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="currentColor" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</g></symbol>'
        )
    for name, path in SIGN_GLYPHS.items():
        symbols.append(
            f'<symbol id="s-{name}" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="currentColor" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</g></symbol>'
        )
    return ('<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
            'aria-hidden="true">' + "".join(symbols) + "</svg>")
