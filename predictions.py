"""
predictions.py — the long-form, AstroTalk-style prediction paragraphs,
generated per-chart through the LLM (via naksha's call_llm) rather than
a hand-written library.

Honest trade-off, stated plainly so future-me remembers:
  - AstroTalk has thousands of pre-written paragraphs. Instant, but generic
    (same text for everyone with Mars-in-12th).
  - This generates text tailored to the ACTUAL chart - the specific house,
    sign, degree, and running dasha - which is more personal, but costs a
    token call and a few seconds per section.
  - So we generate once and CACHE by chart, so the cost is paid once per
    unique birth chart, not once per page view.

Every prediction is built ON TOP of the real calculated chart data. The
LLM is told the exact placements and asked to explain them - it is not
inventing astrology, it is putting the deterministic calculation into
readable, specific prose. That distinction is the whole point.
"""

import json
import time

import naksha
from naksha import _clean_reply


# Each prediction "section" is grounded in specific real chart data. The
# first five back the /api/predictions tab UI; the rest are used to write
# the full PDF reading (see PDF_SECTION_ORDER).
SECTIONS = {
    "personality": {
        "title": "Personality & Nature",
        "focus": "the ascendant (lagna) sign and its lord's placement, and "
                 "the Moon sign - describe how this person comes across, "
                 "their temperament, strengths and blind spots",
    },
    "career": {
        "title": "Career & Profession",
        "focus": "the 10th house sign and any planets in it, the 10th lord's "
                 "placement, and the running mahadasha - describe career "
                 "direction, work style, and current professional phase",
    },
    "wealth": {
        "title": "Wealth & Finances",
        "focus": "the 2nd house (savings, family wealth) and 11th house "
                 "(gains, income) and their occupants - describe the "
                 "financial pattern and how money tends to flow",
    },
    "relationships": {
        "title": "Marriage & Relationships",
        "focus": "the 7th house sign and occupants, Venus placement, and "
                 "any Mangal dosha - describe partnership patterns and what "
                 "this person needs from a relationship",
    },
    "health": {
        "title": "Health",
        "focus": "the 1st house (vitality), 6th house (illness, daily "
                 "habits), and the ascendant sign's classical body "
                 "associations - describe general constitution and areas "
                 "to watch, without alarmism",
    },

    # ---- sections used to compose the full PDF reading ----
    "summary": {
        "title": "In short",
        "focus": "the lagna, the Moon sign, the birth nakshatra and the "
                 "running mahadasha/antardasha together - one tight opening "
                 "paragraph that says who this person is and what phase they "
                 "are in. ONE paragraph only, 4-6 sentences",
        "length": "one paragraph",
    },
    "nature": {
        "title": "Your nature",
        "focus": "the ascendant sign, its lord's house, and the 1st house "
                 "occupants - how they come across, their core temperament, "
                 "what they lead with and what trips them up",
    },
    "mind": {
        "title": "Your mind",
        "focus": "the Moon's sign, house and nakshatra - how they process "
                 "emotion, what their attention returns to, how they settle "
                 "or unsettle",
    },
    "money": {
        "title": "Money and family",
        "focus": "the 2nd and 11th houses, their signs, lords and occupants - "
                 "how money tends to come and go, and the place of family "
                 "support",
    },
    "work_health": {
        "title": "Work and health",
        "focus": "the 6th house (daily work, routine, health) and the "
                 "ascendant sign's bodily temperament - work rhythm and the "
                 "constitution to look after, no alarmism",
    },
    "dasha": {
        "title": "The period you are in",
        "focus": "the running mahadasha lord and antardasha lord, their "
                 "natures and placements, and when the antardasha ends - "
                 "what this specific stretch of time tends to bring up and "
                 "how to work with it",
    },
    "devata": {
        "title": "Your Ishta Devata",
        "focus": "the atmakaraka planet and the ishta devata derived from "
                 "the karakamsa - who this deity is and why the chart points "
                 "here, warmly and without prescribing ritual",
    },
    "practice": {
        "title": "One practice",
        "focus": "the running mahadasha lord - ONE small, concrete, doable "
                 "practice suited to that planet, phrased as an invitation. "
                 "Two to three sentences, not a paragraph",
        "length": "two or three sentences",
    },
}

# The prose sections that make up the downloadable PDF, in order. Each is
# LLM-written and cached per (chart, section) in the predictions table.
PDF_SECTION_ORDER = [
    "summary", "nature", "mind", "money", "work_health",
    "relationships", "career", "dasha", "devata", "practice",
]


def _chart_facts(chart: dict, running: dict) -> str:
    """A compact, factual dump of the real chart the LLM must ground its
    prediction in. No interpretation here - just the calculated truth,
    INCLUDING the deterministically-derived atmakaraka and ishta devata
    (so the devata section states the computed deity, never a guess)."""
    asc = chart["ascendant"]
    lines = [
        f"Ascendant (Lagna): {asc['sign']} at {asc['degree_in_sign']}, "
        f"nakshatra {asc['nakshatra']}",
        f"Moon sign: {chart['moon_sign']}, birth nakshatra: {chart['birth_nakshatra']}",
        f"Running: {running['mahadasha']} mahadasha, {running['antardasha']} antardasha"
        + (f" (antardasha ends {running['antardasha_ends']})"
           if running.get("antardasha_ends") else ""),
    ]
    ak = chart.get("atmakaraka")
    if ak:
        lines.append(f"Atmakaraka (soul planet): {ak['planet']}, navamsa "
                     f"{ak.get('navamsa_sign', '')}")
    try:
        from chart_engine import ishta_devata
        dev = ishta_devata(chart)
        lines.append(f"Ishta Devata (computed, USE THIS EXACT DEITY — do not "
                     f"substitute another): {dev['devata']} "
                     f"(via {dev['indicator']}, 12th from karakamsa = "
                     f"{dev['karakamsa_12th']})")
    except Exception:
        pass
    lines.append("Planet placements (planet: sign, house, retrograde):")
    for p in chart["positions"]:
        r = " retrograde" if p["retrograde"] else ""
        lines.append(f"  {p['name']}: {p['sign']}, house {p['house']}{r}")
    return "\n".join(lines)


PREDICTION_SYSTEM = """You are a careful Vedic astrologer writing a birth \
chart reading. You write clear, warm, specific prose in plain English that \
an ordinary person understands - no heavy jargon, and when you use a Sanskrit \
term you gloss it briefly.

Absolute rules:
- Ground EVERY statement in the specific chart data you are given. Refer to \
the actual houses, signs, and placements. Never write generic filler that \
would apply to anyone.
- Two to three short paragraphs per section. Substantial, but not padded.
- Be honest and balanced: name both strengths and challenges. Never predict \
death, serious disease, or disaster. Frame difficulties as tendencies to \
work with, not fixed fate.
- No hedging boilerplate like "consult an astrologer for details". Write the \
reading itself, confidently but not arrogantly.
- Do not invent placements that are not in the data.

Tone: warm, grounded, and personal, like a thoughtful elder who knows this \
person. Speak TO them ("your", "you"), not about a chart. Lead with what is \
working before what to watch.

When a house has no planet in it, that is normal and NOT a lack — most \
houses in most charts are like that. Never say a house is "empty", "vacant", \
"has nothing", or use that as a negative. Instead read it through its sign \
and its lord's placement, and describe it as an area that runs quietly, on \
its own terms, shaped by where its ruler sits and by any planets aspecting \
it. A house with no planet is a room with the lights low, not a room with \
nothing in it."""


def generate_section(chart: dict, running: dict, section_key: str,
                     name: str = "") -> str:
    """Generate one prediction section. Raises if the LLM is unreachable
    or unconfigured - the caller decides how to degrade."""
    if section_key not in SECTIONS:
        raise ValueError(f"unknown section {section_key}")
    if not naksha.configured():
        raise RuntimeError("LLM not configured")

    sec = SECTIONS[section_key]
    facts = _chart_facts(chart, running)
    who = f" for {name}" if name else ""
    length = sec.get("length", "two to three short paragraphs")
    # Headroom: a reasoning model still generates (hidden) thinking tokens
    # even with reasoning excluded, and they eat this budget — too tight a
    # cap truncates the visible answer mid-sentence.
    max_tokens = 500 if "sentence" in length else (650 if "one paragraph" in length else 1100)
    user_msg = (
        f"Write the '{sec['title']}' section of a birth chart reading{who}, "
        f"focusing on {sec['focus']}.\n\n"
        f"Here is the actual chart to ground everything in:\n\n{facts}\n\n"
        f"Write the section now - {length}, specific to this chart. Plain "
        f"prose only: no headings, no bullet points, no markdown, no labels."
    )

    # Reuse naksha's provider layer, but WITHOUT tools (this is pure prose)
    # and with a token budget sized to the section.
    messages = [{"role": "user", "content": user_msg}]
    if naksha.LLM_PROVIDER == "openrouter":
        resp = naksha._post(
            "https://openrouter.ai/api/v1/chat/completions",
            {"Authorization": "Bearer " + naksha.OPENROUTER_KEY,
             "HTTP-Referer": "https://muhurata.com", "X-Title": "Muhurata"},
            {"model": naksha.OPENROUTER_MODEL, "max_tokens": max_tokens,
             "reasoning": {"exclude": True},   # final answer only, no scratchpad
             "messages": [{"role": "system", "content": PREDICTION_SYSTEM}] + messages},
        )
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "LLM error"))
        choices = resp.get("choices") or []
        # Some free OpenRouter models return content=None (tool-only turn,
        # length cut, or a content filter). Treat that as a real failure
        # rather than crashing on .strip().
        text = (choices[0].get("message", {}).get("content") if choices else None) or ""
    else:
        resp = naksha._post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": naksha.ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
            {"model": naksha.ANTHROPIC_MODEL, "max_tokens": max_tokens,
             "system": PREDICTION_SYSTEM, "messages": messages},
        )
        blocks = resp.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    text = _clean_reply(text or "")
    if not text:
        raise RuntimeError("the model returned an empty response — try again")
    # Guard against a reasoning model leaking its planning notes into the
    # answer (belt-and-braces alongside reasoning={"exclude": true}). Such
    # text must never be cached as a real section.
    head = text[:160].lower()
    if any(m in head for m in (
        "we need to", "let's parse", "let's think", "let me ", "the user wants",
        "first, i", "okay, so", "we must ", "i need to write", "we should ")):
        raise RuntimeError("model returned reasoning scratchpad, not prose")
    return text


def generate_many(chart: dict, running: dict, name: str, section_keys,
                  cache_get=None, cache_put=None, fallback=None,
                  max_workers: int = 3) -> dict:
    """Generate several sections at once for the PDF reading.

    cache_get(key) / cache_put(key, text): optional persistence, so a
      given chart pays the LLM cost once (wired to the predictions table
      in app.py).
    fallback(key) -> str: used when the LLM call for a section fails, so
      one bad call never sinks the whole document.

    Returns {section_key: text}. Runs the misses concurrently.
    """
    from concurrent.futures import ThreadPoolExecutor

    out, misses = {}, []
    for key in section_keys:
        cached = cache_get(key) if cache_get else None
        if cached:
            out[key] = cached
        else:
            misses.append(key)

    def _one(key):
        # one retry — a free model often 429s or returns a stub on the
        # first hit of a 10-section burst and succeeds on a second try
        last = None
        for attempt in (1, 2):
            try:
                text = generate_section(chart, running, key, name)
                if cache_put:
                    try:
                        cache_put(key, text)
                    except Exception:
                        pass
                return key, text
            except Exception as e:
                last = e
                if attempt == 1:
                    time.sleep(1.5)
        print(f"[pdf] section {key!r} fell back to rule-based: "
              f"{type(last).__name__}: {last}", flush=True)
        return key, (fallback(key) if fallback else "")

    if misses:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for key, text in pool.map(_one, misses):
                out[key] = text
    return out
