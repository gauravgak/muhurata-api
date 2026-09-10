# Muhurata API

Birth details in, full reading out. No LLM in the path, so a cache miss
answers in single-digit milliseconds and costs nothing per request.

## Run locally

    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000/docs to poke at it.

## Files

- `chart_engine.py` — sidereal positions, navamsa, vimshottari, atmakaraka,
  ishta devata. Pure maths, deterministic, no I/O.
- `interpret.py` — the tables that turn a chart into sentences. **This is the
  file your astrologer edits.** Their corrections land here and become permanent.
- `app.py` — HTTP layer, geocoding, SQLite cache, lead storage.

## Endpoints

    POST /api/reading    birth details -> chart + reading + WhatsApp text
    GET  /api/leads      unsent leads, for your WhatsApp sender
    GET  /api/health

## Deploy

Railway or Render, both have free tiers and take a Python repo directly.

    web: uvicorn app:app --host 0.0.0.0 --port $PORT

Point `api.muhurata.com` at it, and set the same host in `index.html`
where `API` is defined.

## Before you take real users

1. **Swiss Ephemeris licence.** AGPL or commercial. If you are not
   open-sourcing, buy the commercial licence from Astrodienst before revenue.
2. **Geocoding.** The bundled city list covers ~110 Indian cities. Anything
   else 422s. Wire Nominatim or Google Geocoding into `geocode()` and cache
   every result — you will see the same towns repeatedly.
3. **Timezones.** Everything assumes IST at +5.5. Births before 1955 in India
   used Bombay and Calcutta local time. Use the `tz` database, not a constant,
   or those charts will be wrong by up to 40 minutes — enough to move the lagna.
4. **SQLite.** Fine to a few thousand users. Move to Postgres before you
   run more than one process.
5. **Rate limit `/api/reading`.** It is unauthenticated and writes a lead row
   on every call.
