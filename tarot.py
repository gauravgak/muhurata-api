"""
tarot.py — a full 78-card deck and the draw logic behind /api/tarot.

The card meanings here are keywords, not the reading. The reading itself
is written by the LLM (see app.py), grounded in the exact cards drawn and
their orientation, in Naksha's voice — a confident classical reading, not
a disclaimer.

Deterministic when a seed is given (same question + seed -> same draw),
so a result can be cached and re-shown.
"""

import hashlib
import random

# ---------------------------------------------------------------- major arcana
MAJOR = [
    ("The Fool", "a leap of faith, new journey, openness, spontaneity",
     "recklessness, hesitation, a foolish risk"),
    ("The Magician", "will, skill, focus, making it happen",
     "manipulation, scattered effort, untapped talent"),
    ("The High Priestess", "intuition, the unseen, patience, inner knowing",
     "secrets withheld, ignoring the inner voice"),
    ("The Empress", "abundance, nurture, fertility, growth, the senses",
     "creative block, smothering, neglect of self"),
    ("The Emperor", "structure, authority, stability, a firm hand",
     "rigidity, control, domination, a shaky foundation"),
    ("The Hierophant", "tradition, guidance, belief, a mentor, commitment",
     "breaking with convention, a hollow institution"),
    ("The Lovers", "union, a real choice from the heart, alignment of values",
     "misalignment, avoidance, a choice made for the wrong reason"),
    ("The Chariot", "drive, willpower, a hard-won victory, control of opposing forces",
     "loss of direction, stalled momentum, forcing it"),
    ("Strength", "quiet courage, patience, mastery of impulse, compassion",
     "self-doubt, raw force, running on empty"),
    ("The Hermit", "withdrawal for insight, a guiding light, honest solitude",
     "isolation, avoidance, refusing counsel"),
    ("Wheel of Fortune", "a turning point, cycles, luck shifting, fate in motion",
     "resisting change, a run of bad breaks, feeling stuck"),
    ("Justice", "cause and effect, fairness, a clear decision, accountability",
     "unfairness, dishonesty, avoiding responsibility"),
    ("The Hanged Man", "a pause, surrender, seeing it another way, letting go",
     "stalling, martyrdom, a pointless sacrifice"),
    ("Death", "an ending that clears the way, transformation, release",
     "clinging to what is over, a slow, resisted change"),
    ("Temperance", "balance, patience, blending, the middle path, healing",
     "excess, impatience, working at cross-purposes"),
    ("The Devil", "attachment, a self-made trap, appetite, materialism",
     "breaking free, seeing the chain, reclaiming power"),
    ("The Tower", "a sudden shake-up, a false structure falling, revelation",
     "a disaster narrowly avoided, delaying the inevitable"),
    ("The Star", "hope, renewal, calm after hardship, faith restored",
     "discouragement, disconnection, faith running low"),
    ("The Moon", "uncertainty, the subconscious, illusion, a dream to trust or test",
     "confusion lifting, fear released, truth surfacing"),
    ("The Sun", "clarity, warmth, success, vitality, a plain yes",
     "a delayed yes, dimmed enthusiasm, over-optimism"),
    ("Judgement", "a reckoning, awakening, a clear call, rising to it",
     "self-doubt, ignoring the call, harsh self-judgement"),
    ("The World", "completion, wholeness, arrival, a cycle fulfilled",
     "an unfinished chapter, a goal just out of reach"),
]

# ---------------------------------------------------------------- minor arcana
SUIT_THEME = {
    "Wands": "drive, creativity, ambition, spirit",
    "Cups": "emotion, love, intuition, relationship",
    "Swords": "thought, truth, conflict, communication",
    "Pentacles": "work, money, the body, the material world",
}
RANK_MEANING = {
    "Ace": ("a new beginning, raw potential offered", "a false start, potential blocked"),
    "Two": ("a choice, balance, an early partnership", "imbalance, indecision, a split focus"),
    "Three": ("first results, collaboration, coming together", "a delay, a group out of step"),
    "Four": ("stability, rest, holding steady", "stagnation, clinging, restlessness"),
    "Five": ("friction, loss, a test of resolve", "recovery, moving past the setback"),
    "Six": ("progress, help given or received, a turn upward", "stalled progress, an uneven exchange"),
    "Seven": ("perseverance, assessment, standing your ground", "doubt, giving up too soon"),
    "Eight": ("momentum, focused effort, swift movement", "scattered effort, a slow grind"),
    "Nine": ("near completion, resilience, almost there", "overwhelm, defensiveness, one last hurdle"),
    "Ten": ("a full cycle, culmination, the weight of it all", "a burden set down, an ending overdue"),
    "Page": ("a message, curiosity, a beginner's spark", "immaturity, a stalled start, idle talk"),
    "Knight": ("action, pursuit, moving fast toward it", "haste or delay, a plan that overshoots"),
    "Queen": ("mastery from within, care, steady influence", "over-giving, guardedness, self-neglect"),
    "King": ("mastery outward, authority, command of the area", "rigidity, control, power misused"),
}


def _build_deck():
    deck = []
    for name, up, rev in MAJOR:
        deck.append({"name": name, "arcana": "major", "upright": up, "reversed": rev})
    for suit, theme in SUIT_THEME.items():
        for rank, (up, rev) in RANK_MEANING.items():
            deck.append({
                "name": f"{rank} of {suit}", "arcana": "minor", "suit": suit,
                "upright": f"{up} — in the realm of {theme}",
                "reversed": f"{rev} — in the realm of {theme}",
            })
    return deck


DECK = _build_deck()   # 78 cards

SPREADS = {
    "one":   ["The card"],
    "three": ["Past / what led here", "Present / where it stands", "Likely direction"],
    "cross": ["The heart of it", "What crosses it", "The root", "The recent past",
              "What may come", "The near future"],
}


def draw(spread: str = "three", seed: str | None = None) -> list:
    """Returns a list of {position, name, orientation, meaning, arcana}."""
    positions = SPREADS.get(spread, SPREADS["three"])
    rng = random.Random(
        int(hashlib.sha256(seed.encode()).hexdigest(), 16) if seed else None
    )
    picks = rng.sample(DECK, len(positions))
    out = []
    for pos, card in zip(positions, picks):
        reversed_ = rng.random() < 0.35
        out.append({
            "position": pos,
            "name": card["name"],
            "arcana": card["arcana"],
            "orientation": "reversed" if reversed_ else "upright",
            "meaning": card["reversed"] if reversed_ else card["upright"],
        })
    return out


def cards_block(cards: list) -> str:
    """The drawn cards as a plain block for the LLM to read from."""
    lines = []
    for c in cards:
        lines.append(f"- {c['position']}: {c['name']} ({c['orientation']}) — {c['meaning']}")
    return "\n".join(lines)


TAROT_SYSTEM = """You are Naksha reading tarot for someone at Muhurata. \
Warm, direct, grounded. Plain text only — no markdown, no headers, no \
bullet points, no asterisks.

Read the actual cards that were drawn, in their positions and \
orientations. Weave them into one flowing reading of 2-4 short \
paragraphs that speaks to the person's question.

Give a reading, not a disclaimer. If they ask about a relationship, a \
decision, timing, money, or "will this work out" — answer it through the \
cards: say what the spread leans toward and what to do about it. Speak \
with quiet confidence ("the spread favours...", "this reads as...", \
"the direction here is..."). Do NOT hedge with "tarot can't predict" or \
"this is just for reflection".

The one line you never cross: do not foretell death, serious illness, or \
disaster. If a card like Death or The Tower comes up, read it the \
classical way — an ending, a clearing, a shake-up that makes room — \
never as literal harm."""


def generate_reading(question: str, cards: list, name: str = "") -> str:
    """LLM reading of the drawn cards. Raises if the LLM is unreachable."""
    import naksha
    from naksha import _clean_reply

    if not naksha.configured():
        raise RuntimeError("LLM not configured")

    who = f" for {name}" if name else ""
    user_msg = (
        f"Question{who}: {question.strip() or '(a general reading)'}\n\n"
        f"Cards drawn:\n{cards_block(cards)}\n\n"
        "Write the reading now."
    )
    messages = [{"role": "user", "content": user_msg}]

    if naksha.LLM_PROVIDER == "openrouter":
        resp = naksha._post(
            "https://openrouter.ai/api/v1/chat/completions",
            {"Authorization": "Bearer " + naksha.OPENROUTER_KEY,
             "HTTP-Referer": "https://muhurata.com", "X-Title": "Muhurata"},
            {"model": naksha.OPENROUTER_MODEL, "max_tokens": 500,
             "messages": [{"role": "system", "content": TAROT_SYSTEM}] + messages},
        )
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "LLM error"))
        choices = resp.get("choices") or []
        text = (choices[0].get("message", {}).get("content") if choices else None) or ""
    else:
        resp = naksha._post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": naksha.ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
            {"model": naksha.ANTHROPIC_MODEL, "max_tokens": 500,
             "system": TAROT_SYSTEM, "messages": messages},
        )
        text = "".join(b.get("text", "") for b in resp.get("content", [])
                       if b.get("type") == "text")

    text = _clean_reply(text or "")
    if not text:
        raise RuntimeError("the model returned an empty response — try again")
    return text
