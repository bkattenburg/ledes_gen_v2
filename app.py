
import io, random, datetime, textwrap
from typing import List, Dict, Tuple
try:
    import streamlit as st
except Exception:
    st = None

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
except Exception:
    PILImage = ImageDraw = ImageFont = None

# === UI helper ===
def render_expense_settings_ui():
    if st is None:
        return {"mileage_rate": 0.65, "travel_min": 100.0, "travel_max": 800.0, "tel_min": 5.0, "tel_max": 40.0}
    st.markdown("<h3 style='color: #1E1E1E;'>Expense Settings</h3>", unsafe_allow_html=True)
    with st.expander("Adjust Expense Amounts", expanded=False):
        mileage_rate = st.number_input(
            "Local Travel (E109) mileage rate ($/mile)",
            min_value=0.20, max_value=2.00, value=0.65, step=0.01, key="mileage_rate_e109"
        )
        travel_min, travel_max = st.slider(
            "Out-of-town Travel (E110) amount range ($)",
            min_value=10.0, max_value=2000.0, value=(100.0, 800.0), step=10.0, key="travel_range_e110"
        )
        tel_min, tel_max = st.slider(
            "Telephone (E105) amount range ($)",
            min_value=1.0, max_value=150.0, value=(5.0, 40.0), step=1.0, key="telephone_range_e105"
        )
    return {"mileage_rate": float(mileage_rate), "travel_min": float(travel_min), "travel_max": float(travel_max),
            "tel_min": float(tel_min), "tel_max": float(tel_max)}

# === Enhanced expense generator ===
def generate_expenses_realistic(expense_count: int, billing_start_date: datetime.date,
                                billing_end_date: datetime.date, client_id: str, law_firm_id: str,
                                invoice_desc: str, CONFIG: Dict, OTHER_EXPENSE_DESCRIPTIONS: List[str],
                                settings: Dict) -> List[Dict]:
    rows: List[Dict] = []
    delta = billing_end_date - billing_start_date
    num_days = max(1, delta.days + 1)
    mileage_rate = settings.get("mileage_rate", 0.65)
    travel_min, travel_max = settings.get("travel_min", 100.0), settings.get("travel_max", 800.0)
    tel_min, tel_max = settings.get("tel_min", 5.0), settings.get("tel_max", 40.0)

    # Always include some Copying (E101)
    e101_actual_count = random.randint(1, min(3, expense_count))
    for _ in range(e101_actual_count):
        description = "Copying"
        expense_code = "E101"
        hours = random.randint(50, 300)
        rate = round(random.uniform(0.14, 0.25), 2)
        day = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=day)
        line_item_total = round(hours * rate, 2)
        rows.append({
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": "",
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
            "TASK_CODE": "", "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
            "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": line_item_total
        })

    # Remaining
    for _ in range(max(0, expense_count - e101_actual_count)):
        description = random.choice(OTHER_EXPENSE_DESCRIPTIONS)
        expense_code = CONFIG['EXPENSE_CODES'][description]
        day = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=day)

        if expense_code == "E109":
            miles = random.randint(5, 50)
            hours = miles
            rate = mileage_rate
            total = round(miles * rate, 2)
        elif expense_code == "E110":
            hours = 1
            rate = round(random.uniform(travel_min, travel_max), 2)
            total = rate
        elif expense_code == "E105":
            hours = 1
            rate = round(random.uniform(tel_min, tel_max), 2)
            total = rate
        elif expense_code == "E107":
            hours = 1
            rate = round(random.uniform(20.0, 100.0), 2)
            total = rate
        elif expense_code == "E108":
            hours = 1
            rate = round(random.uniform(5.0, 50.0), 2)
            total = rate
        elif expense_code == "E111":
            hours = 1
            rate = round(random.uniform(15.0, 150.0), 2)
            total = rate
        else:
            hours = random.randint(1, 5)
            rate = round(random.uniform(10.0, 150.0), 2)
            total = round(hours * rate, 2)

        rows.append({
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": "",
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
            "TASK_CODE": "", "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
            "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": total
        })

    return rows

# === Enhanced receipts (will skip E101 by returning None buffer) ===
def _create_receipt_image(expense_row: dict, faker_instance) -> Tuple[str, io.BytesIO]:
    exp_code = str(expense_row.get("EXPENSE_CODE","")).strip()
    # Always skip Copying by returning None buffer
    if exp_code == "E101":
        return f"Receipt_{exp_code}.png", None

    if PILImage is None:
        return f"Receipt_{exp_code}.png", None

    width, height = 600, 950
    bg = (252, 252, 252); fg = (20, 20, 20); faint = (90, 90, 90)
    line_y_gap = 28

    TAX_MAP = {"E111":0.085,"E110":0.0,"E109":0.0,"E108":0.0,"E115":0.085,"E116":0.085,"E117":0.085}

    def money(x): return f"${x:,.2f}"
    def draw_hr(draw, y, pad_left=40, pad_right=40): draw.line([(pad_left,y),(width-pad_right,y)], fill=faint, width=1)

    import random as _r
    def mask_card():
        brand = _r.choice(["VISA","MC","AMEX","DISC"])
        tail = _r.randint(1000,9999)
        return f"{brand} ****-****-****-{tail}" if brand!="AMEX" else f"{brand} ****-******-*{tail}"
    def auth_code(): return f"APPROVED  AUTH {_r.randint(100000,999999)}  REF {_r.randint(1000,9999)}"

    total_amount = float(expense_row.get("LINE_ITEM_TOTAL", 0.0))
    desc = str(expense_row.get("DESCRIPTION","")).strip() or "Item"
    try:
        d = datetime.datetime.strptime(str(expense_row["LINE_ITEM_DATE"]), "%Y-%m-%d").date()
    except Exception:
        d = datetime.datetime.today().date()

    # Simple itemization
    items = [(desc[:20] or "Item", 1, total_amount, total_amount)]
    subtotal = round(sum(x[3] for x in items), 2)
    tax_rate = TAX_MAP.get(exp_code, 0.085 if subtotal>0 else 0.0)
    tax = round(subtotal * tax_rate, 2)
    tip = 0.0
    grand = round(subtotal + tax + tip, 2)
    drift = round(total_amount - grand, 2)
    if abs(drift) >= 0.01 and items:
        name, qty, unit, line_total = items[-1]
        line_total = round(line_total + drift, 2)
        unit = round(line_total / max(qty,1), 2)
        items[-1] = (name, qty, unit, line_total)
        subtotal = round(sum(x[3] for x in items), 2)
        grand = round(subtotal + tax + tip, 2)

    img = PILImage.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("arial.ttf", 34)
        header_font = ImageFont.truetype("arial.ttf", 22)
        mono_font = ImageFont.truetype("arial.ttf", 22)
        small_font = ImageFont.truetype("arial.ttf", 18)
        tiny_font = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        title_font = header_font = mono_font = small_font = tiny_font = ImageFont.load_default()

    y = 30
    title = "RECEIPT"
    tw = draw.textlength(title, font=title_font)
    draw.text(((width - tw) / 2, y), title, font=title_font, fill=fg)
    y += 42

    merchant = faker_instance.company() if faker_instance else "Merchant"
    m_addr = (faker_instance.address().replace("\n", ", ") if faker_instance else "123 Main St, City, ST")
    m_phone = (faker_instance.phone_number() if faker_instance else "(555) 555-1212")
    cashier = (faker_instance.first_name() if faker_instance else "Alex")

    for line in (merchant, m_addr, f"Tel: {m_phone}"):
        draw.text((40, y), line, font=header_font, fill=fg); y += 26
    y += 6; draw_hr(draw, y); y += 14

    rnum = f"{_r.randint(100000,999999)}-{_r.randint(10,99)}"
    draw.text((40, y), f"Date: {d.strftime('%a %b %d, %Y')}", font=mono_font, fill=fg)
    draw.text((width-300, y), f"Receipt #: {rnum}", font=mono_font, fill=fg); y += 30
    draw.text((40, y), f"Cashier: {cashier}", font=mono_font, fill=faint); y += 10
    draw_hr(draw, y); y += 16

    draw.text((40, y), "Item", font=small_font, fill=faint)
    draw.text((width-255, y), "Qty", font=small_font, fill=faint)
    draw.text((width-180, y), "Price", font=small_font, fill=faint)
    draw.text((width-95, y), "Total", font=small_font, fill=faint); y += 22

    for name, qty, unit, line_total in items:
        for i, wrap_line in enumerate(textwrap.wrap(name, width=32) or ["Item"]):
            draw.text((40, y), wrap_line, font=mono_font, fill=fg)
            if i == 0:
                draw.text((width-245, y), str(qty), font=mono_font, fill=fg)
                draw.text((width-180, y), money(unit), font=mono_font, fill=fg)
                draw.text((width-95, y), money(line_total), font=mono_font, fill=fg)
            y += line_y_gap-8
        y += 2
    draw_hr(draw, y); y += 14

    draw.text((width-220, y), "Subtotal", font=mono_font, fill=fg)
    draw.text((width-95, y), money(subtotal), font=mono_font, fill=fg); y += 24
    if tax > 0:
        draw.text((width-220, y), "Tax", font=mono_font, fill=fg)
        draw.text((width-95, y), money(tax), font=mono_font, fill=fg); y += 24
    draw.text((width-220, y), "TOTAL", font=header_font, fill=fg)
    draw.text((width-95, y), money(grand), font=header_font, fill=fg); y += 30
    draw_hr(draw, y); y += 14

    pm = mask_card()
    draw.text((40, y), pm, font=mono_font, fill=fg); y += 26
    draw.text((40, y), auth_code(), font=mono_font, fill=faint); y += 10
    draw_hr(draw, y); y += 14

    policy = "Returns within 30 days with receipt. Items must be unused and in original packaging."
    for line in textwrap.wrap(policy, width=70):
        draw.text((40, y), line, font=tiny_font, fill=faint); y += 20

    y = height - 80; x = 40; _r.seed(rnum)
    for _ in range(60):
        bar_h = _r.randint(20, 50); bar_w = _r.choice([1,1,2])
        draw.rectangle([x, y, x+bar_w, y+bar_h], fill=faint)
        x += bar_w + 3
        if x > width - 40: break

    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return f"Receipt_{exp_code}_{d.strftime('%Y%m%d')}.png", buf
