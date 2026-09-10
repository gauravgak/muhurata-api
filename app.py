"""
app.py — Muhurata reading service.

    POST /api/reading   birth details in, full reading out, cached
    GET  /api/health

Latency budget: chart maths ~3ms, interpretation ~0.1ms, so a cache miss
answers in single-digit milliseconds. A cache hit is a dict lookup.
Nothing here calls an LLM, so nothing here can be slow or expensive.

Run:  uvicorn app:app --reload --port 8000
"""

import asyncio
import json
import os
import db as dbmod
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

import auth
from ratelimit import limiter

from chart_engine import compute_chart, running_dasha, ishta_devata, cache_key
from interpret import reading, whatsapp_text
import whatsapp as wa
from chart_svg import north_indian, south_indian, navamsa_north
from matching import match as guna_match
from horoscope import horoscope as build_horoscope
import naksha
import predictions as preds
import tarot as tarot_mod
import divisionals, kp as kp_engine, ashtakvarga, avakhada as avakhada_mod
from glyphs import all_glyphs_svg_defs
from pdf_report import build_pdf, LEGACY_SECTION_ORDER
from fastapi.responses import Response
import secrets
from fastapi import Request
from fastapi.responses import PlainTextResponse


# ---------------------------------------------------------------- geocoding
# Bundled so the common case never makes a network call. Anything not here
# falls through to a geocoder — wire GEOCODER_URL in prod (Nominatim is free,
# Google is more accurate for Indian localities).
CITIES = {
    "mumbai": (19.0760, 72.8777), "bombay": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090), "new delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867), "chennai": (13.0827, 80.2707),
    "madras": (13.0827, 80.2707), "kolkata": (22.5726, 88.3639),
    "calcutta": (22.5726, 88.3639), "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714), "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462), "kanpur": (26.4499, 80.3319),
    "nagpur": (21.1458, 79.0882), "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126), "patna": (25.5941, 85.1376),
    "vadodara": (22.3072, 73.1812), "surat": (21.1702, 72.8311),
    "ludhiana": (30.9010, 75.8573), "agra": (27.1767, 78.0081),
    "nashik": (19.9975, 73.7898), "varanasi": (25.3176, 82.9739),
    "amritsar": (31.6340, 74.8723), "chandigarh": (30.7333, 76.7794),
    "coimbatore": (11.0168, 76.9558), "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673), "thiruvananthapuram": (8.5241, 76.9366),
    "trivandrum": (8.5241, 76.9366), "guwahati": (26.1445, 91.7362),
    "bhubaneswar": (20.2961, 85.8245), "ranchi": (23.3441, 85.3096),
    "raipur": (21.2514, 81.6296), "dehradun": (30.3165, 78.0322),
    "jodhpur": (26.2389, 73.0243), "udaipur": (24.5854, 73.7125),
    "gwalior": (26.2183, 78.1828), "jabalpur": (23.1815, 79.9864),
    "vijayawada": (16.5062, 80.6480), "visakhapatnam": (17.6868, 83.2185),
    "madurai": (9.9252, 78.1198), "tiruchirappalli": (10.7905, 78.7047),
    "mysore": (12.2958, 76.6394), "mysuru": (12.2958, 76.6394),
    "mangalore": (12.9141, 74.8560), "hubli": (15.3647, 75.1240),
    "aurangabad": (19.8762, 75.3433), "solapur": (17.6599, 75.9064),
    "kolhapur": (16.7050, 74.2433), "thane": (19.2183, 72.9781),
    "navi mumbai": (19.0330, 73.0297), "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266), "noida": (28.5355, 77.3910),
    "faridabad": (28.4089, 77.3178), "ghaziabad": (28.6692, 77.4538),
    "meerut": (28.9845, 77.7064), "allahabad": (25.4358, 81.8463),
    "prayagraj": (25.4358, 81.8463), "srinagar": (34.0837, 74.7973),
    "jammu": (32.7266, 74.8570), "shimla": (31.1048, 77.1734),
    "panaji": (15.4909, 73.8278), "goa": (15.2993, 74.1240),
    "puducherry": (11.9416, 79.8083), "pondicherry": (11.9416, 79.8083),
    "salem": (11.6643, 78.1460), "warangal": (17.9689, 79.5941),
    "guntur": (16.3067, 80.4365), "nellore": (14.4426, 79.9865),
    "tirupati": (13.6288, 79.4192), "kozhikode": (11.2588, 75.7804),
    "thrissur": (10.5276, 76.2144), "kollam": (8.8932, 76.6141),
    "siliguri": (26.7271, 88.3953), "asansol": (23.6739, 86.9524),
    "cuttack": (20.4625, 85.8830), "rourkela": (22.2604, 84.8536),
    "jamshedpur": (22.8046, 86.2029), "dhanbad": (23.7957, 86.4304),
    "bhagalpur": (25.2425, 86.9842), "muzaffarpur": (26.1197, 85.3910),
    "gorakhpur": (26.7606, 83.3732), "bareilly": (28.3670, 79.4304),
    "aligarh": (27.8974, 78.0880), "moradabad": (28.8386, 78.7733),
    "jhansi": (25.4484, 78.5685), "ujjain": (23.1765, 75.7885),
    "ajmer": (26.4499, 74.6399), "bikaner": (28.0229, 73.3119),
    "kota": (25.2138, 75.8648), "rajkot": (22.3039, 70.8022),
    "bhavnagar": (21.7645, 72.1519), "jamnagar": (22.4707, 70.0577),
    "amravati": (20.9374, 77.7796), "akola": (20.7002, 77.0082),
    "belgaum": (15.8497, 74.4977), "davangere": (14.4644, 75.9218),
    "tirunelveli": (8.7139, 77.7567), "erode": (11.3410, 77.7172),
    "vellore": (12.9165, 79.1325), "shillong": (25.5788, 91.8933),
    "imphal": (24.8170, 93.9368), "agartala": (23.8315, 91.2868),
    "aizawl": (23.7271, 92.7176), "itanagar": (27.0844, 93.6053),
    "kohima": (25.6751, 94.1086), "gangtok": (27.3389, 88.6065),
    "hansi": (29.1002, 75.9631), "jind": (29.3159, 76.3140),
    "narnaul": (28.0438, 76.1092), "bhiwadi": (28.2100, 76.8600),
    "rewari": (28.1970, 76.6198), "tohana": (29.7020, 75.9010),
    "safidon": (29.4167, 76.6667), "kaithal": (29.7959, 76.3999),
    "fatehabad": (29.5153, 75.4552), "sirsa city": (29.5321, 75.0318),
    "dabwali": (29.9330, 74.7370), "ellenabad": (29.4530, 74.6580),
    "narwana": (29.5928, 76.1122), "gohana": (29.1359, 76.6939),
    "kharkhoda": (28.8801, 76.9276), "bahadurgarh": (28.6939, 76.9212),
    "jhajjar": (28.6060, 76.6560), "charkhi dadri": (28.5921, 76.2653),
    "loharu": (28.4333, 75.8000), "mahendragarh": (28.2757, 76.1487),
    "palwal": (28.1447, 77.3260), "hodal": (27.8938, 77.3712),
    "ballabgarh": (28.3364, 77.3252), "sohna": (28.2489, 77.0653),
    "nuh": (28.1109, 77.0026), "pehowa": (29.9789, 76.5764),
    "shahabad": (30.1670, 76.8690), "radaur": (30.0450, 77.1610),
    "jagadhri": (30.1670, 77.3010), "kalka": (30.8380, 76.9358),
    "pinjore": (30.7980, 76.9160), "naraingarh": (30.4600, 77.1080),
    "ratia": (29.7080, 75.5760), "adampur": (29.1490, 75.9060),
    "barwala": (29.3660, 75.9130), "uklana": (29.4890, 75.9200),
    "meham": (28.9880, 76.1350), "beri": (28.7000, 76.5750),
    "kosli": (28.4210, 76.4610), "bawal": (28.0730, 76.5850),
    "kanina": (28.2280, 76.3320), "ateli": (28.0210, 76.3900),
    "julana": (29.0930, 76.5410), "uchana": (29.4600, 76.3070),
    "assandh": (29.5230, 76.8420), "nilokheri": (29.8330, 76.9060),
    "gharaunda": (29.5290, 76.9600), "taraori": (29.7180, 76.9500),
    "indri": (29.8930, 77.0700), "babain": (30.0620, 76.9970),
    "ladwa": (30.0170, 77.0430), "thanesar": (29.9690, 76.8290),
    "yamuna nagar": (30.1290, 77.2674), "chhachhrauli": (30.3320, 77.3410),
    "pundri": (29.7660, 76.5580), "siwani": (28.9380, 75.5990),
    "bhawani khera": (29.0100, 75.6980), "ganaur": (29.2760, 77.0110),
    "samalkha": (29.2400, 76.8850), "israna": (29.2530, 76.8300),
    "kalanaur": (28.9330, 76.3670), "sampla": (28.8200, 76.7810),
    "makrana": (27.0430, 74.7280), "degana": (27.3910, 74.3060),
    "nagaur": (27.2020, 73.7340), "didwana": (27.4020, 74.5760),
    "sikar city": (27.6094, 75.1399), "fatehpur shekhawati": (27.9920, 74.9540),
    "nawalgarh": (27.8500, 75.2740), "jhunjhunu": (28.1290, 75.3980),
    "churu": (28.3020, 74.9660), "ratangarh": (28.0850, 74.6150),
    "sujangarh": (27.7040, 74.4670), "sardarshahar": (28.4390, 74.4870),
    "hanumangarh": (29.5810, 74.3290), "suratgarh": (29.3170, 73.9010),
    "raisinghnagar": (29.5330, 73.4470), "anupgarh": (29.1920, 73.2080),
    "bikaner city": (28.0229, 73.3119), "nokha": (27.5730, 73.4160),
    "khajuwala": (28.9700, 73.3200), "pilibanga": (29.4400, 74.1030),
    "sangaria": (29.8330, 74.4630),

    "hisar": (29.1492, 75.7217), "karnal": (29.6857, 76.9905),
    "panipat": (29.3909, 76.9635), "rohtak": (28.8955, 76.6066),
    "sonipat": (28.9931, 77.0151), "ambala": (30.3752, 76.7821),
    "yamunanagar": (30.1290, 77.2674), "sirsa": (29.5321, 75.0318),
    "bhiwani": (28.7975, 76.1322), "rewari": (28.1970, 76.6198),
    "kurukshetra": (29.9695, 76.8783), "patiala": (30.3398, 76.3869),
    "bathinda": (30.2110, 74.9455), "mohali": (30.7046, 76.7179),
    "pathankot": (32.2746, 75.6521), "hoshiarpur": (31.5326, 75.9142),
    "moga": (30.8165, 75.1711), "firozpur": (30.9331, 74.6225),
    "alwar": (27.5530, 76.6346), "bharatpur": (27.2173, 77.4901),
    "sikar": (27.6094, 75.1399), "pali": (25.7711, 73.3234),
    "sri ganganagar": (29.9038, 73.8772), "bhilwara": (25.3407, 74.6313),
    "tonk": (26.1664, 75.7885), "firozabad": (27.1591, 78.3958),
    "mathura": (27.4924, 77.6737), "muzaffarnagar": (29.4727, 77.7085),
    "saharanpur": (29.9640, 77.5460), "shahjahanpur": (27.8815, 79.9092),
    "rampur": (28.8152, 79.0250), "sitapur": (27.5619, 80.6822),
    "etawah": (26.7855, 79.0154), "mirzapur": (25.1461, 82.5646),
    "ayodhya": (26.7922, 82.1998), "faizabad": (26.7922, 82.1998),
    "basti": (26.8148, 82.7275), "hapur": (28.7300, 77.7800),
    "bulandshahr": (28.4041, 77.8498), "orai": (25.9895, 79.4508),
    "banda": (25.4762, 80.3352), "fatehpur": (25.9308, 80.8134),
    "raebareli": (26.2309, 81.2338), "unnao": (26.5464, 80.4879),
    "hardoi": (27.3990, 80.1310), "deoria": (26.5024, 83.7791),
    "azamgarh": (26.0685, 83.1836), "ballia": (25.7600, 84.1500),
    "jaunpur": (25.7479, 82.6837), "pratapgarh": (25.8971, 81.9407),
    "ratlam": (23.3315, 75.0367), "sagar": (23.8388, 78.7378),
    "satna": (24.5854, 80.8322), "rewa": (24.5362, 81.3037),
    "dewas": (22.9676, 76.0534), "khandwa": (21.8258, 76.3529),
    "chhindwara": (22.0574, 78.9382), "vidisha": (23.5251, 77.8081),
    "shivpuri": (25.4231, 77.6584), "damoh": (23.8318, 79.4421),
    "singrauli": (24.1991, 82.6747), "burhanpur": (21.3009, 76.2291),
    "jalgaon": (21.0077, 75.5626), "latur": (18.4088, 76.5604),
    "dhule": (20.9042, 74.7749), "ahmednagar": (19.0952, 74.7496),
    "chandrapur": (19.9615, 79.2961), "parbhani": (19.2704, 76.7601),
    "ichalkaranji": (16.6910, 74.4600), "jalna": (19.8347, 75.8816),
    "satara": (17.6805, 74.0183), "beed": (18.9894, 75.7601),
    "osmanabad": (18.1860, 76.0419), "wardha": (20.7453, 78.6022),
    "yavatmal": (20.3888, 78.1204), "nanded": (19.1383, 77.3210),
    "bhusawal": (21.0436, 75.7851), "bharuch": (21.7051, 72.9959),
    "anand": (22.5645, 72.9289), "nadiad": (22.6939, 72.8615),
    "morbi": (22.8173, 70.8378), "mehsana": (23.5880, 72.3693),
    "palanpur": (24.1722, 72.4383), "gandhinagar": (23.2156, 72.6369),
    "junagadh": (21.5222, 70.4579), "porbandar": (21.6417, 69.6293),
    "veraval": (20.9159, 70.3629), "valsad": (20.5992, 72.9342),
    "navsari": (20.9467, 72.9520), "godhra": (22.7788, 73.6143),
    "purnia": (25.7771, 87.4753), "darbhanga": (26.1542, 85.8918),
    "begusarai": (25.4182, 86.1272), "katihar": (25.5541, 87.5719),
    "munger": (25.3747, 86.4735), "chapra": (25.7810, 84.7500),
    "sasaram": (24.9500, 84.0167), "hajipur": (25.6864, 85.2094),
    "motihari": (26.6485, 84.9153), "bettiah": (26.8022, 84.5019),
    "arrah": (25.5541, 84.6636), "buxar": (25.5644, 83.9773),
    "samastipur": (25.8626, 85.7797), "malda": (25.0108, 88.1414),
    "baharampur": (24.0967, 88.2497), "kharagpur": (22.3302, 87.3237),
    "haldia": (22.0257, 88.0583), "krishnanagar": (23.4058, 88.5023),
    "bardhaman": (23.2324, 87.8615), "habra": (22.8404, 88.6631),
    "jalpaiguri": (26.5167, 88.7333), "alipurduar": (26.4842, 89.5273),
    "berhampur": (19.3149, 84.7941), "sambalpur": (21.4669, 83.9756),
    "balasore": (21.4942, 86.9317), "puri": (19.8135, 85.8312),
    "baripada": (21.9347, 86.7188), "rayagada": (19.1711, 83.4159),
    "bhadrak": (21.0574, 86.5148), "thoothukudi": (8.7642, 78.1348),
    "dindigul": (10.3624, 77.9695), "thanjavur": (10.7870, 79.1378),
    "karur": (10.9601, 78.0766), "sivakasi": (9.4491, 77.7972),
    "kanchipuram": (12.8342, 79.7036), "cuddalore": (11.7480, 79.7714),
    "nagercoil": (8.1790, 77.4338), "ooty": (11.4064, 76.6932),
    "udhagamandalam": (11.4064, 76.6932), "hosur": (12.7409, 77.8253),
    "shimoga": (13.9299, 75.5681), "shivamogga": (13.9299, 75.5681),
    "tumkur": (13.3379, 77.1173), "raichur": (16.2076, 77.3463),
    "bidar": (17.9104, 77.5199), "bijapur": (16.8302, 75.7100),
    "vijayapura": (16.8302, 75.7100), "gulbarga": (17.3297, 76.8343),
    "kalaburagi": (17.3297, 76.8343), "chikmagalur": (13.3161, 75.7720),
    "udupi": (13.3409, 74.7421), "bagalkot": (16.1691, 75.6636),
    "hassan": (13.0072, 76.1004), "alappuzha": (9.4981, 76.3388),
    "palakkad": (10.7867, 76.6548), "kottayam": (9.5916, 76.5222),
    "kannur": (11.8745, 75.3704), "malappuram": (11.0510, 76.0711),
    "idukki": (9.8515, 76.9698), "kadapa": (14.4674, 78.8241),
    "anantapur": (14.6819, 77.6006), "kurnool": (15.8281, 78.0373),
    "rajahmundry": (17.0005, 81.8040), "kakinada": (16.9891, 82.2475),
    "eluru": (16.7107, 81.0952), "ongole": (15.5057, 80.0499),
    "karimnagar": (18.4386, 79.1288), "nizamabad": (18.6725, 78.0941),
    "khammam": (17.2473, 80.1514), "adilabad": (19.6640, 78.5320),
    "mahbubnagar": (16.7375, 77.9873), "bilaspur": (22.0797, 82.1409),
    "durg": (21.1904, 81.2849), "bhilai": (21.2094, 81.4285),
    "korba": (22.3595, 82.7501), "raigarh": (21.8974, 83.3950),
    "jagdalpur": (19.0748, 82.0198), "deoghar": (24.4823, 86.6961),
    "hazaribagh": (23.9925, 85.3637), "giridih": (24.1913, 86.3097),
    "bokaro": (23.6693, 86.1511), "ramgarh": (23.6307, 85.5121),
    "dibrugarh": (27.4728, 94.9120), "silchar": (24.8333, 92.7789),
    "jorhat": (26.7509, 94.2037), "nagaon": (26.3509, 92.6840),
    "tezpur": (26.6338, 92.8000), "tinsukia": (27.4922, 95.3597),
    "solan": (30.9045, 77.0967), "mandi": (31.7084, 76.9319),
    "kullu": (31.9576, 77.1095), "dharamshala": (32.2190, 76.3234),
    "haldwani": (29.2183, 79.5130), "rudrapur": (28.9875, 79.4054),
    "roorkee": (29.8543, 77.8880), "haridwar": (29.9457, 78.1642),
    "anantnag": (33.7311, 75.1487), "baramulla": (34.2096, 74.3436),

}


def geocode(place: str):
    """Returns (lat, lon, resolved_name). Bundled lookup first, then fallback."""
    key = place.strip().lower()
    if key in CITIES:
        return (*CITIES[key], place.strip())

    # try the first comma-separated token, e.g. "Kandivali, Mumbai" -> "mumbai"
    for part in reversed([p.strip().lower() for p in place.split(",")]):
        if part in CITIES:
            return (*CITIES[part], place.strip())
        for city in CITIES:
            if city in part:
                return (*CITIES[city], place.strip())

    url = os.environ.get("GEOCODER_URL")
    if url:
        # TODO: plug in Nominatim or Google Geocoding here.
        # Cache every result in the places table — you will see the same
        # towns over and over and should never pay for them twice.
        raise HTTPException(422, f"Could not resolve '{place}'. Try the nearest large city.")

    raise HTTPException(
        422,
        f"Could not resolve '{place}'. Try the nearest large city, "
        "for example 'Mumbai' or 'Lucknow'.",
    )


# ---------------------------------------------------------------- storage
# Schema is owned by migrations/ (see migrate.py), applied before the
# process starts. Nothing here creates tables.

@contextmanager
def _conn(cur=None):
    """Yield the caller's cursor if they passed one (so several writes
    share a single transaction), otherwise open a short-lived one."""
    if cur is not None:
        yield cur
    else:
        with dbmod.cursor() as c:
            yield c


# In-process chart cache in front of the `charts` table: a repeat birth
# within this worker's lifetime never touches Postgres. Bounded FIFO.
_CHART_MEMO: dict = {}
_CHART_MEMO_MAX = 512


def cache_get(key, cur=None):
    with _conn(cur) as c:
        row = c.execute("SELECT payload FROM charts WHERE key=?", (key,)).fetchone()
    return json.loads(row["payload"]) if row else None


def cache_put(key, payload, cur=None):
    with _conn(cur) as c:
        c.execute(
            "INSERT INTO charts (key, payload, created_at) VALUES (?,?,?) "
            "ON CONFLICT (key) DO UPDATE SET payload = excluded.payload, "
            "created_at = excluded.created_at",
            (key, json.dumps(payload), time.time()),
        )


def get_chart(key, local_dt, lat, lon, tz_offset, cur=None):
    """Memo -> `charts` table -> compute. The single entry point every
    endpoint uses to turn (key, birth inputs) into a chart dict."""
    hit = _CHART_MEMO.get(key)
    if hit is not None:
        return hit
    chart = cache_get(key, cur)
    if chart is None:
        chart = compute_chart(local_dt, lat, lon, tz_offset)
        cache_put(key, chart, cur)
    if len(_CHART_MEMO) >= _CHART_MEMO_MAX:
        _CHART_MEMO.pop(next(iter(_CHART_MEMO)), None)
    _CHART_MEMO[key] = chart
    return chart


def save_lead(req, chart_key, cur=None) -> int:
    with _conn(cur) as c:
        row = c.execute(
            "INSERT INTO leads (name,dob,tob,place,phone,whatsapp_opt_in,chart_key,created_at) "
            "VALUES (?,?,?,?,?,?,?,?) RETURNING id",
            (req.name, req.dob, req.tob, req.place, req.phone,
             int(req.whatsappOptIn), chart_key, time.time()),
        ).fetchone()
    return row["id"]


# ---------------------------------------------------------------- api
class Person(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dob: str
    tob: str
    place: str = Field(min_length=2, max_length=160)
    tz_offset: float = 5.5


class MatchRequest(BaseModel):
    boy: Person
    girl: Person


class SwayamvarRequest(BaseModel):
    self_person: Person = Field(alias="self")
    self_role: str = Field(pattern="^(boy|girl)$")
    candidates: list[Person] = Field(min_length=1, max_length=12)

    model_config = ConfigDict(populate_by_name=True)


class ReadingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dob: str                      # YYYY-MM-DD
    tob: str                      # HH:MM
    place: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=20)
    whatsappOptIn: bool = True
    tz_offset: float = 5.5        # IST. See note below about pre-1955 births.
    website: str = ""            # honeypot — hidden on the form, bots fill it


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Open the DB pool with a short backoff. A DB that is briefly down at
    # boot must NOT crash the process — we start anyway and /api/health
    # reports "degraded" until it recovers.
    for attempt in range(3):
        try:
            dbmod.init_pool()
            if dbmod.healthcheck():
                break
        except Exception:
            pass
        await asyncio.sleep(2 ** attempt)

    # Run pending migrations on startup. Render's free plan has no
    # pre-deploy step, and the build-time run can miss (wrong build
    # command, env vars added later). Migrations are idempotent and this
    # process runs a single worker, so a startup run is safe. Never fatal.
    try:
        import migrate
        applied = await asyncio.to_thread(migrate.main)
        print(f"[lifespan] migrate.main() -> {applied}", flush=True)
    except Exception as e:
        print(f"[lifespan] migration run failed (non-fatal): {e}", flush=True)

    yield
    dbmod.close_pool()


app = FastAPI(title="Muhurata", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://muhurata.com", "https://www.muhurata.com",
                   "http://localhost:8000", "http://127.0.0.1:8000",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.exception_handler(dbmod.DBUnavailable)
async def _db_unavailable(_request, _exc):
    # The database could not be reached for this request. Fail fast and
    # calm instead of a 130s hang into a bare 500.
    return JSONResponse(
        status_code=503,
        content={"detail": "Our service is briefly unavailable. Please try again in a moment."},
    )


# Rate-limit dependencies for the write / cost endpoints. Cloudflare does
# the coarse cross-IP limiting; these are the per-worker backstop.
_rl_reading = limiter("reading", per_minute=5, burst=8)
_rl_pdf = limiter("pdf", per_minute=3, burst=4)
_rl_llm = limiter("llm", per_minute=8, burst=10)


class NakshaMessage(BaseModel):
    role: str
    content: str


class NakshaRequest(BaseModel):
    # session_id used to come from the client, so a refresh reset the
    # quota. Identity is now the verified Supabase user id. The field is
    # kept (ignored) so an older cached frontend doesn't 422.
    session_id: str | None = None
    messages: list[NakshaMessage]
    # What the person is currently looking at on the page — their chart
    # summary, running dasha, ishta devata, the reading text, the
    # practice. Lets Naksha answer about "this" without re-asking for
    # birth details. Free-form dict; the server renders a bounded digest.
    context: dict | None = None


def _naksha_context_block(ctx: dict) -> str:
    """Render the page context the frontend sent into a short, bounded
    block Naksha can read. Never trust lengths — clip everything."""
    def s(v, n=600):
        return str(v).strip()[:n] if v is not None else ""

    lines = ["The person is currently looking at this on the page. Use it to "
             "answer about their chart directly, without asking again for "
             "their birth details:"]
    who = " ".join(x for x in [s(ctx.get("name"), 80), "born",
                               s(ctx.get("dob"), 20), s(ctx.get("tob"), 10),
                               s(ctx.get("place"), 80)] if x and x != "born")
    if who:
        lines.append(f"- {who}")
    pairs = [
        ("Lagna", ctx.get("lagna")), ("Moon sign", ctx.get("moon_sign")),
        ("Birth nakshatra", ctx.get("nakshatra")),
        ("Running mahadasha", ctx.get("mahadasha")),
        ("Running antardasha", ctx.get("antardasha")),
        ("Ishta Devata", ctx.get("ishta_devata")),
    ]
    for label, val in pairs:
        if val:
            lines.append(f"- {label}: {s(val, 60)}")
    pos = ctx.get("positions")
    if isinstance(pos, list) and pos:
        bits = []
        for p in pos[:12]:
            if isinstance(p, dict) and p.get("name"):
                r = " (R)" if p.get("retro") or p.get("retrograde") else ""
                bits.append(f"{s(p['name'],12)} in {s(p.get('sign'),12)} "
                            f"h{s(p.get('house'),3)}{r}")
        if bits:
            lines.append("- Placements: " + "; ".join(bits))
    for label, key in [("Summary shown", "summary"), ("Practice shown", "practice"),
                       ("Remedy shown", "remedy")]:
        if ctx.get(key):
            lines.append(f"- {label}: {s(ctx.get(key), 900)}")
    return "\n".join(lines)


@app.post("/api/naksha/chat")
def naksha_chat(req: NakshaRequest, _rl=Depends(_rl_llm), user: dict = Depends(auth.require_user)):
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(422, "Last message must be from the user.")
    latest = req.messages[-1].content.strip()
    if not latest:
        raise HTTPException(422, "Empty message.")

    uid = user["id"]

    # Signed in with saved birth details but no page context? Load the
    # profile, compute the chart, and hand Naksha the same context the
    # page would — so it never re-asks a logged-in user for their details.
    if not req.context:
        prof = load_profile(uid)
        if prof and prof.get("dob") and prof.get("tob") and prof.get("place"):
            try:
                pdt = datetime.strptime(f"{prof['dob']} {prof['tob']}", "%Y-%m-%d %H:%M")
                plat, plon, _ = geocode(prof["place"])
                pk = cache_key(f"{pdt.isoformat()}@5.5", plat, plon)
                pch = get_chart(pk, pdt, plat, plon, 5.5)
                prun = running_dasha(pch) or {}
                pdev = ishta_devata(pch)
                req.context = {
                    "name": prof.get("name"), "dob": prof["dob"],
                    "tob": prof["tob"], "place": prof["place"],
                    "lagna": pch["ascendant"]["sign"], "moon_sign": pch["moon_sign"],
                    "nakshatra": pch["birth_nakshatra"],
                    "mahadasha": prun.get("mahadasha"), "antardasha": prun.get("antardasha"),
                    "ishta_devata": pdev["devata"],
                    "positions": [{"name": p["name"], "sign": p["sign"],
                                   "house": p["house"], "retrograde": p["retrograde"]}
                                  for p in pch["positions"]],
                }
            except Exception:
                pass

    # Layer 1: FAQ. Free, instant, never touches the quota. Skipped once
    # there is chart context — then even "what is a dasha?" deserves an
    # answer about THEIR dasha, not the glossary entry.
    if not req.context:
        faq = naksha.match_faq(latest)
        if faq:
            return {"reply": faq, "source": "faq", "tool_results": [],
                    "remaining_today": naksha.check_and_increment(uid, cost=False)[1]}

    # Layer 3: LLM. Costs money, so it's gated.
    allowed, remaining = naksha.check_and_increment(uid, cost=True)
    if not allowed:
        return {
            "reply": "You've used today's free messages with me. Unlimited "
                    "chat that reads your own chart is part of Naksha Pro, "
                    "which is coming soon.",
            "source": "limit", "tool_results": [], "remaining_today": 0,
            "limit_reached": True,
        }

    if not naksha.configured():
        raise HTTPException(503, "Naksha's chat brain isn't configured yet.")

    def _kundali_tool(inp):
        p = Person(name=inp.get("name","Friend"), dob=inp["dob"],
                  tob=inp["tob"], place=inp["place"])
        chart = _chart_for(p)
        running = running_dasha(chart)
        devata = ishta_devata(chart)
        return {"lagna": chart["ascendant"]["sign"], "moon_sign": chart["moon_sign"],
                "nakshatra": chart["birth_nakshatra"],
                "mahadasha": running["mahadasha"], "antardasha": running["antardasha"],
                "ishta_devata": devata["devata"]}

    def _match_tool(boy_in, girl_in):
        boy = Person(name=boy_in.get("name","Groom"), dob=boy_in["dob"],
                    tob=boy_in["tob"], place=boy_in["place"])
        girl = Person(name=girl_in.get("name","Bride"), dob=girl_in["dob"],
                     tob=girl_in["tob"], place=girl_in["place"])
        res = guna_match(_chart_for(boy), _chart_for(girl))
        return {"total": res["total"], "verdict": res["verdict"], "summary": res["summary"]}

    try:
        history = [{"role": m.role, "content": m.content} for m in req.messages]
        if req.context:
            # Fold the page context into the latest user message so role
            # order still strictly alternates (Anthropic requires that).
            history[-1] = {
                "role": "user",
                "content": _naksha_context_block(req.context) + "\n\n" + history[-1]["content"],
            }
        result = naksha.chat_turn(history, _kundali_tool, build_horoscope, _match_tool)
    except Exception as e:
        raise HTTPException(502, f"Naksha could not respond: {e}")

    return {**result, "source": "llm", "remaining_today": remaining, "limit_reached": False}


_SWAYAMVAR_SYSTEM = """You are Naksha comparing marriage matches for \
someone at Muhurata. Warm, direct, decisive. Plain text only — no \
markdown, no bullets, no headers.

You are given a ranked list of guna-milan results (score out of 36, \
verdict, whether Mangal dosha is present) for each candidate. Write 2 \
short paragraphs: first, name the strongest match and say plainly why \
it stands out; then a quick honest word on the others — where a lower \
score or a Mangal dosha actually matters and where it doesn't (Mangal \
dosha is commonly cancelled when both charts carry it or by other \
classical exceptions). End with a clear recommendation. Give a reading, \
not a disclaimer."""


def _swayamvar_summary(self_name, self_role, results):
    lines = [f"{self_name or 'The person'} is the "
             f"{'groom' if self_role == 'boy' else 'bride'}. Candidates, "
             f"best first:"]
    for r in results:
        lines.append(f"- {r['name']}: {r['total']}/{r['out_of']} ({r['verdict']})"
                     + (", Mangal dosha present" if r['mangal_dosha'] else ""))
    return naksha.complete(_SWAYAMVAR_SYSTEM, "\n".join(lines), max_tokens=380)


@app.post("/api/swayamvar")
def swayamvar(req: SwayamvarRequest, user: dict = Depends(auth.optional_user)):
    """Match one person against several candidates at once, ranked by
    score. Signed-in users also get an LLM comparison and recommendation."""
    t0 = time.perf_counter()
    self_chart = _chart_for(req.self_person)

    results = []
    for cand in req.candidates:
        cand_chart = _chart_for(cand)
        if req.self_role == "boy":
            res = guna_match(self_chart, cand_chart)
        else:
            res = guna_match(cand_chart, self_chart)
        results.append({
            "name": cand.name, "total": res["total"], "out_of": res["out_of"],
            "verdict": res["verdict"], "summary": res["summary"],
            "mangal_dosha": (res["mangal"]["girl"] if req.self_role == "boy"
                             else res["mangal"]["boy"])["present"],
        })

    results.sort(key=lambda r: r["total"], reverse=True)

    if user:
        try:
            sp = req.self_person
            save_person(user["id"], sp.name, sp.dob, sp.tob, sp.place)
            for cand in req.candidates:
                save_person(user["id"], cand.name, cand.dob, cand.tob, cand.place)
        except Exception:
            pass

    summary = None
    if user and results and naksha.configured():
        try:
            summary = _swayamvar_summary(req.self_person.name, req.self_role, results)
        except Exception:
            summary = None

    return {
        "ms": round((time.perf_counter() - t0) * 1000, 2),
        "self": req.self_person.name,
        "results": results,
        "best_match": results[0]["name"] if results else None,
        "summary": summary,
    }


# LLM PDF section key -> interpret.reading() key, for the rule-based
# fallback when a section's LLM call fails.
_PDF_FALLBACK_KEY = {
    "summary": "summary", "nature": "lagna", "mind": "mind", "money": "money",
    "work_health": "health", "relationships": "relationships", "career": "career",
    "dasha": "period", "devata": "devata", "practice": "practice",
}


def _pdf_sections(chart, running, devata, first_name, chart_key):
    """The reading prose for the PDF: LLM-written, one section at a time,
    cached per (chart, section) in the predictions table. Falls back to
    the rule-based interpret.reading() text for any section the LLM can't
    produce, so a PDF always renders."""
    rule_based = reading(chart, running, devata, first_name)

    def _cache_get(section):
        with dbmod.cursor() as c:
            row = c.execute(
                "SELECT text FROM predictions WHERE chart_key=? AND section=?",
                (chart_key, "pdf:" + section)).fetchone()
        return row["text"] if row else None

    def _cache_put(section, text):
        with dbmod.cursor() as c:
            c.execute(
                "INSERT INTO predictions (chart_key, section, text, created_at) "
                "VALUES (?,?,?,?) ON CONFLICT (chart_key, section) DO UPDATE SET "
                "text = excluded.text, created_at = excluded.created_at",
                (chart_key, "pdf:" + section, text, time.time()))

    def _fallback(section):
        return rule_based.get(_PDF_FALLBACK_KEY.get(section, section), "")

    if not naksha.configured():
        return {k: _fallback(k) for k in preds.PDF_SECTION_ORDER}

    return preds.generate_many(
        chart, running, first_name, preds.PDF_SECTION_ORDER,
        cache_get=_cache_get, cache_put=_cache_put, fallback=_fallback)


@app.post("/api/reading/pdf")
def reading_pdf(req: ReadingRequest, theme: str = "light", _rl=Depends(_rl_pdf)):
    """Same chart as /api/reading, as a downloadable PDF. The prose is
    LLM-written and cached per chart; ?theme=light|dark picks the look."""
    try:
        local_dt = datetime.strptime(f"{req.dob} {req.tob}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD and time HH:MM.")
    lat, lon, _ = geocode(req.place)
    key = cache_key(f"{local_dt.isoformat()}@{req.tz_offset}", lat, lon)
    chart = get_chart(key, local_dt, lat, lon, req.tz_offset)
    running = running_dasha(chart)
    devata = ishta_devata(chart)
    first = req.name.strip().split()[0] if req.name.strip() else ""
    sections = _pdf_sections(chart, running, devata, first, key)

    avk = None
    try:
        from avakhada import avakhada as avakhada_fn
        avk = avakhada_fn(chart, local_dt, lat, lon, req.tz_offset)
    except Exception:
        pass

    pdf_bytes = build_pdf(chart, sections, req.name,
                          theme="dark" if theme == "dark" else "light",
                          avakhada_data=avk)
    fname = f"muhurata-reading-{(first or 'chart').lower()}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/whatsapp/catchup-batch")
def catchup_batch(limit: int = 20, dry_run: bool = True, _admin: dict = Depends(auth.require_admin)):
    """Sends the 'we might have missed you' PDF to unsent leads via the
    approved catch-up template. dry_run=True (the default) computes
    everything and reports what WOULD be sent, without calling the
    WhatsApp API - use that first to sanity-check the batch before
    spending real sends on it.

    Requires CATCHUP_TEMPLATE_NAME to be approved in Meta Business
    Manager first (see whatsapp.py for the exact text to submit).
    Calling this before approval will fail every send with a template
    error - that is Meta rejecting it, not a bug here."""
    with dbmod.cursor() as c:
        rows = c.execute(
            "SELECT id,name,dob,tob,place,phone FROM leads "
            "WHERE sent_at IS NULL ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()

    results = []
    for row in rows:
        entry = {"lead_id": row["id"], "name": row["name"], "phone": row["phone"]}
        try:
            local_dt = datetime.strptime(f"{row['dob']} {row['tob']}", "%Y-%m-%d %H:%M")
            lat, lon, _ = geocode(row["place"])
            chart = compute_chart(local_dt, lat, lon, 5.5)
            running = running_dasha(chart)
            devata = ishta_devata(chart)
            first = row["name"].strip().split()[0] if row["name"] else "there"
            sections = reading(chart, running, devata, first)
            pdf_bytes = build_pdf(chart, sections, row["name"],
                                  section_order=LEGACY_SECTION_ORDER)

            if dry_run:
                entry["status"] = "would_send"
                entry["pdf_bytes"] = len(pdf_bytes)
            else:
                media_id = wa.upload_media(pdf_bytes, "muhurata-reading.pdf")
                send_result = wa.send_template_with_document(
                    row["phone"], wa.CATCHUP_TEMPLATE_NAME, media_id,
                    "muhurata-reading.pdf", [first])
                if "error" in send_result or "messages" not in send_result:
                    entry["status"] = "failed"
                    entry["detail"] = send_result
                else:
                    entry["status"] = "sent"
                    with dbmod.cursor() as c2:
                        c2.execute("UPDATE leads SET sent_at=? WHERE id=?", (time.time(), row["id"]))
        except Exception as e:
            entry["status"] = "error"
            entry["detail"] = str(e)
        results.append(entry)

    return {"dry_run": dry_run, "processed": len(results), "results": results}


class PredictionRequest(Person):
    section: str = Field(pattern="^(personality|career|wealth|relationships|health)$")


@app.post("/api/predictions")
def predictions_ep(req: PredictionRequest, _rl=Depends(_rl_llm), user: dict = Depends(auth.require_user)):
    """One AstroTalk-style long-form section, generated by the LLM grounded
    in the real chart, and CACHED per (chart, section) so each unique chart
    pays the generation cost once. Degrades honestly if the LLM is down.
    Requires sign-in — it spends LLM tokens."""
    try:
        local_dt = datetime.strptime(f"{req.dob} {req.tob}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD and time HH:MM.")
    lat, lon, _ = geocode(req.place)
    key = cache_key(f"{local_dt.isoformat()}@{req.tz_offset}", lat, lon)

    # cache hit?
    with dbmod.cursor() as c:
        row = c.execute("SELECT text FROM predictions WHERE chart_key=? AND section=?",
                        (key, req.section)).fetchone()
    if row:
        return {"section": req.section, "text": row["text"], "cached": True}

    chart = get_chart(key, local_dt, lat, lon, req.tz_offset)
    running = running_dasha(chart)

    if not naksha.configured():
        raise HTTPException(503, "Predictions aren't available right now.")

    try:
        text = preds.generate_section(chart, running, req.section,
                                      req.name.strip().split()[0])
    except Exception as e:
        raise HTTPException(502, f"Could not generate that section: {e}")

    with dbmod.cursor() as c:
        c.execute(
            "INSERT INTO predictions (chart_key, section, text, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT (chart_key, section) DO UPDATE SET text = excluded.text, "
            "created_at = excluded.created_at",
            (key, req.section, text, time.time()),
        )
    return {"section": req.section, "text": text, "cached": False}


@app.post("/api/full-kundli")
def full_kundli(p: Person):
    """Everything the dedicated 7-tab page needs, in one call: basic
    details, all charts, KP, Ashtakvarga, dasha. Predictions are separate
    (they need the LLM and are generated per-tab on demand)."""
    t0 = time.perf_counter()
    try:
        local_dt = datetime.strptime(f"{p.dob} {p.tob}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD and time HH:MM.")
    if local_dt.year < 1900 or local_dt > datetime.now():
        raise HTTPException(422, "Birth date looks wrong.")
    lat, lon, resolved = geocode(p.place)
    key = cache_key(f"{local_dt.isoformat()}@{p.tz_offset}", lat, lon)
    chart = get_chart(key, local_dt, lat, lon, p.tz_offset)

    running = running_dasha(chart)
    devata = ishta_devata(chart)
    avk = avakhada_mod.avakhada(chart, local_dt, lat, lon, p.tz_offset)

    # charts: the commonly-shown divisionals
    charts_data = {}
    for div in ["D1", "D9", "D2", "D3", "D7", "D10", "D12", "D30", "D60"]:
        charts_data[div] = divisionals.divisional_positions(chart, div)

    return {
        "ms": round((time.perf_counter() - t0) * 1000, 2),
        "name": p.name,
        "birth": {"date": p.dob, "time": p.tob, "place": resolved,
                  "lat": lat, "lon": lon},
        "ascendant": chart["ascendant"],
        "moon_sign": chart["moon_sign"],
        "birth_nakshatra": chart["birth_nakshatra"],
        "positions": chart["positions"],
        "avakhada": avk["avakhada"],
        "panchang": avk["panchang"],
        "running": running,
        "ishta_devata": devata,
        "atmakaraka": chart["atmakaraka"],
        "vimshottari": chart["vimshottari"],
        "charts": {
            "north": north_indian(chart, 340),
            "south": south_indian(chart, 340),
            "navamsa": navamsa_north(chart, 340),
        },
        "divisionals": charts_data,
        "kp": {
            "planets": kp_engine.kp_planets(chart),
            "cusps": kp_engine.kp_cusps(chart),
            "ruling": kp_engine.ruling_planets(chart),
        },
        "ashtakvarga": ashtakvarga.sarvashtakavarga(chart),
    }


@app.get("/api/glyphs")
def glyphs_defs():
    """The SVG symbol definitions the page drops in once, then references."""
    return Response(content=all_glyphs_svg_defs(), media_type="image/svg+xml")


@app.get("/api/cities")
def cities():
    """Every place name the free geocoder recognises, for an autocomplete
    on the frontend. Cheap to compute, so no caching needed."""
    seen = set()
    out = []
    for key in CITIES:
        label = key.title()
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    out.sort()
    return {"cities": out}


@app.get("/api/health")
def health(strict: bool = False):
    """Liveness by default: 200 as long as the process is up, with the
    real DB state in the body. That keeps Render's health check from
    flapping when a free-tier Supabase instance auto-pauses (the app
    self-heals when it wakes). `?strict=1` returns 503 on a DB miss, for
    an uptime monitor that wants to know."""
    ok = dbmod.healthcheck()
    return JSONResponse(
        status_code=503 if (strict and not ok) else 200,
        content={"ok": ok, "db": "ok" if ok else "degraded"},
    )


# ---------------------------------------------------------------- profile
class ProfileBody(BaseModel):
    name: str = Field(default="", max_length=120)
    dob: str = Field(default="", max_length=10)
    tob: str = Field(default="", max_length=5)
    place: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=20)


def save_profile(uid, name, dob, tob, place, phone, cur=None):
    """Upsert a signed-in user's birth details so every form can prefill."""
    if not uid:
        return
    with _conn(cur) as c:
        c.execute(
            "INSERT INTO profiles (user_id,name,dob,tob,place,phone,updated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT (user_id) DO UPDATE SET "
            "name=excluded.name, dob=excluded.dob, tob=excluded.tob, "
            "place=excluded.place, phone=excluded.phone, updated_at=excluded.updated_at",
            (uid, name or "", dob or "", tob or "", place or "", phone or "", time.time()),
        )


def load_profile(uid):
    if not uid:
        return None
    with dbmod.cursor() as c:
        return c.execute(
            "SELECT name,dob,tob,place,phone FROM profiles WHERE user_id=?",
            (uid,)).fetchone()


def _person_id(name, dob, tob, place):
    import hashlib
    key = f"{(name or '').strip()}|{dob}|{tob}|{(place or '').strip()}".lower()
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def save_person(uid, name, dob, tob, place, cur=None):
    """Remember someone a signed-in user entered details for."""
    if not (uid and dob and tob and (place or "").strip() and (name or "").strip()):
        return
    pid = _person_id(name, dob, tob, place)
    with _conn(cur) as c:
        c.execute(
            "INSERT INTO people (user_id,person_id,name,dob,tob,place,updated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT (user_id,person_id) DO UPDATE SET "
            "name=excluded.name, place=excluded.place, updated_at=excluded.updated_at",
            (uid, pid, name.strip(), dob, tob, place.strip(), time.time()),
        )


@app.get("/api/people")
def list_people(user: dict = Depends(auth.require_user)):
    with dbmod.cursor() as c:
        rows = c.execute(
            "SELECT person_id,name,dob,tob,place FROM people WHERE user_id=? "
            "ORDER BY updated_at DESC LIMIT 40", (user["id"],)).fetchall()
    return {"people": rows}


@app.post("/api/people")
def add_person(body: ProfileBody, user: dict = Depends(auth.require_user)):
    save_person(user["id"], body.name, body.dob, body.tob, body.place)
    return {"person_id": _person_id(body.name, body.dob, body.tob, body.place)}


@app.delete("/api/people/{person_id}")
def del_person(person_id: str, user: dict = Depends(auth.require_user)):
    with dbmod.cursor() as c:
        c.execute("DELETE FROM people WHERE user_id=? AND person_id=?",
                  (user["id"], person_id))
    return {"ok": True}


@app.get("/api/profile")
def get_profile(user: dict = Depends(auth.require_user)):
    return load_profile(user["id"]) or {}


@app.put("/api/profile")
def put_profile(body: ProfileBody, user: dict = Depends(auth.require_user)):
    save_profile(user["id"], body.name, body.dob, body.tob, body.place, body.phone)
    return {"ok": True}


@app.post("/api/reading")
def make_reading(req: ReadingRequest, _rl=Depends(_rl_reading),
                 user: dict = Depends(auth.optional_user)):
    t0 = time.perf_counter()

    # Honeypot: real users never fill the hidden field. Silently accept
    # and drop so the bot gets no signal.
    if (req.website or "").strip():
        return {"ok": True}

    try:
        local_dt = datetime.strptime(f"{req.dob} {req.tob}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD and time HH:MM.")

    if local_dt.year < 1900 or local_dt > datetime.now():
        raise HTTPException(422, "Birth date looks wrong.")

    lat, lon, resolved = geocode(req.place)

    utc_iso = local_dt.isoformat()
    key = cache_key(f"{utc_iso}@{req.tz_offset}", lat, lon)

    cached = key in _CHART_MEMO

    # One pooled connection, one transaction: chart cache-fill + lead +
    # claim commit together or not at all.
    with dbmod.cursor() as c:
        chart = get_chart(key, local_dt, lat, lon, req.tz_offset, cur=c)
        running = running_dasha(chart)
        devata = ishta_devata(chart)
        first = req.name.strip().split()[0]
        sections = reading(chart, running, devata, first)

        lead_id = save_lead(req, key, cur=c)
        msg = whatsapp_text(sections)
        code = make_claim(msg, first, lead_id, cur=c)

        # signed in? remember their details so they never retype them
        if user:
            save_profile(user["id"], req.name, req.dob, req.tob, req.place, req.phone, cur=c)
            save_person(user["id"], req.name, req.dob, req.tob, req.place, cur=c)

    return {
        "whatsapp_link": wa.claim_link(code),
        "claim_code": code,
        "cached": cached,
        "ms": round((time.perf_counter() - t0) * 1000, 2),
        "place": {"resolved": resolved, "lat": lat, "lon": lon},
        "ascendant": chart["ascendant"],
        "moon_sign": chart["moon_sign"],
        "birth_nakshatra": chart["birth_nakshatra"],
        "positions": chart["positions"],
        "running": running,
        "atmakaraka": chart["atmakaraka"],
        "ishta_devata": devata,
        "charts": {
            "north": north_indian(chart, 340),
            "south": south_indian(chart, 340),
            "navamsa": navamsa_north(chart, 340),
        },
        "reading": sections,
        "whatsapp": whatsapp_text(sections),
    }


@app.get("/api/leads")
def leads(limit: int = 100, _admin: dict = Depends(auth.require_admin)):
    """Pending sends. Wire this to your WhatsApp sender. Admin only —
    this is every customer's name, DOB, birth time, place and phone."""
    with dbmod.cursor() as c:
        rows = c.execute(
            "SELECT id,name,dob,tob,place,phone,created_at FROM leads "
            "WHERE sent_at IS NULL ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows


# ---------------------------------------------------------------- whatsapp
def make_claim(message: str, name: str, lead_id: int, cur=None) -> str:
    code = secrets.token_hex(3).upper()      # 6 chars, e.g. 4F9A2C
    with _conn(cur) as c:
        c.execute("INSERT INTO claims (code,message,name,lead_id,created_at) VALUES (?,?,?,?,?)",
                  (code, message, name, lead_id, time.time()))
    return code


def redeem_claim(code: str):
    with dbmod.cursor() as c:
        row = c.execute("SELECT message,name,lead_id FROM claims WHERE code=? AND claimed_at IS NULL",
                        (code,)).fetchone()
        if row:
            c.execute("UPDATE claims SET claimed_at=? WHERE code=?", (time.time(), code))
    return row


@app.get("/api/whatsapp/webhook")
def wa_verify(request: Request):
    """Meta calls this once when you configure the webhook."""
    q = request.query_params
    if (wa.WA_VERIFY_TOKEN
            and q.get("hub.mode") == "subscribe"
            and q.get("hub.verify_token") == wa.WA_VERIFY_TOKEN):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "verify token mismatch")


@app.post("/api/whatsapp/webhook")
async def wa_webhook(request: Request):
    """User messaged us. If their text carries a claim code, reply with the
    reading. Their inbound message is what opens the 24h service window.

    Verified against Meta's X-Hub-Signature-256 so a forged POST can't
    redeem claim codes or burn WhatsApp sends."""
    raw = await request.body()
    if not wa.verify_signature(raw, request.headers.get("x-hub-signature-256", "")):
        raise HTTPException(403, "bad signature")
    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "bad body")
    frm, text = wa.parse_incoming(body)
    if not frm:
        return {"ok": True}                   # delivery receipt, ignore

    code = None
    for token in (text or "").replace(":", " ").split():
        t = token.strip().upper()
        if len(t) == 6 and all(ch in "0123456789ABCDEF" for ch in t):
            code = t
            break

    if code:
        row = redeem_claim(code)
        if row:
            wa.send_text(frm, row["message"])
            if row["lead_id"] is not None:
                with dbmod.cursor() as c:
                    c.execute("UPDATE leads SET sent_at=? WHERE id=?", (time.time(), row["lead_id"]))
            return {"ok": True, "sent": True}
        wa.send_text(frm, "That code has already been used, or we could not find it. "
                          "Submit your details again at muhurata.com and we will resend.")
        return {"ok": True, "sent": False}

    wa.send_text(frm,
        "Namaste. To get your reading, enter your birth details at muhurata.com "
        "and tap the WhatsApp button that appears.")
    return {"ok": True}


# ---------------------------------------------------------------- free services
def _chart_for(p) -> dict:
    try:
        dt = datetime.strptime(f"{p.dob} {p.tob}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, f"{p.name}: date must be YYYY-MM-DD and time HH:MM.")
    if dt.year < 1900 or dt > datetime.now():
        raise HTTPException(422, f"{p.name}: birth date looks wrong.")
    lat, lon, _ = geocode(p.place)
    key = cache_key(f"{dt.isoformat()}@{p.tz_offset}", lat, lon)
    return get_chart(key, dt, lat, lon, p.tz_offset)


@app.post("/api/kundali")
def kundali(p: Person):
    """Free chart. No phone number, no lead capture — this one is genuinely free."""
    t0 = time.perf_counter()
    chart = _chart_for(p)
    running = running_dasha(chart)
    devata = ishta_devata(chart)
    return {
        "ms": round((time.perf_counter() - t0) * 1000, 2),
        "name": p.name,
        "ascendant": chart["ascendant"],
        "moon_sign": chart["moon_sign"],
        "birth_nakshatra": chart["birth_nakshatra"],
        "positions": chart["positions"],
        "running": running,
        "atmakaraka": chart["atmakaraka"],
        "ishta_devata": devata,
        "charts": {
            "north": north_indian(chart, 340),
            "south": south_indian(chart, 340),
            "navamsa": navamsa_north(chart, 340),
        },
    }


@app.post("/api/matching")
def matching(req: MatchRequest):
    t0 = time.perf_counter()
    b = _chart_for(req.boy)
    g = _chart_for(req.girl)
    res = guna_match(b, g)
    res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
    res["names"] = {"boy": req.boy.name, "girl": req.girl.name}
    res["charts"] = {"boy": north_indian(b, 300), "girl": north_indian(g, 300)}
    return res


@app.get("/api/horoscope")
def horoscope_ep(period: str = "today"):
    if period not in ("today", "tomorrow", "monthly", "yearly"):
        raise HTTPException(422, "period must be today, tomorrow, monthly or yearly")
    return build_horoscope(period)


class TarotRequest(BaseModel):
    question: str = Field(default="", max_length=400)
    spread: str = Field(default="three", pattern="^(one|three|cross)$")
    seed: str | None = Field(default=None, max_length=64)
    # the face-down positions the person tapped, in order — the draw is
    # seeded from these so the cards they chose are the cards they get.
    picks: list[int] | None = Field(default=None, max_length=6)


@app.post("/api/tarot")
def tarot_ep(req: TarotRequest, _rl=Depends(_rl_llm), user: dict = Depends(auth.require_user)):
    """Draw a spread and read it. LLM-written in Naksha's voice — a
    confident reading, not a disclaimer. Requires sign-in (LLM cost)."""
    seed = req.seed
    if req.picks:
        seed = (req.question.strip() + "|" + ",".join(str(int(p)) for p in req.picks))[:200]
    cards = tarot_mod.draw(req.spread, seed)
    first = (user.get("email") or "").split("@")[0]
    try:
        reading_text = tarot_mod.generate_reading(req.question, cards, first)
    except Exception as e:
        raise HTTPException(502, f"Could not read the cards just now: {e}")
    return {"spread": req.spread, "question": req.question, "cards": cards,
            "reading": reading_text}
