"""
Solar Sathi AI — v7.5 Enterprise Production Release
- Multi-Tenant Engine: Pragati Solar Hub (Kanpur Lead-Lock) & Other Clients
- Fixes Post-Completion Loop Bug (Accurate Unit Generation & FAQ Answers)
- Indian Currency Formatting (₹1,08,000 instead of ₹108,000)
- Immediate Partial Lead Alert on Mobile Capture
- 24/7 Keep-Alive Zero Cold-Start Health Check
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID", "1358122214045364")
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP", "918173031237")
PRAGATI_WHATSAPP = os.getenv("PRAGATI_WHATSAPP")
LIGHTSOLAR_WHATSAPP = os.getenv("LIGHTSOLAR_WHATSAPP")

CLIENT_ROUTER = {
    "pragati": PRAGATI_WHATSAPP,
    "lightsolar": LIGHTSOLAR_WHATSAPP,
}

CANDIDATE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "gemma2-9b-it"
]

def resolve_active_model() -> str:
    try:
        remote_models = {m.id for m in client.models.list().data}
        for m in CANDIDATE_MODELS:
            if m in remote_models:
                return m
        return next(iter(remote_models))
    except Exception:
        return "llama3-8b-8192"

ACTIVE_MODEL = resolve_active_model()

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "Timestamp", "Client", "Language", "Name", "Mobile", "City", "State/DISCOM", "Monthly Bill",
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
    client: Optional[str] = "default"

# ------------------------------------------------------------------
# INDIAN CURRENCY FORMATTER
# ------------------------------------------------------------------

def format_inr(number: int) -> str:
    s = str(number)
    if len(s) <= 3:
        return f"₹{s}"
    last_three = s[-3:]
    remaining = s[:-3]
    groups = []
    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.insert(0, remaining)
    return f"₹{','.join(groups)},{last_three}"

# ------------------------------------------------------------------
# KANPUR GEOGRAPHIC & PINCODE INTELLIGENCE
# ------------------------------------------------------------------

KANPUR_LOCALITIES = [
    "gujaini", "barra", "ratanlal nagar", "govind nagar", "vijay nagar",
    "bhaunti", "swaroop nagar", "tilak nagar", "civil lines", "saket nagar",
    "shyam nagar", "azad nagar", "vishnu puri", "kalyanpur", "singhpur",
    "kidwai nagar", "pandu nagar", "sharda nagar", "panki", "kanpur"
]

KANPUR_PINS = [
    "208022", "208027", "208006", "208005", "209305", "208002",
    "208001", "208014", "208013", "208017", "208011", "208025", "208020"
]

KANPUR_OUTSKIRTS = ["bilhaur", "rasulabad", "ghatampur", "hamirpur", "unnao"]

def analyze_location_and_perks(city_text: str, kw: int, central_sub: int) -> Tuple[str, str, int, str]:
    ct = city_text.lower().strip()
    is_kanpur = any(re.search(rf"\b{re.escape(loc)}\b", ct) for loc in KANPUR_LOCALITIES) or any(re.search(rf"\b{pin}\b", ct) for pin in KANPUR_PINS)

    state_sub = min(kw * 15000, 30000)
    total_sub = central_sub + state_sub

    if is_kanpur:
        return "Kanpur, UP", "KESCO (Kanpur Electricity Supply Company)", state_sub, f"Total {format_inr(total_sub)} Subsidy"

    if any(re.search(rf"\b{re.escape(out)}\b", ct) for out in KANPUR_OUTSKIRTS):
        matched = next(out for out in KANPUR_OUTSKIRTS if out in ct).title()
        return f"{matched}, UP", "UPNEDA (MVVNL / DVVNL)", state_sub, f"Total {format_inr(total_sub)} Subsidy"

    return "Uttar Pradesh", "UPNEDA", state_sub, f"Total {format_inr(total_sub)} Subsidy"

# ------------------------------------------------------------------
# SYSTEM SIZING & MATH
# ------------------------------------------------------------------

def estimate_kw_and_subsidy(bill: int, property_type: Optional[str] = None) -> Tuple[int, int]:
    if bill <= 1500: kw, sub = 1, 30000
    elif bill <= 2800: kw, sub = 2, 60000
    elif bill <= 4500: kw, sub = 3, 78000
    elif bill <= 6500: kw, sub = 4, 78000
    elif bill <= 8500: kw, sub = 5, 78000
    else: kw, sub = 7, 78000

    if property_type and property_type.lower() == "commercial":
        return kw, 0
    return kw, sub

def get_roof_area_sqft(kw: int) -> str:
    return f"{kw * 80} - {kw * 100} sq. ft."

# ------------------------------------------------------------------
# TELEGRAM & META WHATSAPP ALERTS
# ------------------------------------------------------------------

def send_telegram_alert(state: dict, complete: bool = True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    client_tag = (state.get("client") or "default").upper()
    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000, state.get("property_type"))
    region, discom, state_sub, _ = analyze_location_and_perks(state.get("city") or "Kanpur", kw, central_sub)
    total_benefit = central_sub + state_sub

    header = f"🚨 *VERIFIED SOLAR LEAD [{client_tag}]!* ☀️" if complete else f"🔥 *HOT LEAD (PHONE CAPTURED) [{client_tag}]!* 📞"

    text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Customer:* {state.get('name') or 'In Progress'}\n"
        f"📞 *Mobile:* `{state.get('mobile')}`\n"
        f"📍 *Area/PIN:* {state.get('city') or 'Area Pending'}\n"
        f"⚡ *DISCOM:* {discom} ({region})\n"
        f"💡 *Bill:* {format_inr(state.get('bill') or 0)} (~{kw} kW Recommended)\n"
        f"💰 *Total Subsidy Benefit:* {format_inr(total_benefit)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}\n"
        f"👉 *Action:* Turant call/WhatsApp karke visit book karein!"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=6)
    except Exception:
        pass

def send_whatsapp_alert(state: dict):
    if not META_ACCESS_TOKEN or not META_PHONE_ID:
        return

    client_key = (state.get("client") or "default").lower().strip()
    target_whatsapp = CLIENT_ROUTER.get(client_key) or ADMIN_WHATSAPP
    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000, state.get("property_type"))
    region, discom, state_sub, _ = analyze_location_and_perks(state.get("city") or "Kanpur", kw, central_sub)
    total_benefit = central_sub + state_sub

    alert_text = (
        f"🚨 *NEW SOLAR INQUIRY [{client_key.upper()}]!* ☀️\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Customer:* {state.get('name')}\n"
        f"📞 *Mobile:* {state.get('mobile')}\n"
        f"📍 *Location:* {state.get('city')}\n"
        f"⚡ *DISCOM:* {discom} ({region})\n"
        f"💡 *Monthly Bill:* {format_inr(state.get('bill') or 0)}\n"
        f"☀️ *Recommended System:* {kw} kW\n"
        f"💰 *Total Subsidy:* {format_inr(total_benefit)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}"
    )

    url = f"https://graph.facebook.com/v20.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        requests.post(url, json={"messaging_product": "whatsapp", "to": target_whatsapp, "type": "text", "text": {"body": alert_text}}, headers=headers, timeout=8)
    except Exception:
        pass

def upsert_lead(state: dict, complete: bool):
    mobile = state.get("mobile")
    if not mobile:
        return
    ensure_csv()

    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000, state.get("property_type"))
    region, discom, state_sub, _ = analyze_location_and_perks(state.get("city") or "Kanpur", kw, central_sub)
    total_benefit = central_sub + state_sub

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        state.get("client") or "default",
        "hinglish",
        state.get("name") or "Pending",
        mobile,
        state.get("city") or "Pending",
        f"{discom} ({region})",
        format_inr(state.get("bill") or 0),
        f"{kw} kW",
        get_roof_area_sqft(kw),
        format_inr(central_sub),
        format_inr(state_sub),
        format_inr(total_benefit),
        state.get("property_type") or "Residential",
        state.get("system_type") or "On-Grid",
        "COMPLETE" if complete else "PARTIAL",
        "HIGH PRIORITY",
    ]

    with open(LEADS_FILE, mode="r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        rows = [CSV_HEADERS]
    header, data = rows[0], rows[1:]
    mobile_idx = header.index("Mobile") if "Mobile" in header else 4

    replaced = False
    for i, r in enumerate(data):
        if len(r) > mobile_idx and r[mobile_idx] == mobile:
            data[i] = row
            replaced = True
            break
    if not replaced:
        data.append(row)

    with open(LEADS_FILE, mode="w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        w.writerows(data)

# ------------------------------------------------------------------
# PARSERS
# ------------------------------------------------------------------

def parse_bill(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{3,6})\b", text)
    return int(m.group(1)) if m else None

def parse_mobile(text: str) -> Optional[str]:
    m = re.search(r"\b([6-9]\d{9})\b", text)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None

def parse_name(text: str) -> Optional[str]:
    t = text.strip()
    if re.search(r"\d", t):
        return None
    words = t.split()
    stopwords = {"haan", "han", "yes", "ok", "theek", "nahi", "no", "kanpur", "barra", "kalyanpur", "govind", "nagar"}
    if 1 <= len(words) <= 4 and t.lower() not in stopwords:
        return t.title()
    return None

def parse_city(text: str) -> Optional[str]:
    t = text.strip()
    if not t or "?" in t:
        return None
    return t.title()

def extract_lead_state(messages: List[str]) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    bill, mobile, name, city = None, None, None, None
    for msg in messages:
        if bill is None:
            b = parse_bill(msg)
            if b:
                bill = b
                continue
        if bill is not None and mobile is None:
            m = parse_mobile(msg)
            if m:
                mobile = m
                continue
        if mobile is not None and name is None:
            n = parse_name(msg)
            if n:
                name = n
                continue
        if name is not None and city is None:
            c = parse_city(msg)
            if c:
                city = c
                continue
    return bill, mobile, name, city

# ------------------------------------------------------------------
# PRAGATI HIGH-CONVERTING WORKFLOW
# ------------------------------------------------------------------

async def process_pragati_leadlock(history: List[HistoryMessage], message: str, bg_tasks: BackgroundTasks):
    hist_user_msgs = [h.text for h in history if h.sender == "user"]
    h_bill, h_mobile, h_name, h_city = extract_lead_state(hist_user_msgs)

    # CASE A: Form was ALREADY completed in an earlier turn -> Answer FAQ directly
    if h_city is not None:
        tl = message.lower()
        kw_val, _ = estimate_kw_and_subsidy(h_bill or 3000)

        # 1. Generation Question (Deterministic)
        if any(w in tl for w in ["unit", "units", "generate", "bijli", "banega", "produce"]):
            u_min = kw_val * 4
            u_max = kw_val * 5
            return (
                f"☀️ Aapke **{kw_val} kW system se rozana lagbhag {u_min} se {u_max} units bijli banegi** "
                f"(average 4–5 ghante dhoop par).\n\n"
                f"Hamare technical engineer survey ke dauran exact load verify karenge. 🙏"
            )

        # 2. Finance / EMI Question
        if any(w in tl for w in ["emi", "loan", "down payment", "finance", "paisa", "kharch"]):
            return (
                "💳 **Pragati Solar Hub EMI & Finance Options:**\n\n"
                "• **Zero Down Payment:** Bina jeb se paisa lagaye 100% bank financing.\n"
                "• **Starting EMI:** Sirf ₹1,499/mahina se shuru (6 se 120 months tenure).\n"
                "• **Fast Approval:** 24–48 ghante me direct bank approval, interest starting at 6% p.a.\n\n"
                "Hamare engineer survey ke dauran sabhi documentation guide kar denge. 🙏"
            )

        # 3. Documents Question
        if any(w in tl for w in ["document", "kagaz", "paper", "aadhaar"]):
            return (
                "📄 **PM Surya Ghar Subsidy ke zaroori documents:**\n\n"
                "1. Latest KESCO Bijli Bill\n"
                "2. Identity Proof (Aadhaar Card copy)\n"
                "3. Bank Passbook copy (Subsidy DBT direct transfer ke liye)\n\n"
                "Hamari team portal registration mein poori help karegi. 🙏"
            )

        return (
            f"Dhanyawad {h_name} ji! Aapki request note hai. "
            f"Hamare solar specialist aapse `{h_mobile}` par contact karke exact detail share karenge. ☀️"
        )

    # CASE B: Form is currently in progress
    all_user_msgs = hist_user_msgs + [message]
    bill, mobile, name, city = extract_lead_state(all_user_msgs)

    # Step 1: Bill pending
    if bill is None:
        return "☀️ Namaste! PM Surya Ghar Yojana ke tehat Kanpur mein ₹78,000–₹1,08,000 tak subsidy check karein. Aapka monthly bijli bill kitna aata hai?"

    # Step 2: Mobile pending -> Show Value Reveal & Lock
    if mobile is None:
        last_b = parse_bill(message)
        if last_b:
            kw, central_sub = estimate_kw_and_subsidy(bill)
            state_sub = min(kw * 15000, 30000)
            total_sub = central_sub + state_sub
            roof = get_roof_area_sqft(kw)
            return (
                f"🎉 **Badhaai ho! Aapke {format_inr(bill)} bill par PM Surya Ghar + UP Sarkar ki taraf se Total {format_inr(total_sub)} tak ki Subsidy Approved hai!**\n\n"
                f"☀️ **System Size:** ~{kw} kW (Monthly 80%–90% bill zero)\n"
                f"🏠 **Chhat par Jagah:** ~{roof} shadow-free\n"
                f"💳 **Pragati Solar Finance:** Zero Down Payment | EMI starting ₹1,499/mahina (6% interest tie-up)\n\n"
                f"🔒 **Subsidy Approval Allotment Code aur Official Cost PDF lock hai.**\n\n"
                f"Ise unlock karke WhatsApp par lene ke liye apna **10-digit WhatsApp Number** likhein:"
            )
        return "⚠️️ Kripya apna valid **10-digit WhatsApp number** likhein taaki Pragati Solar Hub aapko official subsidy quotation bhej sake:"

    # Step 3: Just Mobile captured -> Immediate alert & ask name
    state_draft = {"client": "pragati", "bill": bill, "mobile": mobile, "name": name, "city": city}
    upsert_lead(state_draft, complete=False)

    if parse_mobile(message) and name is None:
        bg_tasks.add_task(send_telegram_alert, state_draft, False)
        return "✅ **WhatsApp Number verify ho gaya!**\n\nAapki quotation file prepare ho rahi hai. Kripya apna **Poora Naam (Full Name)** likhiye:"

    # Step 4: Name pending
    if name is None:
        return "Kripya survey aur quotation ke liye apna **Poora Naam** batayein:"

    # Step 5: Just Name captured -> Ask City
    if city is None:
        last_n = parse_name(message)
        if last_n:
            return f"Dhanyawad {name} ji! 🙏 KESCO Subsidy slot ke liye Kanpur mein apna **Area / Colony aur PIN Code** batayein (jaise: Barra 208027 ya Kalyanpur):"
        return "Kripya Kanpur mein apna Area ya PIN Code likhiye:"

    # Step 6: City just captured -> Complete Initial Booking
    state_draft["name"] = name
    state_draft["city"] = city
    upsert_lead(state_draft, complete=True)

    bg_tasks.add_task(send_telegram_alert, state_draft, True)
    bg_tasks.add_task(send_whatsapp_alert, state_draft)

    kw, central_sub = estimate_kw_and_subsidy(bill)
    state_sub = min(kw * 15000, 30000)
    total_sub = central_sub + state_sub
    region, discom, _, _ = analyze_location_and_perks(city, kw, central_sub)

    return (
        f"🎉 **Dhanyawad {name} ji! Aapka Solar Subsidy Form successfully confirm ho gaya hai!** 🙏\n\n"
        f"📋 **Booking Summary:**\n"
        f"• Plant Size: ~{kw} kW On-Grid System\n"
        f"• Area: {city} [{discom}]\n"
        f"• Total Combined Subsidy: {format_inr(total_sub)}\n"
        f"• Monthly Bachat: Lagbhag {format_inr(int(bill * 0.85))}/month\n"
        f"• Loan Option: Zero Down Payment | 24-48h Approval\n\n"
        f"Hamare senior technical engineer aapse `{mobile}` par contact karke survey schedule karenge. ☀️\n\n"
        f"*(Aap abhi bhi generation units, EMI ya documents ke baare me sawal pooch sakte hain)*"
    )

# ------------------------------------------------------------------
# APP ENTRY & HEALTH MONITORING
# ------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Solar Sathi AI", "timestamp": datetime.now(IST).isoformat()}

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks):
    try:
        client_tag = (req.client or "default").lower().strip()
        
        # Pragati Solar Hub: Value-first lock & FAQ flow
        if client_tag == "pragati":
            reply = await process_pragati_leadlock(req.history, req.message, bg_tasks)
            return {"reply": reply}

        # Default / Other Clients fallback
        return {"reply": "☀️ Welcome to Solar Sathi AI! Kripya apna monthly electricity bill batayein:"}
    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "Sorry, ek technical samasya aayi. Kripya apna answer dobara bhejein."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
