"""
pdf_report.py — turns a reading into an actual document.

reportlab only (no HTML-to-PDF, no headless browser), output to a BytesIO
buffer. Two themes, one layout:

    build_pdf(chart, sections, name, theme="light")   # cream, prints well
    build_pdf(chart, sections, name, theme="dark")    # night ground

`sections` is a dict of prose keyed to whichever `section_order` is used
(LLM_SECTION_ORDER by default; LEGACY_SECTION_ORDER for the catch-up
batch, which stays rule-based). Planet and sign glyphs are drawn as
vector art from glyphs.py.
"""

from io import BytesIO

import glyphs as _glyphs
from svglib.svglib import svg2rlg
from reportlab.graphics.shapes import Drawing, Group
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as _canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from chart_svg import _group, NORTH_POS, SOUTH_CELL, SIGN_NUM

# Serif everywhere — reportlab's built-in Times family, so no font files
# to ship and nothing to break on deploy. HEAD is the display face
# (section titles, the wordmark); BODY is the reading text.
HEAD = "Times-Bold"
HEAD_IT = "Times-BoldItalic"
BODY = "Times-Roman"
BODY_IT = "Times-Italic"
LABEL = "Helvetica"            # the one sans use: tiny all-caps labels

# ---------------------------------------------------------------- palettes
PALETTES = {
    "light": dict(
        bg="#f4f1e9", card="#ffffff", ink="#211f1b", head="#1c130a",
        accent="#96671d", accent_soft="#b68235", rule="#ddd2bd", muted="#6d6252",
        chart_bg="#faf6ee", chart_line="#96671d", chart_text="#211f1b", chart_accent="#7d5411",
    ),
    "dark": dict(
        bg="#171410", card="#221a0d", ink="#e9ddc5", head="#f0cd85",
        accent="#d6a754", accent_soft="#e0b76a", rule="#493c27", muted="#9a8a68",
        chart_bg="#171410", chart_line="#d6a754", chart_text="#f6efe1", chart_accent="#d99b52",
    ),
}


def _styles(pal: dict) -> dict:
    ink = HexColor(pal["ink"])
    head = HexColor(pal["head"])
    accent = HexColor(pal["accent"])
    muted = HexColor(pal["muted"])
    return {
        "wordmark": ParagraphStyle("wordmark", fontName=HEAD, fontSize=27, leading=30,
                                   textColor=head, alignment=TA_CENTER, spaceAfter=2),
        "kicker": ParagraphStyle("kicker", fontName=LABEL, fontSize=8, leading=12,
                                 textColor=accent, alignment=TA_CENTER, spaceAfter=2,
                                 characterSpace=3),
        "for_line": ParagraphStyle("for_line", fontName=BODY_IT, fontSize=12, leading=16,
                                   textColor=muted, alignment=TA_CENTER, spaceBefore=8),
        "birth_line": ParagraphStyle("birth_line", fontName=BODY, fontSize=10, leading=14,
                                     textColor=muted, alignment=TA_CENTER, spaceAfter=4),
        "sec_title": ParagraphStyle("sec_title", fontName=HEAD, fontSize=15, leading=19,
                                    textColor=head, spaceBefore=15, spaceAfter=2),
        "sec_caption": ParagraphStyle("sec_caption", fontName=BODY_IT, fontSize=9.5, leading=13,
                                      textColor=accent, spaceAfter=5),
        "body": ParagraphStyle("body", fontName=BODY, fontSize=10.5, leading=15.5,
                               textColor=ink, alignment=TA_LEFT, spaceAfter=6),
        "lead": ParagraphStyle("lead", fontName=BODY, fontSize=11.5, leading=17,
                               textColor=ink, alignment=TA_LEFT, spaceAfter=6),
        "hl_label": ParagraphStyle("hl_label", fontName=LABEL, fontSize=7.5, leading=10,
                                   textColor=accent, alignment=TA_CENTER, characterSpace=1.5),
        "hl_value": ParagraphStyle("hl_value", fontName=HEAD, fontSize=13, leading=16,
                                   textColor=head, alignment=TA_CENTER),
        "th": ParagraphStyle("th", fontName=LABEL, fontSize=8, leading=11, textColor=accent,
                             characterSpace=1),
        "td": ParagraphStyle("td", fontName=BODY, fontSize=9.5, leading=12.5, textColor=ink),
        "cap": ParagraphStyle("cap", fontName=LABEL, fontSize=8, leading=11, textColor=accent,
                              alignment=TA_CENTER, characterSpace=1),
        "footer": ParagraphStyle("footer", fontName=BODY_IT, fontSize=8.5, leading=12,
                                 textColor=muted, alignment=TA_CENTER, spaceBefore=4),
    }


# ---------------------------------------------------------------- section maps
LLM_SECTION_ORDER = [
    ("summary", "In short", None),
    ("nature", "Your nature", "How you come across, and your core temperament."),
    ("mind", "Your mind", "How you process feeling — where the Moon sits."),
    ("money", "Money and family", "How money tends to move, and family's place in it."),
    ("work_health", "Work and health", "Your working rhythm and the constitution to look after."),
    ("relationships", "Relationships", "What partnership asks of you, and gives you."),
    ("career", "Career", "Your direction, and how visible your work tends to be."),
    ("dasha", "The period you are in", "The planetary period running now, and what it presses on."),
    ("devata", "Your Ishta Devata", "The form of the divine your own chart points toward."),
    ("practice", "One practice", "One small thing to do, suited to this period."),
]

LEGACY_SECTION_ORDER = [
    ("lagna", "Your nature", "How you come across to people, and your basic temperament."),
    ("mind", "Your mind", "How you think and feel — where the Moon sits."),
    ("money", "Money and family", "Your relationship with money, savings, and family support."),
    ("health", "Work and health", "Your daily work patterns and what to watch health-wise."),
    ("relationships", "Relationships", "How partnerships work for you."),
    ("career", "Career", "Your career direction and how visible your work tends to be."),
    ("period", "The period you are in", "The dasha you are running, and what it brings."),
    ("devata", "Your Ishta Devata", "Your guiding deity, from your chart — not your sun sign."),
    ("practice", "One practice", "A simple, specific thing to do during this period."),
]


# ---------------------------------------------------------------- glyphs
def _glyph(kind: str, name: str, color: str, size_mm: float = 3.7):
    table = _glyphs.PLANET_GLYPHS if kind == "planet" else _glyphs.SIGN_GLYPHS
    path = table.get(name)
    if not path:
        return Spacer(size_mm * mm, size_mm * mm)
    # svglib does not resolve "currentColor" — bake the hex in.
    path = path.replace("currentColor", color)
    svg = (f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
           f'<g fill="none" stroke="{color}" stroke-width="1.7" '
           f'stroke-linecap="round" stroke-linejoin="round">{path}</g></svg>')
    return _svg_to_image(svg, size_mm)


# ---------------------------------------------------------------- charts
def _chart_north(chart, pal, size=340):
    by_house, sign_of, _ = _group(chart)
    S = 300
    bg, line, txt, acc = pal["chart_bg"], pal["chart_line"], pal["chart_text"], pal["chart_accent"]
    parts = [
        f'<svg viewBox="0 0 {S} {S}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{S}" height="{S}" fill="{bg}"/>',
        f'<g fill="none" stroke="{line}" stroke-width="1.4">',
        f'<rect x="1" y="1" width="{S-2}" height="{S-2}"/>',
        f'<path d="M1,1 L{S-1},{S-1} M{S-1},1 L1,{S-1}"/>',
        f'<path d="M{S/2},1 L{S-1},{S/2} L{S/2},{S-1} L1,{S/2} Z"/>',
        '</g>',
    ]
    for h in range(1, 13):
        x, y = NORTH_POS[h]
        parts.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Helvetica" '
                     f'font-size="10" fill="{acc}" font-weight="700">{sign_of[h]}</text>')
        planets = [pl.replace("\u1d3f", "R") for pl in by_house[h]]
        for i, row in enumerate([planets[i:i+2] for i in range(0, len(planets), 2)]):
            parts.append(f'<text x="{x}" y="{y+14+i*12}" text-anchor="middle" '
                         f'font-family="Helvetica" font-size="11" fill="{txt}" '
                         f'font-weight="700">{" ".join(row)}</text>')
    ax, ay = NORTH_POS[1]
    parts.append(f'<text x="{ax}" y="{ay-13}" text-anchor="middle" font-family="Helvetica" '
                 f'font-size="9" fill="{pal["chart_accent"]}" font-weight="700" '
                 f'letter-spacing="1">LAGNA</text>')
    parts.append('</svg>')
    return "".join(parts)


def _chart_south(chart, pal, size=340):
    by_house, sign_of, asc_sign = _group(chart)
    house_of_sign = {s: h for h, s in sign_of.items()}
    S, cell = 300, 75
    bg, line, txt, acc = pal["chart_bg"], pal["chart_line"], pal["chart_text"], pal["chart_accent"]
    parts = [
        f'<svg viewBox="0 0 {S} {S}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{S}" height="{S}" fill="{bg}"/>',
    ]
    for sign, (col, row) in SOUTH_CELL.items():
        x, y = col * cell, row * cell
        h = house_of_sign[sign]
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="none" '
                     f'stroke="{line}" stroke-width="1.2"/>')
        if sign == asc_sign:
            parts.append(f'<path d="M{x+3},{y+3} L{x+cell-3},{y+3} L{x+3},{y+cell-3} Z" '
                         f'fill="{acc}" opacity="0.28"/>')
        parts.append(f'<text x="{x+6}" y="{y+14}" font-family="Helvetica" font-size="9" '
                     f'fill="{acc}" font-weight="700">{sign}</text>')
        planets = [pl.replace("\u1d3f", "R") for pl in by_house[h]]
        for i, r in enumerate([planets[i:i+2] for i in range(0, len(planets), 2)]):
            parts.append(f'<text x="{x+cell/2}" y="{y+36+i*13}" text-anchor="middle" '
                         f'font-family="Helvetica" font-size="11" fill="{txt}" '
                         f'font-weight="700">{" ".join(r)}</text>')
    parts.append(f'<text x="{S/2}" y="{S/2-4}" text-anchor="middle" font-family="Helvetica" '
                 f'font-size="11" fill="{acc}" letter-spacing="2">RASI</text>')
    parts.append('</svg>')
    return "".join(parts)


def _chart_navamsa(chart, pal, size=340):
    from chart_svg import _navamsa_of
    nav_asc = SIGN_NUM[_navamsa_of(chart["ascendant"]["longitude"])]
    shifted = {
        "ascendant": {"sign": _navamsa_of(chart["ascendant"]["longitude"]),
                      "longitude": chart["ascendant"]["longitude"]},
        "positions": [
            {**p, "house": ((SIGN_NUM[p["navamsa_sign"]] - nav_asc) % 12) + 1}
            for p in chart["positions"]
        ],
    }
    return _chart_north(shifted, pal, size)


def _svg_to_image(svg_string: str, size_mm: float) -> Drawing:
    """SVG -> reportlab vector Drawing, scaled to fit a size_mm box. Stays
    vector in the PDF (no rasteriser / compiled backend needed)."""
    drawing = svg2rlg(BytesIO(svg_string.encode()))
    target = size_mm * mm
    scale = target / max(drawing.width or 1, drawing.height or 1)
    scaled = Drawing(target, target)
    g = Group(drawing)
    g.scale(scale, scale)
    scaled.add(g)
    return scaled


def _charts_row(chart, pal, styles):
    size = 52
    imgs = [_svg_to_image(_chart_north(chart, pal), size),
            _svg_to_image(_chart_south(chart, pal), size),
            _svg_to_image(_chart_navamsa(chart, pal), size)]
    labels = [Paragraph(t, styles["cap"]) for t in ("North Indian", "South Indian", "Navamsa D9")]
    t = Table([imgs, labels], colWidths=[size * mm + 6] * 3)
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    return t


# ---------------------------------------------------------------- header band
def _highlight_band(chart, pal, styles):
    asc = chart["ascendant"]
    ink_pal = pal
    cells = [
        [Paragraph("LAGNA", styles["hl_label"]),
         Paragraph("MOON SIGN", styles["hl_label"]),
         Paragraph("NAKSHATRA", styles["hl_label"])],
        [_sign_cell(asc["sign"], pal, styles),
         _sign_cell(chart["moon_sign"], pal, styles),
         Paragraph(chart["birth_nakshatra"], styles["hl_value"])],
    ]
    t = Table(cells, colWidths=[56 * mm] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor(ink_pal["card"])),
        ("BOX", (0, 0), (-1, -1), 0.75, HexColor(pal["accent_soft"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor(pal["rule"])),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _sign_cell(sign, pal, styles):
    """A zodiac glyph next to the sign name, centred."""
    g = _glyph("sign", sign, pal["head"], 4.2)
    inner = Table([[g, Paragraph(sign, styles["hl_value"])]],
                  colWidths=[6 * mm, 44 * mm])
    inner.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return inner


# ---------------------------------------------------------------- tables
def _positions_table(positions, pal, styles):
    rows = [[Paragraph("", styles["th"]), Paragraph("PLANET", styles["th"]),
             Paragraph("", styles["th"]), Paragraph("SIGN · DEGREE", styles["th"]),
             Paragraph("NAKSHATRA", styles["th"]), Paragraph("HO.", styles["th"])]]
    for p in positions:
        name = p["name"] + ("  R" if p["retrograde"] else "")
        rows.append([
            _glyph("planet", p["name"], pal["accent"], 3.6),
            Paragraph(name, styles["td"]),
            _glyph("sign", p["sign"], pal["muted"], 3.4),
            Paragraph(f"{p['sign']} {p['degree_in_sign']}", styles["td"]),
            Paragraph(f"{p['nakshatra']} {p['pada']}", styles["td"]),
            Paragraph(str(p["house"]), styles["td"]),
        ])
    t = Table(rows, colWidths=[7 * mm, 21 * mm, 6 * mm, 39 * mm, 41 * mm, 18 * mm])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, HexColor(pal["accent_soft"])),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, HexColor(pal["rule"])),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 1),
        ("LEFTPADDING", (2, 0), (2, -1), 1),
    ]))
    return t


def _dasha_table(chart, pal, styles):
    import datetime as dt
    today = dt.date.today().isoformat()
    rows = [[Paragraph("PERIOD", styles["th"]), Paragraph("FROM", styles["th"]),
             Paragraph("TO", styles["th"]), Paragraph("", styles["th"])]]
    for md in chart["vimshottari"]:
        active = md["start"] <= today < md["end"]
        rows.append([
            Paragraph(md["lord"], styles["td"]),
            Paragraph(md["start"], styles["td"]),
            Paragraph(md["end"], styles["td"]),
            Paragraph("now" if active else "", ParagraphStyle(
                "now", parent=styles["td"], fontName=HEAD, textColor=HexColor(pal["accent"]))),
        ])
    t = Table(rows, colWidths=[28 * mm, 34 * mm, 34 * mm, 16 * mm])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, HexColor(pal["accent_soft"])),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor(pal["rule"])),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _kv_table(pairs, pal, styles):
    rows = [[Paragraph(k, styles["td"]), Paragraph(str(v), ParagraphStyle(
        "v", parent=styles["td"], fontName=HEAD, textColor=HexColor(pal["head"])))]
        for k, v in pairs]
    t = Table(rows, colWidths=[45 * mm, 55 * mm])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor(pal["rule"])),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ---------------------------------------------------------------- background
def _bg_painter(color_hex):
    col = HexColor(color_hex)

    def paint(canvas_obj, _doc):
        canvas_obj.saveState()
        canvas_obj.setFillColor(col)
        canvas_obj.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas_obj.restoreState()
    return paint


# ---------------------------------------------------------------- build
def build_pdf(chart: dict, sections: dict, name: str = "", theme: str = "light",
              section_order=None, avakhada_data: dict = None, kp_data: dict = None,
              ashtakvarga_data: dict = None) -> bytes:
    """sections: {key: prose}. section_order: list of (key, title, caption);
    defaults to LLM_SECTION_ORDER. Returns raw PDF bytes."""
    pal = PALETTES.get(theme, PALETTES["light"])
    st = _styles(pal)
    order = section_order or LLM_SECTION_ORDER

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=16 * mm,
                            leftMargin=19 * mm, rightMargin=19 * mm,
                            title=f"Muhurata reading{(' — ' + name) if name else ''}")
    story = []

    # ---- masthead
    story.append(Paragraph("Muhurata", st["wordmark"]))
    story.append(Paragraph("CHART · TIMING · ACTION", st["kicker"]))
    if name:
        story.append(Paragraph(f"a reading for {name}", st["for_line"]))
    asc = chart["ascendant"]
    story.append(Spacer(1, 8))
    story.append(_highlight_band(chart, pal, st))
    story.append(Spacer(1, 12))

    # ---- opening paragraph (the "summary" section, set larger)
    if sections.get("summary"):
        story.append(Paragraph(sections["summary"].replace("\n\n", "<br/><br/>"), st["lead"]))
        story.append(Spacer(1, 6))

    # ---- charts
    story.append(Paragraph("Your charts", st["sec_title"]))
    story.append(Paragraph("Drawn two classical ways, plus the navamsa (D9).", st["sec_caption"]))
    story.append(_charts_row(chart, pal, st))
    story.append(Spacer(1, 8))

    # ---- reading sections
    for key, title, caption in order:
        if key == "summary":
            continue
        text = (sections.get(key) or "").strip()
        if not text:
            continue
        block = [Paragraph(title, st["sec_title"])]
        if caption:
            block.append(Paragraph(caption, st["sec_caption"]))
        block.append(HRFlowable(width="26%", thickness=1, color=HexColor(pal["accent_soft"]),
                                spaceBefore=1, spaceAfter=5, hAlign="LEFT"))
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        for p in paras:
            block.append(Paragraph(p, st["body"]))
        # keep the title with at least its first paragraph
        story.append(KeepTogether(block[:3] if len(block) > 3 else block))
        for f in block[3:]:
            story.append(f)

    # ---- avakhada + panchang
    if avakhada_data:
        av = avakhada_data.get("avakhada", {})
        if av:
            story.append(Paragraph("Birth attributes (Avakhada)", st["sec_title"]))
            story.append(Paragraph("Classical attributes from the Moon at birth.", st["sec_caption"]))
            story.append(_kv_table(
                [(lbl, av.get(k, "")) for lbl, k in [
                    ("Varna", "varna"), ("Vashya", "vashya"), ("Yoni", "yoni"),
                    ("Gana", "gana"), ("Nadi", "nadi"), ("Tatva", "tatva"),
                    ("Sign lord", "sign_lord"), ("Nakshatra lord", "nakshatra_lord"),
                    ("Pada", "charan")]],
                pal, st))
        pc = avakhada_data.get("panchang", {})
        if pc:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Panchang at birth", st["sec_title"]))
            story.append(Paragraph(
                f"Tithi {pc.get('tithi','')} · Yoga {pc.get('yoga','')} · "
                f"Karana {pc.get('karana','')} · Nakshatra {pc.get('nakshatra','')}",
                st["body"]))

    # ---- positions
    story.append(Paragraph("Planetary positions", st["sec_title"]))
    story.append(Paragraph("Where each planet sits — the data everything above rests on.",
                           st["sec_caption"]))
    story.append(_positions_table(chart["positions"], pal, st))

    # ---- dasha timeline
    if "vimshottari" in chart:
        story.append(Paragraph("Vimshottari Dasha timeline", st["sec_title"]))
        story.append(Paragraph("Your life in major planetary periods.", st["sec_caption"]))
        story.append(_dasha_table(chart, pal, st))

    # ---- footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor(pal["accent_soft"]),
                            spaceBefore=16, spaceAfter=6))
    story.append(Paragraph(
        "Positions: standard ephemeris, sidereal, Lahiri ayanamsa. The reading "
        "is drawn from classical texts — a reading, not a scientific prediction.",
        st["footer"]))
    story.append(Paragraph("muhurata.com", st["footer"]))

    painter = _bg_painter(pal["bg"])
    doc.build(story, onFirstPage=painter, onLaterPages=painter)
    return buf.getvalue()
