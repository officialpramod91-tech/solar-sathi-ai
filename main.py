"""
Solar Sathi AI — v6.7 Enterprise Final Solid Release + Meta WhatsApp Integration
- Real-time Groq Model Discovery (Resolves 404 Model Not Found)
- Deterministic Daily Generation Output (Zero AI dependency for unit math)
- Granular 4 kW Sizing for Rs 4500-5500 Bills
- Transparent Hybrid DISCOM Net-Metering & Storage Terms
- Upgraded Documents Checklist (Aadhaar & Electricity Bill Name Matching)
- Word-Boundary Geographic Routing & Telegram Debouncing
- Official Meta Cloud API WhatsApp Lead Alerts (Zero Ban Risk)
"""

import os
import re
import csv
import asyncio
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

# ------------------------------------------------------------------
# SETUP & CONFIGURATION
# ------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise RuntimeError("GROQ_API_KEY nahi mili! .env file check karein.")

client = Groq(api_key=API_KEY)

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Meta Cloud API Credentials (Official WhatsApp)
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID", "1358122214045364")
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP", "918173031237")

CANDIDATE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "gemma2-9b-it",
    "mixtral-8x7b-32768"
]

def resolve_active_model() -> str:
    try:
        remote_models = {m.id for m in client.models.list().data}
        for m in CANDIDATE_MODELS:
            if m in remote_models:
                print(f"[Active Groq Model Locked]: {m}")
                return m
        first_available = next(iter(remote_models))
        print(f"[Auto-Selected Available Model]: {first_available}")
        return first_available
    except Exception as e:
        print(f"[Model Discovery Fallback]: {e}")
        return "llama3-8b-8192"

ACTIVE_MODEL = resolve_active_model()

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "Timestamp", "Language", "Name", "Mobile", "City", "State/DISCOM", "Monthly Bill",
    "Estimated kW", "Roof Area Req", "Central Subsidy", "State Subsidy", "Total Benefit",
    "Property Type", "System Type", "Status", "Priority",
]

COMPLETED_MOBILES = set()

def ensure_csv():
    if not os.path.exists(LEADS_FILE) or os.path.getsize(LEADS_FILE) == 0:
        with open(LEADS_FILE, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADERS)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HistoryMessage(BaseModel):
    sender: str
    text: str

class ChatRequest(BaseModel):
    message: str
    history: List[HistoryMessage] = []

# ------------------------------------------------------------------
# WORD-BOUNDARY GEOGRAPHIC INTELLIGENCE
# ------------------------------------------------------------------

UP_CITIES = [
    "lucknow", "kanpur", "noida", "greater noida", "ghaziabad", "meerut", "varanasi",
    "agra", "prayagraj", "allahabad", "gorakhpur", "bareilly", "aligarh", "moradabad",
    "saharanpur", "ayodhya", "jhansi", "khalilabad", "basti", "sant kabir nagar", "mathura"
]

DELHI_CITIES = [
    "delhi", "new delhi", "dwarka", "rohini", "saket", "janakpuri", "narela",
    "connaught place", "karol bagh", "laxmi nagar", "pitampura"
]

HARYANA_CITIES = [
    "gurugram", "gurgaon", "faridabad", "sirsa", "panipat", "sonipat",
    "karnal", "hisar", "rohtak", "ambala", "panchkula"
]

MUMBAI_METRO = [
    "mumbai", "navi mumbai", "thane", "kalyan", "dombivli", "borivali",
    "andheri", "bandra", "dadar", "chembur"
]

GUJARAT_CITIES = [
    "ahmedabad", "gandhinagar", "surat", "vadodara", "baroda", "rajkot",
    "bhavnagar", "jamnagar", "anand"
]

PUNJAB_CITIES = [
    "ludhiana", "amritsar", "jalandhar", "patiala", "bathinda", "mohali", "anandpur sahib"
]

RAJASTHAN_CITIES = [
    "jaipur", "jodhpur", "kota", "bikaner", "ajmer", "udaipur", "alwar", "suratgarh"
]

def matches_city(city_list: List[str], text: str) -> bool:
    return any(re.search(rf"\b{re.escape(c)}\b", text) for c in city_list)

def analyze_location_and_perks(city_text: str, kw: int, central_sub: int, lang: str = "hinglish") -> Tuple[str, str, int, str]:
    ct = city_text.lower().strip()
    is_eng = (lang == "english")

    if matches_city(DELHI_CITIES, ct) or re.search(r"\b(11\d{4})\b", ct):
        discom = "Delhi (BRPL / BYPL / TPDDL)"
        perk_msg = (
            "🎉 **Special Benefit for Delhi!**\n"
            "Under the Delhi Solar Policy, enjoy **₹3.00/unit GBI credit** directly adjusted in your power bills!"
            if is_eng else
            "🎉 **Delhi Solar Policy ka Special Fayda!**\n"
            "PM Surya Ghar ke sath aapko **₹3.00 per unit GBI credit** seedha aapke bijli bill mein adjust hoga!"
        )
        return "Delhi", discom, 0, perk_msg

    if matches_city(UP_CITIES, ct) or re.search(r"\b(uttar pradesh|up)\b", ct):
        state_sub = min(kw * 15000, 30000)
        total_sub = central_sub + state_sub
        discom = "UPNEDA (PVVNL/MVVNL/DVVNL/PuVVNL)"
        perk_msg = (
            f"🎉 **Great News for Uttar Pradesh!**\n"
            f"Your {kw} kW system qualifies for **₹{state_sub:,} State Subsidy** (UPNEDA) "
            f"on top of Central PM Surya Ghar (₹{central_sub:,}).\n"
            f"💰 **Total Combined Subsidy: Up to ₹{total_sub:,}!**"
            if is_eng else
            f"🎉 **Uttar Pradesh ke liye Special Fayda!**\n"
            f"Aapke {kw} kW system par PM Surya Ghar (₹{central_sub:,}) ke sath "
            f"**UP Sarkar ki taraf se ₹{state_sub:,} ki extra subsidy** milegi!\n"
            f"💰 **Total Subsidy Benefit: Lagbhag ₹{total_sub:,} tak!**"
        )
        return "Uttar Pradesh", discom, state_sub, perk_msg

    if matches_city(PUNJAB_CITIES, ct) or re.search(r"\bpunjab\b", ct):
        return "Punjab", "PSPCL", 0, ""

    if matches_city(RAJASTHAN_CITIES, ct) or re.search(r"\brajasthan\b", ct):
        return "Rajasthan", "JVVNL / AVVNL / JdVVNL", 0, ""

    if matches_city(GUJARAT_CITIES, ct) or re.search(r"\bgujarat\b", ct):
        return "Gujarat", "UGVCL / DGVCL / PGVCL / MGVCL / Torrent Power", 0, ""

    if matches_city(HARYANA_CITIES, ct) or re.search(r"\bharyana\b", ct):
        return "Haryana", "DHBVN / UHBVN", 0, ""

    if matches_city(MUMBAI_METRO, ct):
        return "Maharashtra", "MSEDCL / BEST / Adani / Tata Power", 0, ""

    return "All India", "National Portal Standard", 0, ""

# ------------------------------------------------------------------
# SYSTEM SIZING (GRANULAR SLABS)
# ------------------------------------------------------------------

def estimate_kw_and_subsidy(bill: int, property_type: Optional[str] = None) -> Tuple[int, int]:
    if bill <= 1500:
        kw, sub = 1, 30000
    elif bill <= 2800:
        kw, sub = 2, 60000
    elif bill <= 4000:
        kw, sub = 3, 78000
    elif bill <= 5500:
        kw, sub = 4, 78000
    elif bill <= 7500:
        kw, sub = 5, 78000
    elif bill <= 9500:
        kw, sub = 7, 78000
    else:
        kw, sub = 10, 78000

    if property_type and property_type.lower() == "commercial":
        return kw, 0
    return kw, sub

def get_roof_area_sqft(kw: int) -> str:
    return f"{kw * 80} - {kw * 100} sq. ft."

def get_priority(bill: Optional[int], prop: Optional[str], sys_type: Optional[str], complete: bool) -> str:
    if not complete:
        return "INCOMPLETE — FOLLOW UP"
    if prop and prop.lower() == "commercial":
        return "HIGH PRIORITY (Commercial Lead)"
    if sys_type and sys_type.lower() == "hybrid":
        return "HIGH PRIORITY (Hybrid Lead)"
    if bill is not None and bill >= 3000:
        return "HIGH PRIORITY (3kW+ Sweet Spot)"
    if bill is not None and bill >= 1500:
        return "MEDIUM PRIORITY"
    return "STANDARD"

# ------------------------------------------------------------------
# TELEGRAM ALERTS
# ------------------------------------------------------------------

def send_telegram_alert(state: dict, complete: bool = True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    prop = state.get("property_type")
    is_comm = prop and prop.lower() == "commercial"
    sys_type = state.get("system_type") or "N/A"

    kw, central_sub = (None, None)
    if state.get("bill") is not None:
        kw, central_sub = estimate_kw_and_subsidy(state["bill"], prop)

    priority = get_priority(state.get("bill"), prop, sys_type, complete)
    region, discom, state_sub, _ = analyze_location_and_perks(
        state.get("city") or "", kw or 3, central_sub or 0, state.get("language") or "hinglish"
    )

    if is_comm:
        state_sub = 0

    header_tag = "🚨 *NEW QUALIFIED SOLAR LEAD!* ☀️" if complete else "🟡 *INCOMPLETE LEAD (FOLLOW-UP!)* ⚠️"
    status_label = "COMPLETE LEAD" if complete else "PARTIAL (City Pending)"

    name = state.get("name") or "Not Provided"
    mobile = state.get("mobile") or "Not Provided"
    city = state.get("city") or "Pending"
    bill_val = f"₹{state['bill']}" if state.get("bill") is not None else "N/A"
    prop_val = "Commercial (Dukan/Office)" if is_comm else (prop or "N/A")
    sys_info = f"{kw} kW ({sys_type})" if kw else "Pending"
    roof_val = get_roof_area_sqft(kw) if kw else "Pending"

    if is_comm:
        sub_line = "Commercial (40% Tax Depreciation / Tariff Reductions)"
    else:
        total_benefit = (central_sub or 0) + state_sub
        if state_sub > 0:
            sub_line = f"₹{central_sub:,} (Central) + ₹{state_sub:,} (State) = *₹{total_benefit:,}*"
        else:
            sub_line = f"₹{central_sub:,}" if central_sub else "Pending"

    time_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")

    text = (
        f"{header_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:* {name}\n"
        f"📞 *Mobile:* `{mobile}`\n"
        f"📍 *Location:* {city}\n"
        f"⚡ *DISCOM / State:* {discom} ({region})\n"
        f"💡 *Monthly Bill:* {bill_val}\n"
        f"🏢 *Property:* {prop_val}\n"
        f"🔋 *System:* {sys_info}\n"
        f"🏠 *Roof Space Req:* ~{roof_val}\n"
        f"💰 *Total Subsidy:* {sub_line}\n"
        f"🎯 *Status:* {status_label}\n"
        f"📊 *Priority:* {priority}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {time_str}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}

    try:
        requests.post(url, json=payload, timeout=6)
    except Exception as e:
        print(f"[Telegram Error]: {e}")

async def send_delayed_incomplete_alert(state: dict, delay_seconds: int = 60):
    await asyncio.sleep(delay_seconds)
    mobile = state.get("mobile")
    if mobile and mobile not in COMPLETED_MOBILES:
        send_telegram_alert(state, complete=False)

# ------------------------------------------------------------------
# META CLOUD API WHATSAPP ALERTS (ZERO BAN RISK)
# ------------------------------------------------------------------

def send_whatsapp_alert(state: dict):
    if not META_ACCESS_TOKEN or not META_PHONE_ID:
        print("[Meta WhatsApp Warning]: META_ACCESS_TOKEN ya META_PHONE_ID missing hai.")
        return

    prop = state.get("property_type")
    is_comm = prop and prop.lower() == "commercial"
    sys_type = state.get("system_type") or "N/A"

    kw, central_sub = (None, None)
    if state.get("bill") is not None:
        kw, central_sub = estimate_kw_and_subsidy(state["bill"], prop)

    priority = get_priority(state.get("bill"), prop, sys_type, True)
    region, discom, state_sub, _ = analyze_location_and_perks(
        state.get("city") or "", kw or 3, central_sub or 0, state.get("language") or "hinglish"
    )

    if is_comm:
        state_sub = 0

    name = state.get("name") or "Not Provided"
    mobile = state.get("mobile") or "Not Provided"
    city = state.get("city") or "Pending"
    bill_val = f"₹{state['bill']}" if state.get("bill") is not None else "N/A"
    prop_val = "Commercial" if is_comm else (prop or "Residential")
    sys_info = f"{kw} kW ({sys_type})" if kw else "Pending"
    roof_val = get_roof_area_sqft(kw) if kw else "Pending"

    if is_comm:
        sub_line = "Commercial (40% Tax Depreciation)"
    else:
        total_benefit = (central_sub or 0) + state_sub
        if state_sub > 0:
            sub_line = f"₹{central_sub:,} (Central) + ₹{state_sub:,} (State) = ₹{total_benefit:,}"
        else:
            sub_line = f"₹{central_sub:,}" if central_sub else "Pending"

    time_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")

    alert_text = (
        f"🚨 *NEW SOLAR SATHI LEAD!* ☀️\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Customer:* {name}\n"
        f"📞 *Mobile:* {mobile}\n"
        f"📍 *Location:* {city} ({region})\n"
        f"⚡ *DISCOM:* {discom}\n"
        f"💡 *Monthly Bill:* {bill_val}\n"
        f"🏢 *Property:* {prop_val}\n"
        f"☀️ *System:* {sys_info}\n"
        f"🏠 *Roof Space Req:* ~{roof_val}\n"
        f"💰 *Total Subsidy:* {sub_line}\n"
        f"📊 *Priority:* {priority}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {time_str}"
    )

    url = f"https://graph.facebook.com/v20.0/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": ADMIN_WHATSAPP,
        "type": "text",
        "text": {"body": alert_text}
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=8)
        if res.status_code == 200:
            print("[Meta WhatsApp Success]: Lead alert delivered successfully!")
        else:
            print(f"[Meta WhatsApp Failed]: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[Meta WhatsApp Error]: {e}")

# ------------------------------------------------------------------
# TEMPLATES & COPY (ENHANCED DOCUMENTS & NET-METERING NOTES)
# ------------------------------------------------------------------

GREETING_MESSAGE = (
    "☀️ **Welcome to Solar Sathi!** 🙏\n\n"
    "Please select your language / Kripya apni bhasha chunein:\n"
    "1️⃣ **English**\n"
    "2️⃣ **Hinglish (Hindi)**\n\n"
    "*(Reply with 1 or 2, or simply type your monthly electricity bill)*"
)

TEMPLATES = {
    "english": {
        "ASK_BILL": "What is your approximate monthly electricity bill? (e.g. 3000)",
        "ASK_PROPERTY": "Is this solar system required for your Home (Residential) or Shop/Office/Factory (Commercial)?",
        "ASK_SYSTEM_TYPE": "Would you prefer an On-Grid system (maximum bill cut to zero) or a Hybrid system (battery backup during power outages)?",
        "ASK_NAME": "Please provide your full name.",
        "ASK_MOBILE": "Please share your 10-digit WhatsApp/mobile number so our certified engineer can share a detailed proposal.",
        "ASK_CITY": "In which City or Area do you want to install solar? (Please share City & PIN code).",
        "INVALID_BILL": "Please enter your monthly electricity bill amount in numbers only — for example: 3500.",
        "INVALID_NAME": "Please provide your full name (letters only) — for example: Pramod Kumar.",
        "INVALID_MOBILE": "That doesn't look like a valid 10-digit Indian mobile number. Please re-enter (e.g. 9876543210).",
        "FAQ_ONGRID": "An On-Grid system connects directly to the power grid with Net-Metering, reducing your electricity bill to nearly zero. It does not provide battery backup during power cuts.",
        "FAQ_HYBRID": "A Hybrid system connects to the grid while storing power in batteries for backup. PM Surya Ghar subsidy covers the solar capacity up to standard norms, while battery storage is paid separately.",
        "FAQ_DIFF": (
            "☀️ **On-Grid:** Connects directly to the grid to reduce electricity bills to zero, but shuts down during power outages.\n"
            "🔋 **Hybrid:** Provides grid savings plus battery backup during load shedding.\n"
            "💰 PM Surya Ghar subsidy covers solar plant capacity; battery storage is billed separately."
        ),
        "DOCUMENTS_LIST": (
            "Documents required for PM Surya Ghar subsidy:\n"
            "1. Latest Electricity Bill\n"
            "2. Identity & Address Proof (Aadhaar / Voter ID)\n"
            "3. Bank Passbook copy (for direct DBT subsidy transfer)\n\n"
            "⚠️ *Important: The name on your electricity bill and Aadhaar/ID proof must match.* Our engineer assists with complete portal registration."
        ),
        "SENSITIVE_REPLY": "Exact zero-down financing/EMI schemes and final quotation depend on site structure feasibility. Our certified technical team will share exact figures during survey.",
    },
    "hinglish": {
        "ASK_BILL": "Aapka monthly electricity bill lagbhag kitna aata hai? (approx amount likhein, jaise 3000)",
        "ASK_PROPERTY": "Yeh solar ghar ke liye chahiye ya dukan/office/factory ke liye?",
        "ASK_SYSTEM_TYPE": "Sirf bill zero karne ke liye On-grid system chahiye, ya power cut mein backup ke liye Hybrid system (battery ke sath)?",
        "ASK_NAME": "Aapka poora naam bata dijiye.",
        "ASK_MOBILE": "Aapka 10-digit WhatsApp/mobile number share karein, taaki hamare technical engineer aapse contact kar saken.",
        "ASK_CITY": "Aap kis city/area mein solar lagwana chahte hain? (PIN code pata ho to sath me likhein)",
        "INVALID_BILL": "Kripya apna monthly electricity bill sirf numbers mein batayein — jaise 3000.",
        "INVALID_NAME": "Kripya sirf apna naam likhiye — jaise: Pramod Kumar.",
        "INVALID_MOBILE": "Ye number sahi nahi lag raha. Kripya apna 10-digit mobile number dobara likhein — jaise 9876543210.",
        "FAQ_ONGRID": "On-Grid system aapke premises ko seedha bijli grid se jodta hai (net metering), jisse bill lagbhag zero ho jata hai. Power cut ke waqt isme backup nahi hota.",
        "FAQ_HYBRID": "Hybrid system mein grid saving ke sath battery backup milta hai. PM Surya Ghar subsidy solar plant par milti hai, bas battery storage ka cost alag se rehta hai.",
        "FAQ_DIFF": (
            "☀️ **On-Grid:** Bijli bill lagbhag zero karta hai (net-metering), par power cut mein backup nahi deta.\n"
            "🔋 **Hybrid:** Bill bachat ke sath battery backup bhi deta hai (power cut ke liye).\n"
            "💰 PM Surya Ghar subsidy solar plant par milti hai, battery ka kharch alag rehta hai."
        ),
        "DOCUMENTS_LIST": (
            "PM Surya Ghar subsidy ke liye zaroori documents:\n"
            "1. Latest Bijli Bill\n"
            "2. Identity & Address Proof (Aadhaar / Voter ID)\n"
            "3. Bank Passbook copy (subsidy direct transfer ke liye)\n\n"
            "⚠️ *Dhyan dein: Bijli bill aur Aadhaar/ID proof par naam match hona zaroori hai.* Hamari team portal registration mein poori help karti hai."
        ),
        "SENSITIVE_REPLY": "Bank EMI schemes, zero-down loan options aur exact quotation site survey par depend karti hai. Hamara installer aapse contact karke detail share karega.",
    }
}

SENSITIVE_KEYWORDS = [
    "emi", "loan", "installment", "warranty", "guarantee", "amc",
    "installation charge", "labour", "price", "cost", "kharch", "kharcha",
    "paisa", "kimat", "keemat"
]

DOCUMENT_KEYWORDS = ["document", "documents", "kagaz", "kagaj", "papers"]

def is_question(text: str) -> bool:
    tl = text.lower()
    if "?" in text:
        return True
    words = [
        "kya", "kaise", "kitna", "kitne", "kaunsa", "konsa", "kab", "kahan",
        "kyun", "kyu", "matlab", "explain", "difference", "farak", "antar", "batao",
        "subsidy", "chalega", "unit", "units", "what", "how", "why", "which",
        "space", "roof", "chhat", "area", "jagah", "kitni", "bijli", "generate",
        "generation", "banega", "karega", "produce", "power"
    ]
    return any(re.search(rf"\b{re.escape(w)}\b", tl) for w in words)

def is_sensitive_topic(text: str) -> bool:
    tl = text.lower()
    return any(k in tl for k in SENSITIVE_KEYWORDS)

def is_document_query(text: str) -> bool:
    tl = text.lower()
    return any(k in tl for k in DOCUMENT_KEYWORDS)

def parse_language(text: str) -> Optional[str]:
    tl = text.lower().strip()
    if tl in ["1", "english", "eng", "en"]:
        return "english"
    if tl in ["2", "hinglish", "hindi", "hin"]:
        return "hinglish"
    if re.search(r"\b(\d{3,6})\b", tl):
        return "hinglish"
    return None

def parse_bill(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{3,6})\b", text)
    return int(m.group(1)) if m else None

def parse_property_type(text: str) -> Optional[str]:
    tl = text.lower()
    if any(k in tl for k in ["dukan", "shop", "office", "commercial", "business", "showroom", "factory"]):
        return "Commercial"
    if any(k in tl for k in ["ghar", "makan", "residential", "home", "apna ghar"]):
        return "Residential"
    return None

def parse_system_type(text: str) -> Optional[str]:
    tl = text.lower()
    if any(k in tl for k in ["hybrid", "backup", "battery", "dono", "both"]):
        return "Hybrid"
    if any(k in tl for k in ["on-grid", "ongrid", "on grid", "grid", "bill kam", "zero bill"]):
        return "On-Grid"
    return None

def parse_name(text: str) -> Optional[str]:
    t = text.strip()
    if re.search(r"\d", t):
        return None
    words = t.split()
    stopwords = {"haan", "han", "yes", "ok", "theek", "thik", "nahi", "no", "ghar", "dukan", "home", "shop"}
    if 1 <= len(words) <= 4 and t.lower() not in stopwords:
        return t.title()
    return None

def parse_mobile(text: str) -> Optional[str]:
    m = re.search(r"\b([6-9]\d{9})\b", text)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None

def parse_city(text: str) -> Optional[str]:
    t = text.strip()
    if not t or is_question(t) or is_sensitive_topic(t) or is_document_query(t):
        return None
    return t.title()

FIELD_ORDER = ["language", "bill", "property_type", "system_type", "name", "mobile", "city"]
PARSERS = {
    "language": parse_language,
    "bill": parse_bill,
    "property_type": parse_property_type,
    "system_type": parse_system_type,
    "name": parse_name,
    "mobile": parse_mobile,
    "city": parse_city,
}

# ------------------------------------------------------------------
# FAQ ENGINE
# ------------------------------------------------------------------

def clean_output(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text.strip()

def build_faq_prompt(kw: Optional[int] = None, property_type: Optional[str] = None, lang: str = "hinglish") -> str:
    kw_val = kw if kw else 3
    kw_str = f"{kw_val} kW"
    units_min = kw_val * 4
    units_max = kw_val * 5
    is_comm = property_type and property_type.lower() == "commercial"
    is_eng = (lang == "english")

    lang_rule = (
        "Respond in fluent, concise, professional English (2-3 short lines max). Directly give the answer."
        if is_eng
        else "Roman Hinglish mein (Devanagari script BILKUL NAHI), 2-3 short lines mein direct aur clear jawab do."
    )

    if is_comm:
        load_context = f"""
Premises Context: Commercial Office/Shop/Showroom.
Load Handling for {kw_str}:
- 1-2 kW: Shop lighting, billing systems, fans, small commercial fridge.
- 3 kW: 1 Inverter AC (1.5 Ton) + showroom lighting & computers.
- 4-5 kW: 2 ACs (1.5 Ton) + office equipment, printers, water cooler.
- 7-10 kW: 3-4 ACs, heavy machinery, large commercial showroom.
Note: NEVER say 'ghar ka load' for commercial.
"""
    else:
        load_context = f"""
Premises Context: Residential Home.
Load Handling for {kw_str}:
- 1 kW: Basic home lights, fans, TV, Wi-Fi router.
- 2 kW: Refrigerator, air cooler, fans, TV, lights (No heavy AC).
- 3 kW: 1 AC (1.5 Ton) + complete household load.
- 4-5 kW: 2 ACs (1.5 Ton each) + complete household load.
- 7-10 kW: Multiple ACs, water pump, complete large bungalow load.
"""

    return f"""
Tum 'Solar Sathi' ho, ek direct aur honest solar consultant.
User ka recommended system size strictly hai: {kw_str} ({units_min}-{units_max} units/day).

{lang_rule}

Rooftop Space: Har 1 kW solar ke liye lagbhag 80-100 sq. ft. shadow-free jagah chahiye. ({kw_val} kW = ~{kw_val * 80}-{kw_val * 100} sq. ft.)

{load_context}

STRICT GUIDELINES:
1. Generation sawal par strictly {kw_str} system ke {units_min}-{units_max} units/day batayein.
2. Roman Hinglish mein English alphabets hi use karein.
3. No meta text, thinking tokens, or greetings. Directly answer the question.
"""

def _call_faq_ai(question: str, kw: Optional[int] = None, property_type: Optional[str] = None, lang: str = "hinglish") -> str:
    global ACTIVE_MODEL
    prompt = build_faq_prompt(kw, property_type, lang)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question},
    ]

    try:
        completion = client.chat.completions.create(
            model=ACTIVE_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=300,
        )
        return clean_output(completion.choices[0].message.content or "")
    except Exception as e:
        print(f"[Model Call Failed on {ACTIVE_MODEL}]: {e}")
        ACTIVE_MODEL = resolve_active_model()
        try:
            completion = client.chat.completions.create(
                model=ACTIVE_MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=300,
            )
            return clean_output(completion.choices[0].message.content or "")
        except Exception:
            return ""

async def get_faq_answer(question: str, kw: Optional[int], property_type: Optional[str], lang: str) -> str:
    raw = await asyncio.to_thread(_call_faq_ai, question, kw, property_type, lang)
    if raw:
        return raw

    if lang == "english":
        return "Our verified technical engineer will inspect load and generation specifics during site visit."
    return "Hamare technical engineer site visit ke dauran exact units generation aur load details aapse share karenge."

# ------------------------------------------------------------------
# LEAD SAVING
# ------------------------------------------------------------------

def upsert_lead(state: dict, complete: bool):
    mobile = state.get("mobile")
    if not mobile:
        return

    ensure_csv()
    prop = state.get("property_type")
    is_comm = prop and prop.lower() == "commercial"

    kw, central_sub = (None, None)
    if state.get("bill") is not None:
        kw, central_sub = estimate_kw_and_subsidy(state["bill"], prop)

    priority = get_priority(state.get("bill"), prop, state.get("system_type"), complete)
    region, discom, state_sub, _ = analyze_location_and_perks(
        state.get("city") or "", kw or 3, central_sub or 0, state.get("language") or "hinglish"
    )

    if is_comm:
        state_sub = 0

    total_benefit = (central_sub or 0) + state_sub
    roof_req = get_roof_area_sqft(kw) if kw else "N/A"

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        state.get("language") or "hinglish",
        state.get("name") or "Not Provided",
        mobile,
        state.get("city") or "Not Provided",
        f"{discom} ({region})",
        f"₹{state['bill']}" if state.get("bill") is not None else "Not Provided",
        f"{kw} kW" if kw else "Not Provided",
        roof_req,
        f"₹{central_sub:,}" if central_sub else "Not Provided",
        f"₹{state_sub:,}" if state_sub else "₹0",
        f"₹{total_benefit:,}" if total_benefit else "Not Provided",
        state.get("property_type") or "Not Provided",
        state.get("system_type") or "Not Provided",
        "COMPLETE" if complete else "PARTIAL",
        priority,
    ]

    with open(LEADS_FILE, mode="r", newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    if not reader:
        reader = [CSV_HEADERS]
    header, rows = reader[0], reader[1:]
    mobile_idx = header.index("Mobile") if "Mobile" in header else 3

    replaced = False
    for i, existing in enumerate(rows):
        if len(existing) > mobile_idx and existing[mobile_idx] == mobile:
            rows[i] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)

    with open(LEADS_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(rows)

# ------------------------------------------------------------------
# CONFIRMATION BUILDER (WITH DISCOM NET-METERING TRANSPARENCY)
# ------------------------------------------------------------------

def build_confirmation(state: dict) -> str:
    lang = state.get("language") or "hinglish"
    is_eng = (lang == "english")
    is_comm = (state.get("property_type") or "").lower() == "commercial"
    is_hybrid = (state.get("system_type") or "").lower() == "hybrid"

    kw, central_sub = estimate_kw_and_subsidy(state["bill"], state.get("property_type"))
    region, discom, state_sub, perk_msg = analyze_location_and_perks(state["city"], kw, central_sub, lang)
    roof_req = get_roof_area_sqft(kw)

    if is_comm:
        state_sub = 0

    total_sub = central_sub + state_sub

    if is_eng:
        prop_str = "Commercial (Shop/Office)" if is_comm else "Residential (Home)"
        if is_comm:
            benefit = "📈 Benefit: 40% Accelerated Tax Depreciation + Substantial Commercial Tariff Reductions"
        elif is_hybrid:
            benefit = (
                f"💰 Solar Subsidy: Up to ₹{total_sub:,} (PM Surya Ghar subsidy applies to solar capacity; "
                f"battery storage billed separately; subject to local DISCOM grid net-metering norms)"
            )
        else:
            if state_sub > 0:
                benefit = f"💰 Total Subsidy Benefit: Up to ₹{total_sub:,} (PM Surya Ghar + State Incentive)"
            else:
                benefit = f"💰 Central Subsidy: Up to ₹{central_sub:,} under PM Surya Ghar"

        perk_banner = f"\n{perk_msg}\n" if perk_msg else ""

        return (
            f"Thank you, {state['name']}! 🙏 Your personalized solar plan has been generated:\n\n"
            f"☀️ Recommended System: ~{kw} kW ({state['system_type']})\n"
            f"🏢 Category: {prop_str}\n"
            f"📍 Location: {state['city']} [{discom}]\n"
            f"🏠 Required Shadow-Free Roof: ~{roof_req}\n"
            f"{benefit}\n"
            f"⚡ Bill Impact: Up to 80%–90% monthly bill reduction*\n"
            f"{perk_banner}\n"
            f"Our verified technical engineer will contact you at `{state['mobile']}` to schedule your free rooftop survey. "
            f"Have a sunny day! ☀️\n\n"
            f"Feel free to ask questions regarding documents, roof space, or EMI options!\n\n"
            f"*Disclaimer: Actual bill reduction depends on rooftop orientation, shading, and local DISCOM net-metering regulations."
        )
    else:
        prop_str = "Commercial (Dukan/Office)" if is_comm else "Residential (Ghar)"
        if is_comm:
            benefit = "📈 Benefit: 40% Tax Depreciation benefit + commercial unit rates par maximum bachat"
        elif is_hybrid:
            benefit = (
                f"💰 Solar Subsidy: Lagbhag ₹{total_sub:,} tak (PM Surya Ghar rules ke mutabiq plant par subsidy; "
                f"battery cost alag rehti hai aur grid net-metering local DISCOM approval par depend karti hai)"
            )
        else:
            if state_sub > 0:
                benefit = f"💰 Total Subsidy Benefit: Lagbhag ₹{total_sub:,} tak (PM Surya Ghar + State Scheme)"
            else:
                benefit = f"💰 Central Subsidy: Lagbhag ₹{central_sub:,} tak (PM Surya Ghar Yojana)"

        perk_banner = f"\n{perk_msg}\n" if perk_msg else ""

        return (
            f"Dhanyawad {state['name']} ji! 🙏 Aapki solar details note ho gayi hain:\n\n"
            f"☀️ Recommended System: Lagbhag {kw} kW ({state['system_type']})\n"
            f"🏢 Property: {prop_str}\n"
            f"📍 Location: {state['city']} [{discom}]\n"
            f"🏠 Chhat Par Jagah Chahiye: Lagbhag ~{roof_req} (Shadow-free)\n"
            f"{benefit}\n"
            f"⚡ Bijli Bill Impact: Monthly bill mein lagbhag 80%–90% tak kami aane ka anuman*\n"
            f"{perk_banner}\n"
            f"Hamari technical team aapse `{state['mobile']}` par contact karke free site survey schedule karegi. "
            f"Aapka din shubh ho! ☀️\n\n"
            f"Agar chahein to aap abhi bhi documents, chhat ki jagah ya load ke baare mein pooch sakte hain!\n\n"
            f"*Disclaimer: Asli bachat aur generation chhat ki disha, dhoop aur local DISCOM ke net-metering niyamon par depend karti hai."
        )

# ------------------------------------------------------------------
# STATE MACHINE LOGIC
# ------------------------------------------------------------------

def build_state(customer_messages: List[str]):
    state = {f: None for f in FIELD_ORDER}

    def next_field():
        for f in FIELD_ORDER:
            if state[f] is None:
                return f
        return None

    last_outcome = None

    for i, msg in enumerate(customer_messages):
        field = next_field()
        is_last = i == len(customer_messages) - 1
        if field is None:
            break

        if field == "language":
            lang_val = parse_language(msg)
            if lang_val:
                state["language"] = lang_val
                bill_val = parse_bill(msg)
                if bill_val:
                    state["bill"] = bill_val
                if is_last:
                    last_outcome = ("filled", "bill" if bill_val else "language")
                continue

        if is_document_query(msg):
            if is_last:
                last_outcome = ("document", field, msg)
            continue

        if is_sensitive_topic(msg):
            if is_last:
                last_outcome = ("sensitive", field, msg)
            continue

        value = None if is_question(msg) else PARSERS[field](msg)
        if value is not None:
            state[field] = value
            if is_last:
                last_outcome = ("filled", field)
        else:
            if is_last:
                if is_question(msg):
                    last_outcome = ("faq", field, msg)
                else:
                    last_outcome = ("invalid", field)

    return state, last_outcome, next_field()

async def process_message(history: List[HistoryMessage], message: str, bg_tasks: BackgroundTasks):
    customer_messages = [h.text for h in history if h.sender == "user"] + [message]
    state, outcome, pending_field = build_state(customer_messages)
    lang = state.get("language") or "hinglish"
    t = TEMPLATES[lang]

    kw_val = None
    if state.get("bill"):
        kw_val, _ = estimate_kw_and_subsidy(state["bill"], state.get("property_type"))

    if outcome is not None and outcome[0] == "filled":
        field_filled = outcome[1]
        complete = all(state[f] is not None for f in FIELD_ORDER)

        if state.get("mobile"):
            upsert_lead(state, complete)
            if field_filled == "mobile" and not complete:
                bg_tasks.add_task(send_delayed_incomplete_alert, dict(state), 60)

        if complete:
            if state.get("mobile"):
                COMPLETED_MOBILES.add(state["mobile"])
            # Background alerts: Telegram & Official WhatsApp (Meta Cloud API)
            bg_tasks.add_task(send_telegram_alert, state, True)
            bg_tasks.add_task(send_whatsapp_alert, state)
            return build_confirmation(state), state

        if field_filled in ["language", "bill"]:
            if state.get("bill"):
                kw, _ = estimate_kw_and_subsidy(state["bill"])
                if lang == "english":
                    bill_msg = f"Based on your ₹{state['bill']} monthly bill, approximately a {kw} kW solar system is recommended.\n\n{t['ASK_PROPERTY']}"
                else:
                    bill_msg = f"Aapke ₹{state['bill']} monthly bill ke hisaab se lagbhag {kw} kW ka system suitable rahega.\n\n{t['ASK_PROPERTY']}"
                return bill_msg, None
            return t["ASK_BILL"], None

        if field_filled == "property_type":
            is_comm = (state.get("property_type") or "").lower() == "commercial"
            kw, sub = estimate_kw_and_subsidy(state["bill"])
            if lang == "english":
                prefix = (
                    "Commercial connections qualify for 40% accelerated tax depreciation benefits rather than central subsidy.\n\n"
                    if is_comm else
                    f"Residential homes qualify for up to ₹{sub:,} under the PM Surya Ghar Subsidy Scheme! 🎉\n\n"
                )
            else:
                prefix = (
                    "Commercial (Dukan/Office) par 40% tax depreciation benefit milta hai aur commercial tariff par maximum bachat hoti hai.\n\n"
                    if is_comm else
                    f"Residential (Ghar) ke liye aapko PM Surya Ghar Yojana ke tahat lagbhag ₹{sub:,} tak ki subsidy milti hai! 🎉\n\n"
                )
            return prefix + t["ASK_SYSTEM_TYPE"], None

        return t[f"ASK_{pending_field.upper()}"], None

    if outcome is not None and outcome[0] == "invalid":
        field = outcome[1]
        inv_key = f"INVALID_{field.upper()}"
        ask_key = f"ASK_{field.upper()}"
        return t.get(inv_key, t.get(ask_key, GREETING_MESSAGE)), None

    if outcome is not None and outcome[0] == "document":
        field = outcome[1]
        ask_key = f"ASK_{field.upper()}"
        return f"{t['DOCUMENTS_LIST']}\n\n{t.get(ask_key, '')}", None

    if outcome is not None and outcome[0] == "sensitive":
        field = outcome[1]
        ask_key = f"ASK_{field.upper()}"
        return f"{t['SENSITIVE_REPLY']}\n\n{t.get(ask_key, '')}", None

    # FAQ Handler
    if outcome is not None and outcome[0] == "faq":
        field, question = outcome[1], outcome[2]
        tl = question.lower()
        
        if any(k in tl for k in ["difference", "antar", "farak", "comparison"]):
            ans = t.get("FAQ_DIFF", f"{t['FAQ_ONGRID']}\n\n{t['FAQ_HYBRID']}")
        elif "hybrid" in tl and "grid" not in tl:
            ans = t["FAQ_HYBRID"]
        elif "grid" in tl and "hybrid" not in tl:
            ans = t["FAQ_ONGRID"]
        else:
            ans = await get_faq_answer(question, kw_val, state.get("property_type"), lang)
            
        ask_key = f"ASK_{field.upper()}"
        return f"{ans}\n\n{t.get(ask_key, '')}", None

    # Post Completion (Deterministic Daily Units Handler)
    if pending_field is None:
        tl = message.lower()
        if is_document_query(message):
            return t["DOCUMENTS_LIST"], None
        if is_sensitive_topic(message):
            return t["SENSITIVE_REPLY"], None
            
        # PURE PYTHON DETERMINISTIC UNITS (Zero AI/API Failures)
        if any(w in tl for w in ["unit", "units", "generate", "generation", "bijli"]):
            kw_now = kw_val if kw_val else 3
            u_min = kw_now * 4
            u_max = kw_now * 5
            if lang == "english":
                return f"A {kw_now} kW solar system generates approximately **{u_min} to {u_max} units per day** under 4-5 hours of direct sunlight.\n\nOur certified technician will verify site feasibility during survey. 🙏", None
            else:
                return f"Aapke {kw_now} kW system se rozana lagbhag **{u_min} se {u_max} units bijli** banegi (average 4-5 ghante achhi dhoop par).\n\nHamare technician site survey par exact load verify karenge. 🙏", None

        ans = await get_faq_answer(message, kw_val, state.get("property_type"), lang)
        close_note = " Our technician will review this during site visit. 🙏" if lang == "english" else " Hamare installer site visit par detail denge. 🙏"
        return f"{ans}\n\n{close_note}", None

    if pending_field == "language":
        return GREETING_MESSAGE, None

    return t[f"ASK_{pending_field.upper()}"], None

# ------------------------------------------------------------------
# APP ENTRY
# ------------------------------------------------------------------

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks):
    try:
        reply, _ = await process_message(req.history, req.message, bg_tasks)
        return {"reply": reply}
    except Exception as e:
        print(f"Chat Endpoint Error: {e}")
        return {"reply": "Sorry, an unexpected technical issue occurred. Please try sending your last answer again."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
