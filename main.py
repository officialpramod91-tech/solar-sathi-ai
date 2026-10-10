"""
Solar Sathi AI — Dedicated Engine (v9.0 Pan-India Production)
Platform: BijliGyaan.in
Features:
- Pan-India Postal PIN Code Detection (UP, Delhi, RJ, MP, MH, Bihar, HR, etc.)
- Strict 6-Step Lead State Funnel: Bill -> Property -> System -> Location -> Consent -> Phone & Name
- Mid-Funnel Global FAQ Interceptor (EMI, Loans, Generation Units, Documents)
- No Third-Party Multi-Tenant Routing (Dedicated BijliGyaan Engine)
- Formatted INR & Real-time Telegram Push
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "Timestamp", "Name", "Mobile", "City_PIN", "State_Region", "DISCOM", "Monthly_Bill",
    "Property_Type", "System_Type", "Installer_Required", "System_kW", "Roof_Area_Req",
    "Central_Subsidy", "State_Subsidy", "Total_Benefit", "Status"
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
# SYSTEM SIZING & MATH
# ------------------------------------------------------------------

def estimate_kw_and_subsidy(bill: int, prop_type: Optional[str] = "Residential") -> Tuple[int, int]:
    if bill <= 1500: kw, sub = 1, 30000
    elif bill <= 2800: kw, sub = 2, 60000
    elif bill <= 4500: kw, sub = 3, 78000
    elif bill <= 6500: kw, sub = 4, 78000
    elif bill <= 8500: kw, sub = 5, 78000
    else: kw, sub = 7, 78000

    if prop_type and "commercial" in prop_type.lower():
        return kw, 0
    return kw, sub

def get_roof_area_sqft(kw: int) -> str:
    return f"{kw * 80} - {kw * 100} sq. ft."

# ------------------------------------------------------------------
# PAN-INDIA POSTAL INTELLIGENCE
# ------------------------------------------------------------------

def detect_region_and_subsidy(location_text: str, kw: int, central_sub: int) -> Tuple[str, str, int, str]:
    text = location_text.lower()
    pin_match = re.search(r"\b([1-8]\d{5})\b", text)
    pin = pin_match.group(1) if pin_match else ""
    pin_prefix = pin[:2] if len(pin) >= 2 else ""

    # 1. Uttar Pradesh (Prefix: 20 to 28)
    if (pin_prefix and 20 <= int(pin_prefix) <= 28) or any(k in text for k in ["up", "uttar pradesh", "kanpur", "lucknow", "khalilabad", "basti", "gorakhpur", "varanasi", "noida", "ghaziabad", "agra", "meerut", "prayagraj"]):
        state_sub = min(kw * 15000, 30000) if central_sub > 0 else 0
        total = central_sub + state_sub
        return "Uttar Pradesh", "UPNEDA / MVVNL / DVVNL / PVVNL / PuVVNL / KESCO", state_sub, f"Total {format_inr(total)} (Central + UP State UPNEDA Subsidy)"

    # 2. Delhi NCR (Prefix: 11)
    if pin_prefix == "11" or any(k in text for k in ["delhi", "new delhi"]):
        return "Delhi NCR", "BSES / TPDDL (Delhi Solar Policy GBI)", 0, f"Total {format_inr(central_sub)} Central Subsidy + Monthly GBI Credit"

    # 3. Rajasthan (Prefix: 30 to 34)
    if (pin_prefix and 30 <= int(pin_prefix) <= 34) or any(k in text for k in ["rajasthan", "jaipur", "jodhpur", "kota", "udaipur", "bikaner", "ajmer"]):
        return "Rajasthan", "JVVNL / AVVNL / JdVVNL", 0, f"Total {format_inr(central_sub)} Central Subsidy (Highest Solar Generation Belt)"

    # 4. Maharashtra (Prefix: 40 to 44)
    if (pin_prefix and 40 <= int(pin_prefix) <= 44) or any(k in text for k in ["maharashtra", "mumbai", "pune", "nagpur", "nashik", "thane"]):
        return "Maharashtra", "MSEDCL (Mahavitaran) / Tata Power / Adani", 0, f"Total {format_inr(central_sub)} Central Subsidy (Fast Payback High Tariff Slab)"

    # 5. Madhya Pradesh (Prefix: 45 to 48)
    if (pin_prefix and 45 <= int(pin_prefix) <= 48) or any(k in text for k in ["mp", "madhya pradesh", "indore", "bhopal", "jabalpur", "gwalior"]):
        return "Madhya Pradesh", "MPPKVVCL / MPMKVVCL (Urja Saksharta)", 0, f"Total {format_inr(central_sub)} Central Subsidy"

    # 6. Bihar (Prefix: 80 to 85)
    if (pin_prefix and 80 <= int(pin_prefix) <= 85) or any(k in text for k in ["bihar", "patna", "gaya", "muzaffarpur", "bhagalpur", "darbhanga"]):
        return "Bihar", "NBPDCL / SBPDCL (Suvidha Portal)", 0, f"Total {format_inr(central_sub)} Central Subsidy"

    # 7. Haryana (Prefix: 12, 13)
    if pin_prefix in ["12", "13"] or any(k in text for k in ["haryana", "gurugram", "faridabad", "panipat", "karnal", "sonipat"]):
        return "Haryana", "DHBVN / UHBVN", 0, f"Total {format_inr(central_sub)} Central Subsidy"

    # Default Pan-India
    return "India (Pan-India)", "State Electricity Board / DISCOM", 0, f"Total {format_inr(central_sub)} Central Subsidy"

# ------------------------------------------------------------------
# PARSERS & EXTRACTORS
# ------------------------------------------------------------------

def parse_bill(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{3,6})\b", text)
    return int(m.group(1)) if m else None

def parse_property(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in ["dukan", "commercial", "factory", "shop", "office", "business"]):
        return "Commercial"
    if any(k in t for k in ["ghar", "residential", "home", "house"]):
        return "Residential"
    return None

def parse_system(text: str) -> Optional[str]:
    t = text.lower()
    if "hybrid" in t: return "Hybrid"
    if "off-grid" in t or "offgrid" in t: return "Off-Grid"
    if "on-grid" in t or "ongrid" in t or "bill zero" in t: return "On-Grid"
    return None

def parse_location(text: str) -> Optional[str]:
    t = text.strip()
    if re.search(r"\b[1-8]\d{5}\b", t) or len(t) >= 3:
        if not any(k in t.lower() for k in ["emi", "loan", "unit", "document", "kya hai", "kaise"]):
            return t.title()
    return None

def parse_installer_consent(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in ["haan", "yes", "installer", "connect", "suggest", "jarurat hai"]):
        return "Yes (Connect Installer)"
    if any(k in t for k in ["nahi", "no", "sirf pdf", "sirf slip", "only report", "jarurat nahi"]):
        return "No (Only Report)"
    return None

def parse_mobile(text: str) -> Optional[str]:
    m = re.search(r"\b([6-9]\d{9})\b", text)
    if m: return m.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None

def parse_name(text: str) -> Optional[str]:
    t = text.strip()
    if re.search(r"\d", t): return None
    words = t.split()
    stopwords = {"haan", "han", "yes", "ok", "theek", "nahi", "no", "delhi", "mumbai", "patna", "kanpur", "khalilabad", "jaipur"}
    if 1 <= len(words) <= 4 and t.lower() not in stopwords:
        return t.title()
    return None

def extract_state(history_msgs: List[str]):
    bill, prop, sys_t, loc, consent, mob, name = None, None, None, None, None, None, None
    for msg in history_msgs:
        if bill is None:
            b = parse_bill(msg)
            if b: bill = b; continue
        if bill is not None and prop is None:
            p = parse_property(msg)
            if p: prop = p; continue
        if prop is not None and sys_t is None:
            s = parse_system(msg)
            if s: sys_t = s; continue
        if sys_t is not None and loc is None:
            l = parse_location(msg)
            if l: loc = l; continue
        if loc is not None and consent is None:
            c = parse_installer_consent(msg)
            if c: consent = c; continue
        if consent is not None and mob is None:
            m = parse_mobile(msg)
            if m: mob = m; continue
        if mob is not None and name is None:
            n = parse_name(msg)
            if n: name = n; continue
    return bill, prop, sys_t, loc, consent, mob, name

# ------------------------------------------------------------------
# TELEGRAM & CSV STORAGE
# ------------------------------------------------------------------

def send_telegram_alert(state: dict, complete: bool = True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000, state.get("property"))
    region, discom, state_sub, _ = detect_region_and_subsidy(state.get("location") or "India", kw, central_sub)
    total_benefit = central_sub + state_sub

    header = "🚨 *NEW SOLAR SATHI LEAD (BIJLIGYAAN)!* ☀️" if complete else "🔥 *HOT LEAD: PHONE CAPTURED!* 📞"
    text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Customer:* {state.get('name') or 'In Progress'}\n"
        f"📞 *Mobile:* `{state.get('mobile')}`\n"
        f"📍 *Location:* {state.get('location') or 'Pending'}\n"
        f"⚡ *DISCOM:* {discom} ({region})\n"
        f"💡 *Bill:* {format_inr(state.get('bill') or 0)} (~{kw} kW Recommended)\n"
        f"🏠 *Property:* {state.get('property') or 'Residential'} | *System:* {state.get('system') or 'On-Grid'}\n"
        f"🛠️ *Installer Required:* {state.get('consent') or 'Undecided'}\n"
        f"💰 *Total Subsidy:* {format_inr(total_benefit)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}\n"
        f"🌐 *Source:* BijliGyaan Organic Tool"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=6)
    except Exception:
        pass

def upsert_lead(state: dict, complete: bool):
    mobile = state.get("mobile")
    if not mobile: return
    ensure_csv()

    kw, central_sub = estimate_kw_and_subsidy(state.get("bill") or 3000, state.get("property"))
    region, discom, state_sub, _ = detect_region_and_subsidy(state.get("location") or "India", kw, central_sub)
    total_benefit = central_sub + state_sub

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        state.get("name") or "Pending",
        mobile,
        state.get("location") or "Pending",
        region,
        discom,
        format_inr(state.get("bill") or 0),
        state.get("property") or "Residential",
        state.get("system") or "On-Grid",
        state.get("consent") or "Pending",
        f"{kw} kW",
        get_roof_area_sqft(kw),
        format_inr(central_sub),
        format_inr(state_sub),
        format_inr(total_benefit),
        "COMPLETE" if complete else "PARTIAL",
    ]

    with open(LEADS_FILE, mode="r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows: rows = [CSV_HEADERS]
    header, data = rows[0], rows[1:]
    mobile_idx = header.index("Mobile") if "Mobile" in header else 2

    replaced = False
    for i, r in enumerate(data):
        if len(r) > mobile_idx and r[mobile_idx] == mobile:
            data[i] = row
            replaced = True
            break
    if not replaced: data.append(row)

    with open(LEADS_FILE, mode="w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        w.writerows(data)

# ------------------------------------------------------------------
# FAQ INTERCEPTOR
# ------------------------------------------------------------------

def check_faq_interceptor(message: str, bill: Optional[int], kw_val: int) -> Optional[str]:
    tl = message.lower()

    if any(w in tl for w in ["emi", "loan", "down payment", "finance", "byaj", "kisht"]):
        return (
            "💳 **PM Surya Ghar Solar Loan & EMI Options:**\n\n"
            "• **Collateral-Free Loan:** SBI, Canara, PNB wagairah se sirf ~7% annual concessional interest par loan milta hai.\n"
            "• **Zero Down Payment:** Kai banks 100% plant financing provide karte hain.\n"
            "• **Easy EMI:** 36 se 120 mahine tak ki aasan kisht (starting ~₹1,400/mahina).\n\n"
        )

    if any(w in tl for w in ["unit", "units", "bijli", "banega", "produce", "generate"]):
        u_min, u_max = kw_val * 4, kw_val * 5
        return (
            f"⚡ **Unit Generation Estimate:**\n\n"
            f"Aapke **{kw_val} kW plant se rozana lagbhag {u_min} se {u_max} units bijli banegi** "
            f"(mahine me ~{kw_val * 120} se {kw_val * 150} units) achhi dhoop par.\n\n"
        )

    if any(w in tl for w in ["document", "kagaz", "paper", "documents"]):
        return (
            "📄 **Sarkari Subsidy ke zaroori documents:**\n\n"
            "1. Latest Bijli Bill (Current Electricity Bill)\n"
            "2. Identity Proof (Aadhaar Card)\n"
            "3. Bank Passbook copy / Cancelled Cheque (DBT Subsidy Direct Transfer ke liye)\n\n"
        )
    return None

# ------------------------------------------------------------------
# CORE CONVERSATION CONTROLLER
# ------------------------------------------------------------------

async def process_solar_sathi(history: List[HistoryMessage], message: str, bg_tasks: BackgroundTasks):
    hist_user_msgs = [h.text for h in history if h.sender == "user"]
    h_bill, h_prop, h_sys, h_loc, h_consent, h_mob, h_name = extract_state(hist_user_msgs)

    # 1. Post-Completion FAQ Check
    if h_name is not None:
        kw_val, _ = estimate_kw_and_subsidy(h_bill or 3000, h_prop)
        faq_ans = check_faq_interceptor(message, h_bill, kw_val)
        if faq_ans:
            return f"{faq_ans}Hamare verified engineer aapse `{h_mob}` par contact karke exact feasibility guide karenge. 🙏"
        return f"Dhanyawad {h_name} ji! Aapki report note hai. Hamari team aapse `{h_mob}` par sampark karegi. ☀️"

    all_user_msgs = hist_user_msgs + [message]
    bill, prop, sys_t, loc, consent, mob, name = extract_state(all_user_msgs)

    # Calculate active kw for FAQ reference
    kw_current, _ = estimate_kw_and_subsidy(bill or 3000, prop)
    faq_snippet = check_faq_interceptor(message, bill, kw_current)

    # Step 1: Bill Pending
    if bill is None:
        return "☀️ Namaste! PM Surya Ghar Muft Bijli Yojana ke tehat apne ghar ke liye Sarkari Subsidy check karein. Aapka monthly bijli bill kitna aata hai?"

    # Step 2: Property Type Pending
    if prop is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return prefix + "Aap solar plant kis jagah ke liye lagwana chahte hain? (Neeche tap karein):"

    # Step 3: System Type Pending
    if sys_t is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return prefix + "Aapko kis type ka solar system chahiye? (Neeche select karein):"

    # Step 4: Location / PIN Code Pending
    if loc is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return prefix + "Apne area ka **6-digit PIN Code ya City** likhein (jaise: 272175, 302001, 800001, 400001) taaki aapke state ki extra subsidy aur DISCOM rules calculate ho sakein:"

    # Step 5: Installer Consent Pending (BIG VALUE REVEAL)
    kw, central_sub = estimate_kw_and_subsidy(bill, prop)
    region, discom, state_sub, perk_text = detect_region_and_subsidy(loc, kw, central_sub)
    total_benefit = central_sub + state_sub
    roof = get_roof_area_sqft(kw)
    u_min, u_max = kw * 4, kw * 5

    if consent is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return (
            prefix +
            f"🎉 **Badhaai ho! Aapke {loc} [{region}] ke liye Feasibility Report Ready Hai:**\n\n"
            f"☀️ **Recommended Plant:** ~{kw} kW ({sys_t})\n"
            f"⚡ **Daily Bijli:** ~{u_min} se {u_max} Units/din (85% bill zero)\n"
            f"🏠 **Chhat ki Jagah:** ~{roof} shadow-free\n"
            f"💰 **Subsidy Benefit:** **{perk_text}**\n"
            f"⚡ **DISCOM Authority:** {discom}\n\n"
            f"🛠️ **Kya aap chahte hain ki aapke area me BijliGyaan Verified & Empaneled Solar Installers ko free site inspection ke liye suggest kiya jaye?** (Neeche tap karein):"
        )

    # Step 6: Mobile Pending
    state_draft = {
        "bill": bill, "property": prop, "system": sys_t, "location": loc,
        "consent": consent, "mobile": mob, "name": name
    }

    if mob is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return (
            prefix +
            f"🔒 **Aapki Official Feasibility Slip & {discom} Solar Quote PDF ready hai!**\n\n"
            f"Ise direct WhatsApp par secure receive karne ke liye apna **10-digit WhatsApp Number** likhein:"
        )

    # Step 7: Mobile Just Captured -> Push Telegram Hot Alert & Ask Name
    upsert_lead(state_draft, complete=False)

    if parse_mobile(message) and name is None:
        bg_tasks.add_task(send_telegram_alert, state_draft, False)
        return "✅ **WhatsApp Number confirm ho gaya!**\n\nOfficial document aur subsidy slip par registration ke liye apna **Poora Naam (Full Name)** likhiye:"

    if name is None:
        prefix = f"{faq_snippet}\n" if faq_snippet else ""
        return prefix + "Kripya apna **Poora Naam** batayein:"

    # Step 8: Completed Flow
    state_draft["name"] = name
    upsert_lead(state_draft, complete=True)
    bg_tasks.add_task(send_telegram_alert, state_draft, True)

    installer_note = "Hamare verified local installer aapse survey ke liye jald connect karenge." if "Yes" in consent else "Aapki feasibility technical report WhatsApp par bhej di jayegi."

    return (
        f"🎉 **Dhanyawad {name} ji! Aapki Solar Sathi Advisory Slip confirm ho gayi hai!** 🙏\n\n"
        f"📋 **Booking Summary:**\n"
        f"• Capacity: ~{kw} kW {sys_t} ({prop})\n"
        f"• Location: {loc} [{region}]\n"
        f"• Approved Subsidy: {perk_text}\n"
        f"• Monthly Bachat: Lagbhag {format_inr(int(bill * 0.85))}/mahina\n"
        f"• Installer Recommendation: {consent}\n\n"
        f"{installer_note} ☀️\n\n"
        f"*(Aap abhi bhi units generation, loan EMI ya documents ke baare mein sawal pooch sakte hain)*"
    )

# ------------------------------------------------------------------
# APP ROUTING
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
