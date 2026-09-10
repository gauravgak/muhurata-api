"""
interpret.py — turns a computed chart into readable text.

Deliberately rule-based, not an LLM call. Three reasons:
  1. Instant. Sub-millisecond instead of 2-5 seconds.
  2. Free. Cost does not scale with users.
  3. Deterministic. The same chart always produces the same reading,
     so when a jyotishi corrects something, the fix is permanent.

Feed the astrologer's corrections back in as edits to these tables.
That is the whole strategy: their judgment becomes your rule set.
"""

# Plain, everyday words on purpose - a reading nobody can understand
# without a dictionary is not actually useful to them.
# Every entry is a pure list of adjectives / adjectival phrases, on
# purpose - these get dropped into "that makes you ___" and "you come
# across as ___" sentences, and a stray verb ("wants to be noticed",
# "builds things") breaks that grammar. Keep new entries adjective-only.
SIGN_TRAITS = {
    "Mesha": "direct, quick to start, impatient with delay",
    "Vrishabha": "steady, comfort-loving, slow to change but hard to move once set",
    "Mithuna": "talkative, curious, easily bored, drawn to variety",
    "Karka": "caring, sentimental, slow to trust new people",
    "Simha": "confident, warm, eager to be noticed and appreciated",
    "Kanya": "detail-focused, practical, uneasy until things are done right",
    "Tula": "fair-minded, easygoing on the surface, slow to decide",
    "Vrischika": "intense, private, all in once actually committed",
    "Dhanu": "big-picture, honest, freedom-loving",
    "Makara": "patient, hardworking, built for the long run",
    "Kumbha": "independent-minded, a little detached, drawn to the unusual",
    "Meena": "sensitive, imaginative, easily affected by the mood around you",
}

HOUSE_MEANING = {
    1: "how you come across to others", 2: "money, family and how you speak",
    3: "effort, siblings and courage", 4: "home, mother and peace of mind",
    5: "intelligence, children and good luck earned earlier",
    6: "daily work, debts and health",
    7: "partnership and the people you commit to",
    8: "sudden change, inheritance and things kept hidden",
    9: "luck, father and what you believe in",
    10: "career and how you're seen publicly",
    11: "income, friends and older siblings",
    12: "spending, distance from home and letting go",
}

DASHA_TONE = {
    "Sun": "confidence, visibility, your father, and where you stand",
    "Moon": "your state of mind, your mother, and how settled you feel",
    "Mars": "conflict, property, siblings, and quick decisive action",
    "Mercury": "conversations, business, learning, and negotiation",
    "Jupiter": "growth, teachers, children, and questions of right and wrong",
    "Venus": "relationships, comfort, beauty, and money that comes easily",
    "Saturn": "delay, discipline, hard work, and change that builds slowly",
    "Rahu": "ambition, foreign or unfamiliar things, and wanting more, fast",
    "Ketu": "losing interest, turning inward, and letting things go",
}

# What a planet's presence emphasises, independent of which house it sits
# in - combined with HOUSE_MEANING and SIGN_TRAITS at read time so four
# life areas can be generated from three small tables instead of a
# hand-written paragraph for every sign/planet/house combination.
PLANET_EMPHASIS = {
    "Sun": "confidence and being seen", "Moon": "feelings and mood",
    "Mars": "energy, drive, and sometimes friction", "Mercury": "talking things through and detail",
    "Jupiter": "growth, and things becoming bigger than planned",
    "Venus": "comfort, attraction, and what feels good to have",
    "Saturn": "delay, but the kind that leads to something lasting",
    "Rahu": "restlessness, wanting more before it's even clear why",
    "Ketu": "a pull to step back and let go of it",
}


# Full, plain-English personality reads per sign - not adjective lists.
# Each has a real strength and a real, specific thing to watch out for,
# the way an actual person would describe someone, not a chart printout.
SIGN_PROFILE = {
    "Mesha": {
        "desc": "You're direct and quick to act — when you want something, you go for it rather than waiting around for the right moment.",
        "strength": "Your drive gets things moving when everyone else is still deciding.",
        "watch": "You can jump in before thinking it through, so it helps to pause before the big decisions specifically.",
    },
    "Vrishabha": {
        "desc": "You're steady and value comfort — once you're settled into something, you don't like being rushed out of it.",
        "strength": "People can count on you to actually stick with things.",
        "watch": "You can be slow to let go of what isn't working, even after it's clearly time to.",
    },
    "Mithuna": {
        "desc": "You're curious and quick with words — you get bored fast and need variety to stay genuinely interested.",
        "strength": "You pick up new things quickly and talk your way through most problems.",
        "watch": "You can start more than you finish — worth picking one thing and actually seeing it through.",
    },
    "Karka": {
        "desc": "You're caring and protective of people close to you, but you take real time before you trust someone new.",
        "strength": "You remember what matters to people and consistently show up for them.",
        "watch": "You can hold onto old hurts longer than they deserve — some things are worth actually letting go.",
    },
    "Simha": {
        "desc": "You're confident and warm, and you want your effort to actually be seen, not just quietly done.",
        "strength": "You lead naturally, and people notice your energy without you trying too hard.",
        "watch": "You can take it hard when you're not recognised — try not to measure your worth by applause.",
    },
    "Kanya": {
        "desc": "You're practical and detail-focused — you notice what's wrong before you notice what's right, and you like fixing things properly.",
        "strength": "People trust you specifically to get the details right when it matters.",
        "watch": "You can be harder on yourself than the situation calls for. Not everything needs to be perfect.",
    },
    "Tula": {
        "desc": "You're fair-minded and want harmony — you weigh both sides carefully, sometimes for longer than the decision actually needs.",
        "strength": "People trust your judgement because you genuinely consider their side too.",
        "watch": "You can delay decisions trying to keep everyone happy, when sometimes you just need to choose.",
    },
    "Vrischika": {
        "desc": "You're intense and private — you don't open up easily, but once you're committed to something or someone, you go all in.",
        "strength": "Your loyalty and focus run deep once someone has actually earned your trust.",
        "watch": "You can shut people out when you're hurt instead of talking it through — worth catching yourself doing this.",
    },
    "Dhanu": {
        "desc": "You think in big picture terms and value your freedom — you need real room to move and a genuine reason before you commit.",
        "strength": "Your honesty and optimism make people want to follow where you're headed.",
        "watch": "You can promise more than you follow through on, or leave before finishing what you started.",
    },
    "Makara": {
        "desc": "You're patient and hardworking — you build things slowly, the kind of way that actually lasts.",
        "strength": "You get results because you don't quit when things get slow or difficult.",
        "watch": "You can put off enjoying life until 'later' — later doesn't always come, so let yourself rest sometimes.",
    },
    "Kumbha": {
        "desc": "You think independently and don't mind being the odd one out — conventional answers rarely satisfy you.",
        "strength": "You see angles other people miss, and you're not afraid to say so.",
        "watch": "You can come across as detached even when you care — it helps to actually say what you feel sometimes.",
    },
    "Meena": {
        "desc": "You're sensitive and imaginative, and you tend to absorb the mood of whoever and whatever is around you.",
        "strength": "Your empathy makes the people around you feel genuinely understood.",
        "watch": "You can take on other people's stress as if it's your own — it's alright to put some distance there.",
    },
}

from chart_engine import SIGNS

SIGN_INDEX = {s: i for i, s in enumerate(SIGNS)}


def _sign_in_house(asc_sign: str, house: int) -> str:
    return SIGNS[(SIGN_INDEX[asc_sign] + house - 1) % 12]


# Simplified, not a full classical strength assessment (that also needs
# exaltation, own-sign, aspects, and combustion, none of which are in
# scope here) - but a defensible, honest first cut. Jupiter and Venus
# ease a house; Saturn, Mars, Rahu and Ketu make it work harder; the
# Sun leans slightly toward the demanding side. This is what actually
# answers "is this good or does this need effort", which a placement
# list on its own never does.
PLANET_NATURE = {
    "Jupiter": "supportive", "Venus": "supportive", "Moon": "supportive",
    "Mercury": "supportive",
    "Sun": "demanding", "Mars": "demanding", "Saturn": "demanding",
    "Rahu": "demanding", "Ketu": "demanding",
}

# Domain-specific, tone-specific takeaways. Four domains, four tones
# each (supportive / demanding / mixed / quiet-no-occupant), all phrased
# as an actual answer to "how does this affect me", not a placement list.
DOMAIN_TONE = {
    "money": {
        "supportive": "Money tends to come without a constant fight for it, and family support is often part of the picture. Save with a plan anyway — ease is not the same as unlimited.",
        "demanding": "Money takes real, deliberate effort here — very little about your finances is likely to feel automatic. A budget matters more for you than it does for most people.",
        "mixed": "Money moves in waves for you — some stretches easy, others tight. Building a buffer in the easy periods is the practical move, not optional.",
    },
    "health": {
        "supportive": "Health and day-to-day work tend to go smoothly without constant intervention. Don't let that ease turn into neglect — check in on yourself anyway.",
        "demanding": "Health and work both ask for real, ongoing attention here — this is not the area to run on autopilot. Regular check-ins pay off more for you than for most.",
        "mixed": "Some parts of health and work come easily, others need real discipline. Notice which is which, rather than assuming the whole area behaves the same way.",
    },
    "relationships": {
        "supportive": "Partnership tends to come more naturally to you than to most people — trust is usually returned in kind, and closeness doesn't take endless convincing.",
        "demanding": "Partnership asks more of you here than an average chart — trust and closeness take real, deliberate work, not just time passing.",
        "mixed": "Relationships give you both ease and friction depending on the person and the moment — not a fixed pattern either way, so don't assume the last relationship predicts the next.",
    },
    "career": {
        "supportive": "Career is one of your stronger areas — effort here tends to actually get seen and rewarded, more reliably than in most charts.",
        "demanding": "Career takes real, sustained effort for you — recognition rarely arrives on its own, and you'll likely need to make your work visible yourself rather than wait to be noticed.",
        "mixed": "Career has both easy stretches and real friction — outcomes here depend more on timing and effort than on things simply falling into place.",
    },
}

DOMAIN_LABEL = {
    "money": "house of money and family", "health": "house of work and health",
    "relationships": "house of partnership", "career": "house of career and standing",
}

# When no planet occupies the house — the common case for most houses in
# most charts. Framed as an actual reading ("shaped by the sign and its
# ruler"), never as a lack. Each string is a complete sentence and names
# the sign's ruler so two charts get genuinely different text.
DOMAIN_QUIET = {
    "money": "Money and family aren't driven hard by any one planet here — "
             "{sign} sets the tone, and its ruler {ruler}, by the house it "
             "occupies in your chart, is what actually shapes how income comes "
             "in and how much of a backstop family turns out to be.",
    "health": "Your daily work and health aren't dominated by a single planet "
              "pulling at them; {sign} colours how the routine feels, and its "
              "ruler {ruler} carries the real influence — so this area tends to "
              "hold together on its own as long as you don't run it into the "
              "ground.",
    "relationships": "Partnership here isn't under loud, forcing pressure. It "
                     "takes its temperament from {sign}, and the real story is "
                     "written by where that sign's ruler {ruler} sits — that "
                     "placement says far more about your close relationships "
                     "than this house being unoccupied does.",
    "career": "Your standing builds steadily rather than being pushed by a "
              "planet parked here: {sign} gives your public life its character, "
              "and its ruler {ruler}, by the house it falls in, shows where "
              "your work and reputation actually gain ground.",
}


def _life_area(chart, house: int, domain: str) -> str:
    """Composes a reading for one house from what actually occupies it,
    and — unlike a placement list — actually says whether that reads as
    generally supportive or generally demanding for this domain. Two
    charts with different placements get genuinely different text and
    a genuinely different verdict, not just different planet names."""
    asc_sign = chart["ascendant"]["sign"]
    sign = _sign_in_house(asc_sign, house)
    occupants = [p["name"] for p in chart["positions"] if p["house"] == house]
    profile = SIGN_PROFILE.get(sign)
    trait = profile["desc"] if profile else f"takes its cue from {sign}."
    domain_opener = {
        "money": "When it comes to money and family,",
        "health": "When it comes to your daily work and health,",
        "relationships": "When it comes to partnership,",
        "career": "When it comes to your career,",
    }[domain]
    # lowercase the profile's "You're..." opener so it reads as one sentence
    # after the domain framing, instead of two disconnected clauses
    trait_lc = trait[0].lower() + trait[1:] if trait else trait
    base = f"{domain_opener} {trait_lc}"

    if not occupants:
        from matching import SIGN_LORD
        ruler = SIGN_LORD.get(sign, "its ruler")
        return base + " " + DOMAIN_QUIET[domain].format(sign=sign, ruler=ruler)

    natures = [PLANET_NATURE.get(p, "demanding") for p in occupants]
    n_support = natures.count("supportive")
    n_demand = natures.count("demanding")
    if n_demand == 0:
        tone = "supportive"
    elif n_support == 0:
        tone = "demanding"
    else:
        tone = "mixed"

    parts = [f"{p} ({PLANET_EMPHASIS.get(p, 'its own emphasis')})" for p in occupants]
    if len(parts) == 1:
        occupant_line = f" {parts[0]} is placed here."
    elif len(parts) == 2:
        occupant_line = f" {parts[0]} and {parts[1]} are both placed here."
    else:
        occupant_line = f" {', '.join(parts[:-1])}, and {parts[-1]} all land here."

    verdict = DOMAIN_TONE[domain][tone]
    return f"{base}{occupant_line} {verdict}"


DEVATA_NOTE = {
    "Surya / Shiva": "Sunday, at sunrise, facing east",
    "Parvati / Gauri": "Monday, at moonrise",
    "Kartikeya / Hanuman": "Tuesday, at dusk",
    "Vishnu": "Wednesday, midday",
    "Dakshinamurthy": "Thursday, morning",
    "Lakshmi": "Friday, at dusk",
    "Shani / Hanuman": "Saturday, at dusk",
    "Durga": "Tuesday or Friday, at night",
    "Ganesha": "any day, before beginning something",
}

# Practice, not "remedy" — nothing here presumes something is wrong.
PRACTICE = {
    "Sun": "Offer water to the sun at sunrise. Twelve days, unbroken.",
    "Moon": "Sit with the moon visible on a Monday evening. No phone.",
    "Mars": "Recite the Hanuman Chalisa on Tuesday, once, aloud.",
    "Mercury": "Give something green away on Wednesday. Fruit will do.",
    "Jupiter": "Light a lamp on Thursday morning before you eat anything.",
    "Venus": "Offer something white on Friday at dusk. Rice, cloth, sweets.",
    "Saturn": "Feed someone on Saturday. A person, not a ritual object.",
    "Rahu": "Sit in silence for ten minutes at dusk. Same time, nine days.",
    "Ketu": "Give away one thing you have kept without using.",
}


def _p(chart, name):
    return next(p for p in chart["positions"] if p["name"] == name)


def reading(chart, running, devata, first_name=""):
    """Returns the sections the WhatsApp message is assembled from."""
    asc = chart["ascendant"]
    moon = _p(chart, "Moon")
    md, ad = running["mahadasha"], running["antardasha"]
    ak = chart["atmakaraka"]

    lagna_lord = None
    from matching import SIGN_LORD
    lagna_lord = SIGN_LORD.get(asc["sign"])
    lord_house = next((p["house"] for p in chart["positions"] if p["name"] == lagna_lord), None)

    asc_profile = SIGN_PROFILE.get(asc["sign"])
    if asc_profile:
        lagna = f"{asc_profile['desc']} {asc_profile['strength']} {asc_profile['watch']}"
        if lord_house:
            lagna += (
                f" A lot of this actually shows up through {HOUSE_MEANING.get(lord_house, '')} "
                f"— that's the area {lagna_lord}, which rules your nature, sits in."
            )
    else:
        lagna = f"Your lagna is {asc['sign']}, in {asc['nakshatra']}."

    money = _life_area(chart, 2, "money")
    health = _life_area(chart, 6, "health")
    relationships = _life_area(chart, 7, "relationships")
    career = _life_area(chart, 10, "career")

    moon_profile = SIGN_PROFILE.get(moon["sign"])
    if moon_profile:
        mind = (
            f"Emotionally, {moon_profile['desc'][0].lower()}{moon_profile['desc'][1:]} "
            f"Your attention keeps returning to {HOUSE_MEANING[moon['house']]} — "
            f"that's just where your Moon happens to sit."
        )
    else:
        mind = f"The Moon sits in {moon['sign']}, house {moon['house']}."

    if md == ad:
        period = (
            f"You are in {md} mahadasha, and its own {ad} antardasha — "
            f"the opening stretch of the period, where its themes run undiluted. "
            f"{md} brings up {DASHA_TONE.get(md, 'its own themes')}. "
            f"This sub-period runs until {running['antardasha_ends']}, "
            f"and the larger {md} period until {running['mahadasha_ends']}."
        )
    else:
        period = (
            f"You are in {md} mahadasha, {ad} antardasha. "
            f"{md} periods bring up {DASHA_TONE.get(md, 'their own themes')}. "
            f"Inside that, {ad} colours it with {DASHA_TONE.get(ad, 'its own weight')}. "
            f"This sub-period runs until {running['antardasha_ends']}, "
            f"and the larger {md} period until {running['mahadasha_ends']}."
        )

    dev = (
        f"Your Ishta Devata is {devata['devata']}. "
        f"It comes from {ak['planet']} as your atmakaraka, and the twelfth "
        f"sign from its navamsa position, which is {devata['karakamsa_12th']}. "
        f"That is the classical route — it has nothing to do with your sun sign. "
        f"Best approached on {DEVATA_NOTE.get(devata['devata'], 'any auspicious day')}."
    )

    practice_lord = ad if ad in PRACTICE else md
    prac = (
        f"One practice for this period: {PRACTICE.get(practice_lord, PRACTICE['Jupiter'])} "
        f"It is chosen for {practice_lord}, which is what is currently running."
    )

    lagna_short = SIGN_TRAITS.get(asc["sign"], "hard to sum up in one line")
    summary = (
        f"In short: you come across as {lagna_short}. "
        f"You're currently in a {md} period, which tends to bring "
        f"{DASHA_TONE.get(md, 'its own themes')}. "
        f"Your guiding figure is {devata['devata']}. "
        "The sections below go through money, health, relationships and "
        "career in more detail, one at a time."
    )

    return {
        "greeting": f"{first_name}, here is your chart." if first_name else "Here is your chart.",
        "summary": summary,
        "lagna": lagna,
        "mind": mind,
        "money": money,
        "health": health,
        "relationships": relationships,
        "career": career,
        "period": period,
        "devata": dev,
        "practice": prac,
    }


def whatsapp_text(sections):
    return (
        f"*{sections['greeting']}*\n\n"
        f"{sections['summary']}\n\n"
        f"*Your nature*\n{sections['lagna']}\n\n"
        f"*Your mind*\n{sections['mind']}\n\n"
        f"*Money and family*\n{sections['money']}\n\n"
        f"*Work and health*\n{sections['health']}\n\n"
        f"*Relationships*\n{sections['relationships']}\n\n"
        f"*Career*\n{sections['career']}\n\n"
        f"*The period you are in*\n{sections['period']}\n\n"
        f"*Your Ishta Devata*\n{sections['devata']}\n\n"
        f"*One practice*\n{sections['practice']}\n\n"
        "_Muhurata — muhurata.com_"
    )
