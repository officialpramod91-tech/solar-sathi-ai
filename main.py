"""
Solar Sathi AI — Dedicated Official Engine
Platform: BijliGyaan.in
Scope: Pan-India PM Surya Ghar Advisory & Lead Generation
Author: Pramod
"""

import os
import re
import csv
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

IST = timezone(timedelta(hours=5, minutes=30))
load_dotenv()

# Alert Configurations
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "Timestamp", "Name", "Mobile", "City_State", "DISCOM", "Monthly_Bill",
    "System_kW", "Roof_Area_Req", "Central_Subsidy", "State_Subsidy", "Total_Benefit",
    "Status"
]

def ensure_csv():
    if not os.path.exists(LEADS_FILE) or os.path.getsize(LEADS_FILE) == 0:
        with open(LEADS_FILE, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADERS)

app = FastAPI(title="Solar Sathi AI — BijliGyaan")

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
# PAN-INDIA LOCATION & SUBSIDY MAPPING
# ------------------------------------------------------------------

def analyze_location_and_perks(location_text: str, kw: int, central_sub: int) -> Tuple[str, str, int, str]:
    loc = location_text.lower().strip()
    
    # Uttar Pradesh (UPNEDA Extra State Subsidy up to Rs 30,000)
    up_keywords = ["kanpur", "lucknow", "agra", "varanasi", "noida", "ghaziabad", "prayagraj", "gorakhpur", "up", "uttar pradesh", "2080", "2093", "2013", "2260"]
    if any(k in loc for k in up_keywords):
        state_sub = min(kw * 15000, 30000)
        total = central_sub + state_sub
        return "Uttar Pradesh", "UPNEDA / State DISCOM", state_sub, f"Total {format_inr(total)} (Central + UP State Subsidy)"

    # Delhi NCR
    if any(k in loc for k in ["delhi", "new delhi", "1100"]):
        state_sub = min(kw * 2000, 10000)
        total = central_sub + state_sub
        return "Delhi NCR", "BSES / TPDDL (Solar Policy)", state_sub, f"Total {format_inr(total)} Subsidy"

    # Pan-India Default (Central Scheme Standard)
    return "India (Pan-India)", "Local State DISCOM", 0, f"Total {format_inr(central_sub)} Central Subsidy"

def estimate_kw_and_subsidy(bill: int) -> Tuple[int, int]:
    if bill <= 1500: return 1, 30000
    elif bill <= 2800: return 2, 60000
    elif bill <= 4500: return 3, 78000
    elif bill <= 6500: return 4, 78000
    elif bill <= 8500: return 5, 78000
    else: return 7, 78000

def get_roof_area_sqft(kw: int) -> str:
    return f"{kw * 80} - {kw * 100} sq. ft."

# ------------------------------------------------------------------
# TELEGRAM ALERTS
# ------------------------------------------------------------------

def send_telegram_alert(state: dict, complete: bool = True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000)
    region, discom, state_sub, _ = analyze_location_and_perks(state.get("city") or "India", kw, central_sub)
    total_benefit = central_sub + state_sub

    header = "🚨 *NEW SOLAR SATHI LEAD (BIJLIGYAAN)!* ☀️" if complete else "🔥 *HOT LEAD: MOBILE CAPTURED!* 📞"

    text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Customer:* {state.get('name') or 'In Progress'}\n"
        f"📞 *Mobile:* `{state.get('mobile')}`\n"
        f"📍 *Location:* {state.get('city') or 'Pending'}\n"
        f"⚡ *DISCOM:* {discom} ({region})\n"
        f"💡 *Bill:* {format_inr(state.get('bill') or 0)} (~{kw} kW Recommended)\n"
        f"💰 *Total Subsidy Benefit:* {format_inr(total_benefit)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}\n"
        f"🌐 *Source:* BijliGyaan.in Organic Portal"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=6)
    except Exception:
        pass

def upsert_lead(state: dict, complete: bool):
    mobile = state.get("mobile")
    if not mobile:
        return
    ensure_csv()

    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000)
    region, discom, state_sub, _ = analyze_location_and_perks(state.get("city") or "India", kw, central_sub)
    total_benefit = central_sub + state_sub

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
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
        "COMPLETE" if complete else "PARTIAL (Phone Only)",
    ]

    with open(LEADS_FILE, mode="r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        rows = [CSV_HEADERS]
    header, data = rows[0], rows[1:]
    mobile_idx = header.index("Mobile") if "Mobile" in header else 2

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
# STRICT PARSERS
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
    stopwords = {"haan", "han", "yes", "ok", "theek", "nahi", "no", "delhi", "mumbai", "patna", "kanpur", "lucknow"}
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
# SOLAR SATHI AI CONVERSATION ENGINE
# ------------------------------------------------------------------

async def process_solar_sathi(history: List[HistoryMessage], message: str, bg_tasks: BackgroundTasks):
    hist_user_msgs = [h.text for h in history if h.sender == "user"]
    h_bill, h_mobile, h_name, h_city = extract_lead_state(hist_user_msgs)

    # 1. Post-Completion FAQ Handler (When user asks queries after form submission)
    if h_city is not None:
        tl = message.lower()
        kw_val, _ = estimate_kw_and_subsidy(h_bill or 3000)

        # Generation Question
        if any(w in tl for w in ["unit", "units", "bijli", "banega", "generate", "produce"]):
            u_min, u_max = kw_val * 4, kw_val * 5
            return (
                f"☀️ Aapke **{kw_val} kW system se rozana lagbhag {u_min} se {u_max} units bijli banegi** "
                f"(average 4–5 ghante achhi dhoop par).\n\n"
                f"BijliGyaan feasibility report aapse jaldi share ki jayegi. 🙏"
            )

        # Document Question
        if any(w in tl for w in ["document", "kagaz", "paper", "documents"]):
            return (
                "📄 **PM Surya Ghar Subsidy ke zaroori documents:**\n\n"
                "1. Latest Electricity Bill (Bijli Bill)\n"
                "2. Identity Proof (Aadhaar Card)\n"
                "3. Bank Passbook copy ya Cancelled Cheque (Direct DBT subsidy transfer ke liye)\n\n"
                "National portal par verification process bohot smooth hai. 🙏"
            )

        # Loan / EMI Question
        if any(w in tl for w in ["emi", "loan", "down payment", "finance", "paisa"]):
            return (
                "💳 **Solar Subsidy Loan Options:**\n\n"
                "• **Low Interest:** PM Surya Ghar ke tehat nationalized banks se 7% ke aas-paas concessional loan milta hai.\n"
                "• **Tenure:** 3 saal se 10 saal tak ki aasan EMI suvidha available hai.\n\n"
                "Complete details official feasibility PDF report mein shamil hongi. 🙏"
            )

        return f"Dhanyawad {h_name} ji! Aapki request safely registered hai. Hamare expert jald aapse `{h_mobile}` par contact karenge. ☀️"

    all_user_msgs = hist_user_msgs + [message]
    bill, mobile, name, city = extract_lead_state(all_user_msgs)

    # 2. Step 1: Bill Pending
    if bill is None:
        return "☀️ Namaste! PM Surya Ghar Muft Bijli Yojana ke tehat apne ghar ke liye Sarkari Subsidy check karein. Aapka monthly bijli bill kitna aata hai?"

    # 3. Step 2: Mobile Pending (Value-First Reveal & Smart Gate)
    if mobile is None:
        last_b = parse_bill(message)
        if last_b:
            kw, central_sub = estimate_kw_and_subsidy(bill)
            roof = get_roof_area_sqft(kw)
            u_min, u_max = kw * 4, kw * 5
            return (
                f"🎉 **Badhaai ho! Aapke {format_inr(bill)} bill ke liye Feasibility Calculation Ready Hai:**\n\n"
                f"☀️ **Recommended System:** ~{kw} kW On-Grid Solar Plant\n"
                f"⚡ **Rozana Bijli:** ~{u_min} se {u_max} Units/din (Monthly 85% bill zero)\n"
                f"🏠 **Chhat ki Jagah:** ~{roof} shadow-free rooftop\n"
                f"💰 **Central Subsidy Benefit:** {format_inr(central_sub)} (Direct Bank DBT)\n\n"
                f"🔒 **DISCOM Net-Metering Eligibility, Cost Breakdown aur Official PDF lock hai.**\n\n"
                f"Ise direct WhatsApp par receive karne ke liye apna **10-digit WhatsApp Number** likhein:"
            )
        return "⚠️ Kripya apna valid **10-digit WhatsApp number** likhein taaki feasibility report share ki ja sake:"

    # 4. Step 3: Mobile Captured -> Instant Telegram Alert
    state_draft = {"bill": bill, "mobile": mobile, "name": name, "city": city}
    upsert_lead(state_draft, complete=False)

    if parse_mobile(message) and name is None:
        bg_tasks.add_task(send_telegram_alert, state_draft, False)
        return "✅ **WhatsApp Number confirm ho gaya!**\n\nOfficial proposal aur slip generate karne ke liye kripya apna **Poora Naam (Full Name)** likhiye:"

    # 5. Step 4: Name Pending
    if name is None:
        return "Kripya apna **Poora Naam** batayein:"

    # 6. Step 5: Name Captured -> Ask Location
    if city is None:
        last_n = parse_name(message)
        if last_n:
            return f"Dhanyawad {name} ji! 🙏 Apne state ki local DISCOM rules aur extra state subsidy ke liye apna **City/State aur PIN Code** likhein:"
        return "Kripya apna City, State aur PIN Code likhein:"

    # 7. Step 6: Complete Lead Captured
    state_draft["name"] = name
    state_draft["city"] = city
    upsert_lead(state_draft, complete=True)
    bg_tasks.add_task(send_telegram_alert, state_draft, True)

    kw, central_sub = estimate_kw_and_subsidy(bill)
    region, discom, state_sub, perk_text = analyze_location_and_perks(city, kw, central_sub)

    return (
        f"🎉 **Dhanyawad {name} ji! Aapki Solar Sathi Advisory Slip confirm ho gayi hai!** 🙏\n\n"
        f"📋 **System Summary:**\n"
        f"• Plant Capacity: ~{kw} kW On-Grid System\n"
        f"• Location & DISCOM: {city} [{discom}]\n"
        f"• Subsidy Category: {perk_text}\n"
        f"• Monthly Bachat: Lagbhag {format_inr(int(bill * 0.85))}/mahina\n\n"
        f"Aapki detailed quotation PDF slip ready ho rahi hai aur jald WhatsApp par share kar di jayegi. ☀️\n\n"
        f"*(Aap abhi bhi units generation, loan ya documents ke baare mein sawal pooch sakte hain)*"
    )

# ------------------------------------------------------------------
# APP ENDPOINTS
# ------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Solar Sathi AI — BijliGyaan", "timestamp": datetime.now(IST).isoformat()}

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks):
    try:
        reply = await process_solar_sathi(req.history, req.message, bg_tasks)
        return {"reply": reply}
    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "Technical samasya aayi. Kripya apna jawab dobara bhejein."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
