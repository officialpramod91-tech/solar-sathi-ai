"""
Solar Sathi AI — PRODUCTION FINAL VERSION (v3.7 — Residential vs Commercial Smart Routing)
"""

import os
import re
import csv
import asyncio
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

# ------------------------------------------------------------------
# SETUP & CONFIGURATION (INDIAN TIMEZONE SET)
# ------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise RuntimeError("GROQ_API_KEY nahi mili! .env file check karein.")

client = Groq(api_key=API_KEY)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FAQ_MODEL_PRIORITY = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "moonshotai/kimi-k2-instruct-0905",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


def resolve_faq_model() -> str:
    try:
        available = {m.id for m in client.models.list().data}
        for model in FAQ_MODEL_PRIORITY:
            if model in available:
                print(f"[Model Resolution] Using: {model}")
                return model
        print(f"[Model Resolution] None of preferred models found. Available: {available}")
    except Exception as e:
        print(f"[Model Resolution Failed]: {e}")
    return FAQ_MODEL_PRIORITY[0]


FAQ_MODEL = resolve_faq_model()

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "Timestamp", "Name", "Mobile", "City", "Monthly Bill",
    "Estimated kW", "Est. Subsidy", "Property Type", "System Type",
    "Status", "Priority",
]


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
# DETERMINISTIC HELPERS
# ------------------------------------------------------------------

def estimate_kw_and_subsidy(bill: int, property_type: Optional[str] = None):
    # Bill ke hisaab se accurate kW sizing
    if bill < 1500:
        kw = 1
        sub = 30000
    elif bill <= 3000:
        kw = 2
        sub = 60000
    elif bill <= 4500:
        kw = 3
        sub = 78000
    elif bill <= 6500:
        kw = 5
        sub = 78000
    elif bill <= 9000:
        kw = 7
        sub = 78000
    else:
        kw = 10
        sub = 78000

    # Commercial property par central subsidy lagu nahi hoti
    if property_type and property_type.lower() == "commercial":
        return kw, 0
    return kw, sub


def get_priority(bill: Optional[int], prop: Optional[str], complete: bool) -> str:
    if not complete:
        return "INCOMPLETE — FOLLOW UP"
    if prop and prop.lower() == "commercial":
        return "HIGH PRIORITY (Commercial Client)"
    if bill is not None and bill >= 4500:
        return "HIGH PRIORITY"
    if bill is not None and bill >= 2000:
        return "MEDIUM PRIORITY"
    return "STANDARD"


# ------------------------------------------------------------------
# TELEGRAM ALERT NOTIFIER
# ------------------------------------------------------------------

def send_telegram_alert(state: dict, complete: bool = True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Alert Skipped]: Credentials missing in .env")
        return

    prop = state.get("property_type")
    is_comm = prop and prop.lower() == "commercial"
    
    kw = None
    subsidy = None
    if state.get("bill") is not None:
        kw, subsidy = estimate_kw_and_subsidy(state["bill"], prop)

    priority = get_priority(state.get("bill"), prop, complete)

    if complete:
        header_tag = "🚨 *NEW QUALIFIED SOLAR LEAD!* ☀️"
        status_label = "COMPLETE LEAD"
    else:
        header_tag = "🟡 *NEW INCOMPLETE LEAD (FOLLOW-UP!)* ⚠️"
        status_label = "PARTIAL (City Pending)"

    name = state.get("name") or "Not Provided"
    mobile = state.get("mobile") or "Not Provided"
    city = state.get("city") or "Pending"
    bill_val = f"₹{state['bill']}" if state.get("bill") is not None else "N/A"
    prop_val = "Commercial (Dukan/Office)" if is_comm else (prop or "N/A")
    sys_type = state.get("system_type") or "N/A"
    sys_info = f"{kw} kW ({sys_type})" if kw else "Pending"
    
    if is_comm:
        subsidy_info = "N/A (Tax/Tariff Benefits)"
    else:
        subsidy_info = f"₹{subsidy}" if subsidy else "Pending"
    
    time_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")

    text = (
        f"{header_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:* {name}\n"
        f"📞 *Mobile:* `{mobile}`\n"
        f"📍 *City / PIN:* {city}\n"
        f"⚡ *Monthly Bill:* {bill_val}\n"
        f"🏢 *Property:* {prop_val}\n"
        f"🔋 *System:* {sys_info}\n"
        f"💰 *Est. Subsidy:* {subsidy_info}\n"
        f"🎯 *Status:* {status_label}\n"
        f"📊 *Priority:* {priority}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {time_str}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        res = requests.post(url, json=payload, timeout=6)
        if res.status_code == 200:
            lead_kind = "Complete" if complete else "Partial"
            print(f"[Telegram Alert Sent]: {lead_kind} lead for {mobile} notified.")
        else:
            print(f"[Telegram Error]: Status {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[Telegram Notification Failed]: {e}")


# ------------------------------------------------------------------
# STATIC QUESTION TEMPLATES
# ------------------------------------------------------------------

ASK_BILL = "Aapka monthly electricity bill lagbhag kitna aata hai? (approx amount bata dijiye)"
ASK_PROPERTY = "Yeh solar ghar ke liye chahiye ya dukan/office ke liye?"
ASK_SYSTEM_TYPE = "Sirf bill kam karne ke liye On-grid system chahiye, ya power cut mein bhi backup ke liye Hybrid system?"
ASK_NAME = "Aapka naam bata dijiye."
ASK_MOBILE = "Aapka 10-digit WhatsApp/mobile number share kar dijiye, taaki hamari team aapse contact kar sake."
ASK_CITY = "Aap kis city/area mein solar lagwana chahte hain? (PIN code pata ho to sath me likhein)"

INVALID_BILL = "Kripya apna monthly electricity bill (Rupees mein, sirf number) batayein — jaise 3000."
INVALID_NAME = "Kripya sirf apna naam likhiye — jaise: Pramod Kumar."
INVALID_MOBILE = "Ye number sahi nahi lag raha. Kripya apna 10-digit mobile number dobara likhein — jaise 9876543210."

FAQ_ONGRID = (
    "On-Grid system aapke premises ko seedha bijli grid se jodta hai. Jo extra bijli "
    "panels banate hain wo grid ko chali jaati hai (net metering) aur bill lagbhag zero hota hai — "
    "lekin power cut ke time ismein normally backup nahi milta."
)
FAQ_HYBRID = (
    "Hybrid system mein On-Grid ka fayda milta hai aur battery backup bhi hota hai, isliye "
    "power cut ke time bhi zaroori appliances aur equipment chalte rehte hain. Battery ki wajah se "
    "iski cost On-Grid se thodi zyada hoti hai."
)

FAQ_SENSITIVE_TOPIC = (
    "Iski exact detail (jaise documents, EMI eligibility, final pricing, warranty terms) "
    "scheme, bank aur system ke hisaab se alag hoti hai. Hamari team aapko site "
    "survey/call ke time exact aur latest detail confirm karegi, taaki koi confusion na ho."
)
SENSITIVE_KEYWORDS = [
    "document", "kagaz", "kagaj", "emi", "loan", "installment",
    "warranty", "guarantee", "amc", "maintenance",
    "installation charge", "labour", "labor",
    "price", "cost", "kharch", "kharcha", "paisa", "kimat", "keemat",
    "eligib",
]


def is_question(text: str) -> bool:
    tl = text.lower()
    if "?" in text:
        return True
    question_words = [
        "kya", "kaise", "kitna", "kitne", "kaunsa", "konsa", "kab", "kahan",
        "kyun", "kyu", "matlab", "samjha", "samajh", "explain", "difference",
        "farak", "batao", "bataye", "subsidy", "chalega", "chalenge", "unit", "units",
    ]
    return any(re.search(rf"\b{re.escape(w)}\b", tl) for w in question_words)


def is_sensitive_topic(text: str) -> bool:
    tl = text.lower()
    return any(k in tl for k in SENSITIVE_KEYWORDS)


# ------------------------------------------------------------------
# FIELD PARSERS
# ------------------------------------------------------------------

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
    if any(k in tl for k in ["hybrid", "backup", "battery", "dono"]):
        return "Hybrid"
    if any(k in tl for k in ["on-grid", "ongrid", "on grid", "grid", "bill kam"]):
        return "On-Grid"
    return None


def parse_name(text: str) -> Optional[str]:
    t = text.strip()
    if re.search(r"\d", t):
        return None
    words = t.split()
    stopwords = {"haan", "han", "yes", "ok", "theek", "thik", "nahi", "no", "ghar", "dukan"}
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
    if not t or is_question(t) or is_sensitive_topic(t):
        return None
    return t.title()


FIELD_ORDER = ["bill", "property_type", "system_type", "name", "mobile", "city"]
PARSERS = {
    "bill": parse_bill,
    "property_type": parse_property_type,
    "system_type": parse_system_type,
    "name": parse_name,
    "mobile": parse_mobile,
    "city": parse_city,
}
INVALID_MESSAGES = {"bill": INVALID_BILL, "name": INVALID_NAME, "mobile": INVALID_MOBILE}
ASK_MESSAGES = {
    "bill": ASK_BILL, "property_type": ASK_PROPERTY, "system_type": ASK_SYSTEM_TYPE,
    "name": ASK_NAME, "mobile": ASK_MOBILE, "city": ASK_CITY,
}


# ------------------------------------------------------------------
# AI FAQ HANDLER
# ------------------------------------------------------------------

def build_faq_prompt(kw: Optional[int] = None) -> str:
    kw_val = kw if kw else 3
    kw_str = f"{kw_val} kW"
    units_min = kw_val * 4
    units_max = kw_val * 5
    
    return f"""
Tum 'Solar Sathi' ho, ek friendly expert solar consultant.
Customer ne ek general sawal poocha hai.
Customer ka recommended system size STRICTLY hai: {kw_str}.
Is {kw_str} system se rozana lagbhag {units_min}-{units_max} units generate honge.

Roman Hinglish mein (Devanagari nahi), 2-3 short lines mein clear jawab do.

System capacity load guidelines:
- 1 kW ({units_min}-{units_max} units/day): Lights, fans, TV aur basic appliances.
- 2 kW ({units_min}-{units_max} units/day): Fridge, washing machine, cooler, lights aur fans (bina AC).
- 3 kW ({units_min}-{units_max} units/day): 1 AC (1.5 ton), fridge, TV, lights aur fans.
- 5 kW ({units_min}-{units_max} units/day): 2 ACs (1.5 ton each), fridge, washing machine, water pump aur poora load.
- 7 kW to 10 kW ({units_min}-{units_max} units/day): 3-4 ACs, heavy commercial machinery ya large office.

STRICT INSTRUCTIONS:
1. Agar sawal units generation ya appliance load ka hai, toh sirf {kw_str} ({units_min}-{units_max} units/day) ka hi figure batao!
2. Direct, polite aur accurate raho.
"""


def _call_faq_ai(question: str, kw: Optional[int] = None) -> str:
    global FAQ_MODEL
    system_prompt = build_faq_prompt(kw)
    kwargs = dict(
        model=FAQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.2,
        max_tokens=220,
    )
    if FAQ_MODEL.startswith("qwen/"):
        kwargs["reasoning_effort"] = "none"
        kwargs["reasoning_format"] = "hidden"

    try:
        completion = client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content or ""
    except Exception as e:
        print(f"[Primary FAQ model failed]: {e}")
        FAQ_MODEL = resolve_faq_model()
        kwargs["model"] = FAQ_MODEL
        kwargs.pop("reasoning_effort", None)
        kwargs.pop("reasoning_format", None)
        if FAQ_MODEL.startswith("qwen/"):
            kwargs["reasoning_effort"] = "none"
            kwargs["reasoning_format"] = "hidden"
        completion = client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content or ""


def clean_output(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def get_faq_answer(question: str, kw: Optional[int] = None) -> str:
    try:
        raw = await asyncio.to_thread(_call_faq_ai, question, kw)
        return clean_output(raw) or "Hamari technical team aapse call par detail se discuss karegi."
    except Exception as e:
        print(f"[FAQ AI Error]: {e}")
        return "Hamari technical team aapse call par detail se discuss karegi."


# ------------------------------------------------------------------
# LEAD SAVING — Upsert by Mobile with IST
# ------------------------------------------------------------------

def upsert_lead(state: dict, complete: bool):
    mobile = state.get("mobile")
    if not mobile:
        return

    ensure_csv()
    kw, subsidy = (None, None)
    if state.get("bill") is not None:
        kw, subsidy = estimate_kw_and_subsidy(state["bill"], state.get("property_type"))
    priority = get_priority(state.get("bill"), state.get("property_type"), complete)

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        state.get("name") or "Not Provided",
        mobile,
        state.get("city") or "Not Provided",
        f"₹{state['bill']}" if state.get("bill") is not None else "Not Provided",
        f"{kw} kW" if kw else "Not Provided",
        f"₹{subsidy}" if subsidy else "Not Provided",
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
    mobile_idx = header.index("Mobile") if "Mobile" in header else 2

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


def build_confirmation(state: dict) -> str:
    is_comm = (state.get("property_type") or "").lower() == "commercial"
    kw, subsidy = estimate_kw_and_subsidy(state["bill"], state.get("property_type"))
    
    if is_comm:
        prop_str = "Commercial (Dukan/Office)"
        benefit_line = "📈 Benefit: Commercial Tax Benefits (40% Depreciation) + Bill Savings (No Subsidy)"
        team_detail = "commercial tax benefits aur ROI ki poori detail degi"
    else:
        prop_str = "Residential (Ghar)"
        benefit_line = f"💰 Estimated Subsidy: PM Surya Ghar Yojana ke tahat lagbhag ₹{subsidy} tak (final subsidy survey ke baad confirm hogi)"
        team_detail = "free site survey schedule karegi"

    return (
        f"Dhanyawad {state['name']} ji! 🙏 Aapki details note ho gayi hain:\n\n"
        f"☀️ System: lagbhag {kw} kW ({state['system_type']})\n"
        f"🏢 Property: {prop_str}\n"
        f"📍 Location: {state['city']}\n"
        f"{benefit_line}\n\n"
        f"Humari team aapse {state['mobile']} par contact karke {team_detail}. "
        f"Aapka din shubh ho! ☀️\n\n"
        f"Agar chahein to abhi bhi pooch sakte hain:\n"
        f"1️⃣ EMI, loan ya documents ke baare mein\n"
        f"2️⃣ Solar system se judi koi aur jaankari\n\n"
        f"Bas apna sawal likh dijiye! 😊"
    )


def build_bill_response(bill: int) -> str:
    kw, _ = estimate_kw_and_subsidy(bill)
    return (
        f"Aapke ₹{bill} ke monthly bill ke hisaab se lagbhag {kw} kW ka solar system suitable rahega. "
        f"(Final size site survey ke baad confirm hoti hai).\n\n{ASK_PROPERTY}"
    )


def build_system_type_response(state: dict) -> str:
    is_comm = (state.get("property_type") or "").lower() == "commercial"
    kw, subsidy = estimate_kw_and_subsidy(state["bill"])
    
    if is_comm:
        prefix = (
            "Commercial properties (Dukan/Office/Factory) par PM Surya Ghar yojana ki subsidy lagu nahi hoti, "
            "lekin aapko 40% tak ka Income Tax Depreciation Benefit milega aur aapka commercial electricity bill bachat maximum hogi! 💰\n\n"
        )
    else:
        prefix = (
            f"Residential (Ghar) ke liye aapko PM Surya Ghar Yojana ke tahat maximum ₹{subsidy} tak ki government subsidy mil sakti hai. 🎉\n\n"
        )
    return prefix + ASK_SYSTEM_TYPE


# ------------------------------------------------------------------
# CONVERSATION STATE MACHINE
# ------------------------------------------------------------------

def extract_bill_from_history(customer_messages: List[str]) -> Optional[int]:
    for msg in customer_messages:
        b = parse_bill(msg)
        if b is not None:
            return b
    return None


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

    current_kw = None
    bill_found = state.get("bill") or extract_bill_from_history(customer_messages)
    if bill_found is not None:
        current_kw, _ = estimate_kw_and_subsidy(bill_found, state.get("property_type"))

    if outcome is not None and outcome[0] == "filled":
        field_filled = outcome[1]
        complete = all(state[f] is not None for f in FIELD_ORDER)

        if state.get("mobile"):
            upsert_lead(state, complete)
            if field_filled == "mobile" and not complete:
                bg_tasks.add_task(send_telegram_alert, state, False)

        if complete:
            bg_tasks.add_task(send_telegram_alert, state, True)
            return build_confirmation(state), state

        if field_filled == "bill":
            return build_bill_response(state["bill"]), None

        if field_filled == "property_type":
            return build_system_type_response(state), None

        return ASK_MESSAGES[pending_field], None

    if outcome is not None and outcome[0] == "invalid":
        field = outcome[1]
        return INVALID_MESSAGES.get(field, ASK_MESSAGES[field]), None

    if outcome is not None and outcome[0] == "sensitive":
        field = outcome[1]
        return f"{FAQ_SENSITIVE_TOPIC}\n\n{ASK_MESSAGES[field]}", None

    if outcome is not None and outcome[0] == "faq":
        field, question = outcome[1], outcome[2]
        tl = question.lower()
        on_grid_hybrid_related = any(
            k in tl for k in ["hybrid", "on-grid", "on grid", "ongrid", "grid", "battery", "backup"]
        )
        if field == "system_type" and on_grid_hybrid_related:
            if "hybrid" in tl and "grid" not in tl:
                answer = FAQ_HYBRID
            elif "grid" in tl:
                answer = FAQ_ONGRID
            else:
                answer = f"{FAQ_ONGRID}\n\n{FAQ_HYBRID}"
        else:
            answer = await get_faq_answer(question, kw=current_kw)
        return f"{answer}\n\n{ASK_MESSAGES[field]}", None

    # Post-completion handling
    if pending_field is None:
        if is_sensitive_topic(message):
            return (
                f"{FAQ_SENSITIVE_TOPIC}\n\n"
                f"Humara installer aapki site visit ke time iski poori detail dega. 🙏"
            ), None

        tl = message.lower()
        on_grid_hybrid_related = any(
            k in tl for k in ["hybrid", "on-grid", "on grid", "ongrid", "grid", "battery", "backup"]
        )
        if on_grid_hybrid_related:
            if "hybrid" in tl and "grid" not in tl:
                answer = FAQ_HYBRID
            elif "grid" in tl:
                answer = FAQ_ONGRID
            else:
                answer = f"{FAQ_ONGRID}\n\n{FAQ_HYBRID}"
            return f"{answer}\n\nHumara installer site visit ke time iski poori detail dega. 🙏", None

        if is_question(message):
            answer = await get_faq_answer(message, kw=current_kw)
            return f"{answer}\n\nHumara installer site visit ke time iski poori detail dega. 🙏", None

        return "Aapki details already register ho chuki hain. Hamari team jald hi aapse contact karegi. 🙏", None

    return ASK_MESSAGES[pending_field], None


# ------------------------------------------------------------------
# API ENDPOINT
# ------------------------------------------------------------------

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks):
    try:
        reply, _completed_state = await process_message(req.history, req.message, bg_tasks)
        return {"reply": reply}
    except Exception as e:
        print(f"Chat Endpoint Error: {e}")
        return {"reply": "Maaf kijiye, thodi technical dikkat aa gayi. Kripya apna pichla jawab dobara likh dijiye."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
