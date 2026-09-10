"""
naksha.py — the chat brain.

Three layers, cheapest first:

  1. FAQ match      free, instant, no API call. Covers the questions
                     almost everyone asks (what is a dasha, etc).
  2. Service intent  free. If the message is clearly asking for a kundali,
                     horoscope, or match, the frontend routes it to the
                     existing /api/kundali /api/horoscope /api/matching
                     endpoints directly - no LLM needed for that either.
  3. LLM chat        costs money. Only reached when 1 and 2 don't cover it.
                     Capped per session per day. Uses Claude Haiku with
                     tool use, so it can still call the free services
                     itself mid-conversation if the person gives it
                     birth details in plain text.

This ordering is the whole cost strategy: most real questions never
reach step 3.
"""

import json
import os
import db
import time
import urllib.request
from datetime import datetime, timedelta, timezone

FREE_DAILY_LIMIT = 5

# ---------------------------------------------------------------- provider
# Two backends, one normalized interface, switched by an env var so
# testing on a free model and running on paid Haiku never means a
# second rewrite - just a different value here.
#
#   LLM_PROVIDER=openrouter   speaks OpenAI's chat-completions format.
#                              Set OPENROUTER_API_KEY. Defaults to
#                              openrouter/free, a router that picks
#                              among free models filtered for tool-call
#                              support - safer than pinning one free
#                              model, which tends to vanish or go paid
#                              on its own schedule.
#   LLM_PROVIDER=anthropic    speaks Anthropic's native Messages API.
#                              Set ANTHROPIC_API_KEY. This is the path
#                              to switch to for production.
#
# Free-tier note: some free models on OpenRouter may use prompts for
# training. Test with made-up birth details, not real ones.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter").strip().lower()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Raised from 300 -> 600 after real answers were observed cutting off
# mid-sentence, especially ones grounded in tool results (chart data +
# explanation together runs longer than plain FAQ text). 600 tokens is
# roughly 420-450 English words. Costed at Haiku 4.5 pricing ($5/M
# output tokens), a maxed-out 600-token reply is about $0.003 - still a
# fraction of a rupee. On the free OpenRouter model this costs nothing
# regardless. Raise further only if replies are STILL visibly cut off.
MAX_TOKENS = int(os.environ.get("NAKSHA_MAX_TOKENS", "600"))


def configured() -> bool:
    if LLM_PROVIDER == "openrouter":
        return bool(OPENROUTER_KEY)
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_KEY)
    return False

# ---------------------------------------------------------------- FAQ
# Keyword -> answer. Checked before anything else. Add to this file
# freely; every entry answered here is an entry that costs nothing.
FAQ = [
    (["dasha"],
     "A dasha is a planetary period. Vedic astrology divides your life into "
     "stretches of time ruled by different planets - the vimshottari system "
     "runs on a 120 year cycle. Whichever planet's dasha you're in colours "
     "what that period tends to bring up. Want to know which one you're in? "
     "Just share your birth details and I'll work it out."),
    (["nakshatra"],
     "A nakshatra is one of 27 lunar constellations the moon passes through. "
     "Your birth nakshatra is whichever one the Moon was in at the moment "
     "you were born, and it's more specific than your moon sign - each sign "
     "contains a little over two nakshatras."),
    (["ishta devata", "isht dev", "ishta dev"],
     "Your Ishta Devata is the form of the divine your own chart points you "
     "toward - worked out from the atmakaraka, the planet at the highest "
     "degree in your chart, and where its navamsa placement leads. It's "
     "personal to your chart, not a general rule like a sun sign horoscope."),
    (["muhurat", "muhurta", "auspicious time"],
     "A muhurat is the astrologically supported window for starting "
     "something - a wedding, a house move, a launch. It's read from the "
     "panchang for a specific date and place, not guessed."),
    (["mangal dosha", "manglik"],
     "Mangal dosha shows up when Mars sits in the 1st, 2nd, 4th, 7th, 8th "
     "or 12th house from the ascendant. It's commonly cancelled when both "
     "charts in a match carry it, and by a few other classical exceptions - "
     "so it's worth checking properly rather than treating it as a verdict."),
    (["guna milan", "kundali match", "kundli match", "matching score",
      "36 points", "gun milan", "compatibility score"],
     "Guna milan scores compatibility across eight kootas - varna, vashya, "
     "tara, yoni, graha maitri, gana, bhakoot and nadi - out of 36 total. "
     "18 is the usual threshold. Want me to run an actual match? I'll need "
     "both people's birth details."),
    (["north indian", "south indian", "chart style", "kundli style", "kundali style"],
     "North Indian charts are a fixed diamond where houses stay put and "
     "signs rotate. South Indian charts are a fixed grid where signs stay "
     "put and houses rotate. Same information, different convention - "
     "North is standard in the Hindi belt, South in Tamil Nadu, Kerala, "
     "Andhra and Karnataka."),
    (["navamsa", "d9", "d-9"],
     "The navamsa, or D9, is the divisional chart made by splitting each "
     "sign into nine parts. It's read alongside the main chart for "
     "marriage and inner strength, and it's what your Ishta Devata is "
     "actually calculated from."),
    (["rahu", "ketu"],
     "Rahu and Ketu are the lunar nodes - not physical planets, but the "
     "points where the Moon's path crosses the Sun's. They're always "
     "exactly opposite each other. Rahu is associated with ambition and "
     "unclear appetite, Ketu with detachment and release."),
    (["how accurate", "is this real", "is this accurate", "actually accurate"],
     "The planetary positions are exact - standard ephemeris data, "
     "sidereal, Lahiri ayanamsa, the same maths every serious astrology "
     "tool uses. The interpretation on top of that is a reading drawn from "
     "classical texts, not a scientific prediction. We're upfront about "
     "that distinction rather than blurring it."),
]


def match_faq(message: str):
    m = message.lower()
    for keys, answer in FAQ:
        if any(k in m for k in keys):
            return answer
    return None


# ---------------------------------------------------------------- rate limit
def check_and_increment(user_id: str, cost: bool):
    """Returns (allowed, remaining). Only increments if cost=True, so FAQ
    and service-intent replies never touch the quota.

    Keyed on the verified Supabase user id (app.py passes user["id"]).
    A page refresh no longer resets the count, and a fresh identity now
    needs a real Google account. The naksha_usage table is created by
    migrations/0002, not here."""
    # reset the daily quota at midnight IST, not UTC
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date().isoformat()

    with db.cursor() as c:
        row = c.execute(
            "SELECT count FROM naksha_usage WHERE user_id=? AND day=?",
            (user_id, today),
        ).fetchone()
    used = row["count"] if row else 0

    if not cost:
        return True, max(0, FREE_DAILY_LIMIT - used)

    if used >= FREE_DAILY_LIMIT:
        return False, 0

    with db.cursor() as c:
        c.execute(
            "INSERT INTO naksha_usage (user_id, day, count) VALUES (?,?,1) "
            "ON CONFLICT (user_id, day) DO UPDATE SET count = naksha_usage.count + 1",
            (user_id, today),
        )
    return True, FREE_DAILY_LIMIT - used - 1


# ---------------------------------------------------------------- LLM
SYSTEM_PROMPT = """You are Naksha, the chat guide for Muhurata, a Vedic \
astrology service. Your name means "map" in Hindi/Urdu.

Voice: calm, warm, direct. Short sentences. Never mystical-vague, never \
salesy. You explain classical concepts plainly and you are honest about \
what is calculation (exact) versus interpretation (a reading, not a fact).

CRITICAL OUTPUT RULES:
- Reply with ONLY your answer to the user. Do NOT include any thinking, \
  reasoning, planning, or internal monologue in your response.
- Do NOT write things like "The user is asking about..." or "I should \
  respond with..." or "Let me think about this" — just give the answer.
- Do NOT use markdown formatting like **bold** or *italic* or # headers. \
  Write in plain text only. No asterisks around words.
- Keep replies short. Two to four sentences unless the person clearly \
  wants more.

Hard rules:
- Give readings, not disclaimers. When someone asks about marriage, a \
  specific partner, career, money, children, timing, or "will X happen" — \
  answer the way a seasoned classical astrologer would: read the relevant \
  house, its lord, the planets in and aspecting it, the running \
  mahadasha/antardasha, and any yoga, and say what the chart leans toward. \
  Be specific and confident: "your 7th house and Venus read as steady and \
  loyal", "this is a supportive period for commitment", "the yoga here \
  favours it, especially after <dasha> turns". If they are already in a \
  relationship, read that: "if you're with someone now, the chart shows \
  it as strong / worth working at / needing patience". \
  NEVER deflect with "astrology only shows compatibility" or "I can't say \
  whether you specifically will marry them" — give the reading of the \
  tendency and the likely timing.
- Frame every prediction as the chart's leaning, not sealed fate: "the \
  chart favours", "this reads as", "classically this points to", "the \
  timing looks like" — not "you will definitely".
- The one line you never cross: do not predict death, a terminal or \
  serious illness, or an accident/disaster. If pushed there, say plainly \
  that you don't read for those, and turn to what the chart does support.
- Never pressure a purchase. Mention paid features once, plainly, move on.
- If someone gives you birth details (name, date, time, place), use the \
  tools to calculate the real chart, horoscope, or match rather than \
  guessing.
- If a question is entirely outside astrology, say so and steer back.
"""

# Tool definitions in Anthropic's shape (name/description/input_schema).
# Converted to OpenAI's shape (type:function, function:{...,parameters})
# at request time for the OpenRouter path - one source of truth either way.
TOOLS = [
    {
        "name": "get_kundali",
        "description": "Calculate a birth chart - lagna, moon sign, "
                       "nakshatra, running dasha, Ishta Devata. Use this "
                       "when the person gives full birth details and wants "
                       "their chart or asks who their Ishta Devata is.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "dob": {"type": "string", "description": "YYYY-MM-DD"},
                "tob": {"type": "string", "description": "HH:MM, 24 hour"},
                "place": {"type": "string"},
            },
            "required": ["name", "dob", "tob", "place"],
        },
    },
    {
        "name": "get_horoscope",
        "description": "Get today's, tomorrow's, this month's or this "
                       "year's horoscope for one zodiac sign, read from "
                       "actual current planetary transits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sign": {"type": "string", "description": "e.g. Simha, Mesha"},
                "period": {"type": "string",
                          "enum": ["today", "tomorrow", "monthly", "yearly"]},
            },
            "required": ["sign", "period"],
        },
    },
    {
        "name": "get_matching",
        "description": "Run kundali matching (guna milan) between two "
                       "people given both sets of full birth details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "boy": {"type": "object", "properties": {
                    "name": {"type": "string"}, "dob": {"type": "string"},
                    "tob": {"type": "string"}, "place": {"type": "string"}}},
                "girl": {"type": "object", "properties": {
                    "name": {"type": "string"}, "dob": {"type": "string"},
                    "tob": {"type": "string"}, "place": {"type": "string"}}},
            },
            "required": ["boy", "girl"],
        },
    },
]


def _tools_openai_shape():
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["input_schema"]}} for t in TOOLS]


def _post(url, headers, body, timeout=30):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={**headers, "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_anthropic(messages: list) -> dict:
    """Anthropic's native Messages API. Returns the normalized shape:
    {stop_reason, text, tool_calls: [{id, name, input}]}."""
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    resp = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
        {"model": ANTHROPIC_MODEL, "max_tokens": MAX_TOKENS,
         "system": SYSTEM_PROMPT, "messages": messages, "tools": TOOLS},
    )
    blocks = resp.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    calls = [{"id": b["id"], "name": b["name"], "input": b.get("input", {})}
             for b in blocks if b.get("type") == "tool_use"]
    return {"stop_reason": resp.get("stop_reason"), "text": text.strip(),
            "tool_calls": calls, "_raw_assistant_blocks": blocks}


def call_openrouter(messages: list) -> dict:
    """OpenRouter's OpenAI-compatible chat-completions format. Same
    normalized return shape as call_anthropic, so chat_turn never needs
    to know which provider answered."""
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    oi_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    resp = _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {"Authorization": "Bearer " + OPENROUTER_KEY,
         "HTTP-Referer": "https://muhurata.com", "X-Title": "Naksha"},
        {"model": OPENROUTER_MODEL, "max_tokens": MAX_TOKENS,
         # Reasoning models (nemotron, deepseek-r1, …) otherwise leak their
         # scratchpad into `content`; this returns the final answer only.
         # Harmless for non-reasoning models like gpt-4o.
         "reasoning": {"exclude": True},
         "messages": oi_messages, "tools": _tools_openai_shape()},
    )
    if "error" in resp:
        raise RuntimeError(resp["error"].get("message", "OpenRouter error"))

    choice = resp["choices"][0]
    msg = choice["message"]
    finish = choice.get("finish_reason")
    raw_calls = msg.get("tool_calls") or []
    calls = []
    for tc in raw_calls:
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        calls.append({"id": tc["id"], "name": tc["function"]["name"], "input": args})

    stop_reason = "tool_use" if (finish == "tool_calls" or calls) else "end_turn"
    return {"stop_reason": stop_reason, "text": (msg.get("content") or "").strip(),
            "tool_calls": calls, "_raw_assistant_message": msg}


def call_llm(messages: list) -> dict:
    if LLM_PROVIDER == "openrouter":
        return call_openrouter(messages)
    if LLM_PROVIDER == "anthropic":
        return call_anthropic(messages)
    raise RuntimeError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")


def complete(system: str, user: str, max_tokens: int = 500) -> str:
    """One-shot plain-prose completion (no tools). Shared by predictions,
    tarot and swayamvar. Raises on an unreachable / empty model."""
    if not configured():
        raise RuntimeError("LLM not configured")
    if LLM_PROVIDER == "openrouter":
        resp = _post(
            "https://openrouter.ai/api/v1/chat/completions",
            {"Authorization": "Bearer " + OPENROUTER_KEY,
             "HTTP-Referer": "https://muhurata.com", "X-Title": "Muhurata"},
            {"model": OPENROUTER_MODEL, "max_tokens": max_tokens,
             "reasoning": {"exclude": True},   # final answer only, no scratchpad
             "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": user}]},
        )
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "LLM error"))
        choices = resp.get("choices") or []
        text = (choices[0].get("message", {}).get("content") if choices else None) or ""
    else:
        resp = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
            {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
             "messages": [{"role": "user", "content": user}]},
        )
        text = "".join(b.get("text", "") for b in resp.get("content", [])
                       if b.get("type") == "text")
    text = _clean_reply(text or "")
    if not text:
        raise RuntimeError("the model returned an empty response — try again")
    return text


def run_tool(name: str, tool_input: dict, chart_fn, horoscope_fn, match_fn):
    """Dispatch a tool call to the real, already-tested service functions.
    Never invents data - if geocoding or validation fails, the error
    string goes back to the model so it can explain that to the person."""
    try:
        if name == "get_kundali":
            return chart_fn(tool_input)
        if name == "get_horoscope":
            data = horoscope_fn(tool_input["period"])
            sign = tool_input["sign"].strip().title()
            row = next((s for s in data["signs"] if s["sign"] == sign), None)
            return row or {"error": f"Unknown sign '{sign}'"}
        if name == "get_matching":
            return match_fn(tool_input["boy"], tool_input["girl"])
        return {"error": f"Unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)}


def _append_assistant_turn(messages, norm):
    """Append the assistant's tool-call turn in whichever shape the
    active provider expects, so the next call sees valid history."""
    if LLM_PROVIDER == "anthropic":
        messages.append({"role": "assistant", "content": norm["_raw_assistant_blocks"]})
    else:
        messages.append({"role": "assistant", "content": norm.get("text") or None,
                         "tool_calls": [
                             {"id": c["id"], "type": "function",
                              "function": {"name": c["name"], "arguments": json.dumps(c["input"])}}
                             for c in norm["tool_calls"]]})


def _append_tool_results(messages, norm, results):
    """results: list of (call, result_dict) pairs, same order as norm['tool_calls']."""
    if LLM_PROVIDER == "anthropic":
        content = [{"type": "tool_result", "tool_use_id": call["id"],
                    "content": json.dumps(result)[:4000]}
                   for call, result in results]
        messages.append({"role": "user", "content": content})
    else:
        for call, result in results:
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(result)[:4000]})


def _clean_reply(text: str) -> str:
    """Strip thinking-token leaks and markdown from free-model responses.
    Free models on OpenRouter sometimes ignore system-prompt instructions
    and output their internal reasoning or markdown formatting anyway.
    This catches it at the code level so the user never sees it."""
    import re
    # strip <think>...</think> blocks some models emit
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    # strip lines that look like internal monologue
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        low = line.strip().lower()
        if any(low.startswith(p) for p in [
            'the user is', 'i should', 'let me think', 'i need to',
            'the question is', 'i will', 'my response', 'thinking:',
            'reasoning:', 'analysis:', 'internal:'
        ]):
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned).strip()
    # strip markdown bold/italic: **text** -> text, *text* -> text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # strip markdown headers: ### text -> text
    text = re.sub(r'^#{1,4}\s*', '', text, flags=re.M)
    return text.strip()


def chat_turn(history: list, chart_fn, horoscope_fn, match_fn) -> dict:
    """Runs one full turn including any tool-use round trips. Provider-
    agnostic: works off call_llm's normalized shape regardless of which
    backend answered. Returns {"reply": str, "tool_results": [...]} -
    tool_results lets the frontend render a chart/horoscope card instead
    of just text."""
    messages = list(history)
    collected = []

    for _ in range(4):   # hard cap on tool-call loops
        norm = call_llm(messages)

        if norm["stop_reason"] != "tool_use" or not norm["tool_calls"]:
            return {"reply": _clean_reply(norm["text"]), "tool_results": collected}

        _append_assistant_turn(messages, norm)

        results = []
        for call in norm["tool_calls"]:
            result = run_tool(call["name"], call["input"], chart_fn, horoscope_fn, match_fn)
            collected.append({"tool": call["name"], "input": call["input"], "result": result})
            results.append((call, result))
        _append_tool_results(messages, norm, results)

    return {"reply": "I ran into trouble putting that together. Could you try rephrasing?",
            "tool_results": collected}
