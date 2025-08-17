import streamlit as st
import pandas as pd
import random
import datetime
import calendar
import io
import os
import logging
import re
import smtplib
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from faker import Faker
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from PIL import Image as PILImage, ImageDraw, ImageFont
import zipfile

# --- Logging Setup ---
logging.basicConfig(level=logging.ERROR)

# --- Constants ---
EXPENSE_CODES = {
    "Copying": "E101", "Outside printing": "E102", "Word processing": "E103",
    "Facsimile": "E104", "Telephone": "E105", "Online research": "E106",
    "Delivery services/messengers": "E107", "Postage": "E108", "Local travel": "E109",
    "Out-of-town travel": "E110", "Meals": "E111", "Court fees": "E112",
    "Subpoena fees": "E113", "Witness fees": "E114", "Deposition transcripts": "E115",
    "Trial transcripts": "E116", "Trial exhibits": "E117",
    "Litigation support vendors": "E118", "Experts": "E119",
    "Private investigators": "E120", "Arbitrators/mediators": "E121",
    "Local counsel": "E122", "Other professionals": "E123", "Other": "E124",
}
EXPENSE_DESCRIPTIONS = list(EXPENSE_CODES.keys())
OTHER_EXPENSE_DESCRIPTIONS = [desc for desc in EXPENSE_DESCRIPTIONS if EXPENSE_CODES[desc] != "E101"]

DEFAULT_TASK_ACTIVITY_DESC = [
    ("L100", "A101", "Legal Research: Analyze legal precedents"),
    # ... (omitted for brevity, add all)
]

MAJOR_TASK_CODES = {"L110", "L120", "L130", "L140", "L150", "L160", "L170", "L180", "L190"}
DEFAULT_CLIENT_ID = "02-4388252"
DEFAULT_LAW_FIRM_ID = "02-1234567"
DEFAULT_INVOICE_DESCRIPTION = "Monthly Legal Services"

MANDATORY_ITEMS = {
    'KBCG': {
        'desc': ("Commenced data entry into the KBCG e-licensing portal for Piers Walter Vermont "
                 "form 1005 application; Drafted deficiency notice to send to client re: same; "
                 "Scheduled follow-up call with client to review application status and address outstanding deficiencies."),
        'tk_name': "Tom Delaganis",
        'task': "L140",
        'activity': "A107",
        'is_expense': False
    },
    'John Doe': {
        'desc': ("Reviewed and summarized deposition transcript of John Doe; prepared exhibit index; "
                 "updated case chronology spreadsheet for attorney review"),
        'tk_name': "Ryan Kinsey",
        'task': "L120",
        'activity': "A102",
        'is_expense': False
    },
    'Uber E110': {
        'desc': "10-mile Uber ride to client's office",
        'expense_code': "E110",
        'is_expense': True
    },
}

# --- Helper Functions ---
def _find_timekeeper_by_name(timekeepers: List[Dict], name: str) -> Optional[Dict]:
    """Find timekeeper by name."""
    if not timekeepers:
        return None
    for tk in timekeepers:
        if str(tk.get("TIMEKEEPER_NAME", "")).strip().lower() == str(name).strip().lower():
            return tk
    return None

def _force_timekeeper_on_row(row: Dict, forced_name: str, timekeepers: List[Dict]) -> Dict:
    """Force timekeeper on row if applicable."""
    if row.get("EXPENSE_CODE"):
        return row
    tk = _find_timekeeper_by_name(timekeepers, forced_name)
    if tk is None and timekeepers:
        tk = timekeepers[0]
    if tk is None:
        row["TIMEKEEPER_NAME"] = forced_name
        return row
    row["TIMEKEEPER_NAME"] = forced_name
    row["TIMEKEEPER_ID"] = tk.get("TIMEKEEPER_ID", row.get("TIMEKEEPER_ID", ""))
    row["TIMEKEEPER_CLASSIFICATION"] = tk.get("TIMEKEEPER_CLASSIFICATION", row.get("TIMEKEEPER_CLASSIFICATION", ""))
    try:
        row["RATE"] = float(tk.get("RATE", row.get("RATE", 0.0)))
        hours = float(row.get("HOURS", 0))
        row["LINE_ITEM_TOTAL"] = round(hours * float(row["RATE"]), 2)
    except Exception:
        pass
    return row

def _process_description(description: str, faker_instance: Faker) -> str:
    """Process description by replacing placeholders and dates."""
    pattern = r"\b(\d{2}/\d{2}/\d{4})\b"
    if re.search(pattern, description):
        days_ago = random.randint(15, 90)
        new_date = (datetime.date.today() - datetime.timedelta(days=days_ago)).strftime("%m/%d/%Y")
        description = re.sub(pattern, new_date, description)
    description = description.replace("{NAME_PLACEHOLDER}", faker_instance.name())
    return description

def _load_timekeepers(uploaded_file: Optional[Any]) -> Optional[List[Dict]]:
    """Load timekeepers from CSV."""
    if uploaded_file is None:
        return None
    try:
        df = pd.read_csv(uploaded_file)
        required_cols = ["TIMEKEEPER_NAME", "TIMEKEEPER_CLASSIFICATION", "TIMEKEEPER_ID", "RATE"]
        if not all(col in df.columns for col in required_cols):
            st.error(f"Timekeeper CSV must contain the following columns: {', '.join(required_cols)}")
            return None
        return df.to_dict(orient='records')
    except Exception as e:
        st.error(f"Error loading timekeeper file: {e}")
        logging.error(e)
        return None

# ... (other functions like _load_custom_task_activity_data, _create_ledes_line_1998b, etc., with docstrings and type hints)

def _generate_fees(fee_count: int, timekeeper_data: List[Dict], billing_start_date: datetime.date, billing_end_date: datetime.date, task_activity_desc: List[tuple], major_task_codes: set, max_hours_per_tk_per_day: int, faker_instance: Faker) -> List[Dict]:
    """Generate fee lines."""
    rows = []
    delta = billing_end_date - billing_start_date
    num_days = delta.days + 1
    major_items = [item for item in task_activity_desc if item[0] in major_task_codes]
    other_items = [item for item in task_activity_desc if item[0] not in major_task_codes]
    daily_hours_tracker = {}
    MAX_DAILY_HOURS = max_hours_per_tk_per_day

    for _ in range(fee_count):
        # ... (fee generation logic)
    return rows

def _generate_expenses(expense_count: int, billing_start_date: datetime.date, billing_end_date: datetime.date) -> List[Dict]:
    """Generate expense lines."""
    rows = []
    # ... (expense generation logic using global OTHER_EXPENSE_DESCRIPTIONS)
    return rows

def _handle_block_billing(rows: List[Dict], include_block_billed: bool, task_activity_desc: List[tuple]) -> List[Dict]:
    """Handle block billing logic."""
    if not include_block_billed:
        rows = [row for row in rows if not ("; " in row["DESCRIPTION"])]
    elif include_block_billed:
        if not any('; ' in row['DESCRIPTION'] for row in rows):
            for task_code, activity_code, desc in task_activity_desc:
                if '; ' in desc and len(rows) > 0:
                    extra = rows[0].copy()
                    extra['DESCRIPTION'] = desc
                    extra['TASK_CODE'] = task_code
                    extra['ACTIVITY_CODE'] = activity_code
                    rows.insert(0, extra)
                    break
    return rows

def _generate_invoice_data(fee_count: int, expense_count: int, timekeeper_data: List[Dict], client_id: str, law_firm_id: str, invoice_desc: str, billing_start_date: datetime.date, billing_end_date: datetime.date, task_activity_desc: List[tuple], major_task_codes: set, max_hours_per_tk_per_day: int, include_block_billed: bool, faker_instance: Faker) -> tuple[List[Dict], float]:
    """Generate invoice data by calling sub-functions."""
    current_invoice_total = 0.0
    fee_rows = _generate_fees(fee_count, timekeeper_data, billing_start_date, billing_end_date, task_activity_desc, major_task_codes, max_hours_per_tk_per_day, faker_instance)
    expense_rows = _generate_expenses(expense_count, billing_start_date, billing_end_date)
    rows = fee_rows + expense_rows
    for row in rows:
        current_invoice_total += row["LINE_ITEM_TOTAL"]
    rows = _handle_block_billing(rows, include_block_billed, task_activity_desc)
    return rows, current_invoice_total

def _ensure_mandatory_lines(rows: List[Dict], timekeeper_data: List[Dict], invoice_desc: str, client_id: str, law_firm_id: str, billing_start_date: datetime.date, billing_end_date: datetime.date, selected_items: List[str]) -> List[Dict]:
    """Ensure mandatory lines based on selected items."""
    def _rand_date_str():
        delta = billing_end_date - billing_start_date
        num_days = max(1, delta.days + 1)
        off = random.randint(0, num_days - 1)
        return (billing_start_date + datetime.timedelta(days=off)).strftime("%Y-%m-%d")

    for item in selected_items:
        config = MANDATORY_ITEMS[item]
        if config['is_expense']:
            hours = 1
            rate = round(random.uniform(25, 80), 2)
            total = round(hours * rate, 2)
            row = {
                "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
                "LINE_ITEM_DATE": _rand_date_str(), "TIMEKEEPER_NAME": "", "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
                "TASK_CODE": "", "ACTIVITY_CODE": "", "EXPENSE_CODE": config['expense_code'],
                "DESCRIPTION": config['desc'], "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": total
            }
        else:
            base_tk = _find_timekeeper_by_name(timekeeper_data, config['tk_name']) or (timekeeper_data[0] if timekeeper_data else None)
            rate = float(base_tk.get("RATE", 250.0)) if base_tk else 250.0
            hours = round(random.uniform(0.5, 3.0), 1)
            total = round(hours * rate, 2)
            row = {
                "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
                "LINE_ITEM_DATE": _rand_date_str(), "TIMEKEEPER_NAME": "", "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
                "TASK_CODE": config['task'], "ACTIVITY_CODE": config['activity'], "EXPENSE_CODE": "",
                "DESCRIPTION": config['desc'], "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": total
            }
        rows.append(row)

    # Enforce timekeepers
    for r in rows:
        d = str(r.get("DESCRIPTION","")).lower()
        if "kbcg" in d:
            _force_timekeeper_on_row(r, "Tom Delaganis", timekeeper_data or [])
        if "john doe" in d:
            _force_timekeeper_on_row(r, "Ryan Kinsey", timekeeper_data or [])
    return rows

# ... (other functions)

def _get_logo_bytes(uploaded_logo: Optional[Any], law_firm_id: str) -> bytes:
    """Get logo bytes from upload or default."""
    if uploaded_logo:
        return uploaded_logo.read()
    if law_firm_id == DEFAULT_LAW_FIRM_ID:
        logo_file_name = "nelsonmurdock2.jpg"
    else:
        logo_file_name = "icon.jpg"
    script_dir = os.path.dirname(__file__)
    logo_path = os.path.join(script_dir, "assets", logo_file_name)
    try:
        with open(logo_path, "rb") as f:
            return f.read()
    except Exception as e:
        logging.error(f"Logo load failed: {e}")
        # Fallback placeholder
        img = PILImage.new("RGB", (128, 128), color="white")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((10, 20), "Logo", font=font, fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

def _create_pdf_invoice(df: pd.DataFrame, total_amount: float, invoice_number: str, invoice_date: datetime.date, billing_start_date: datetime.date, billing_end_date: datetime.date, client_id: str, law_firm_id: str, logo_bytes: bytes) -> io.BytesIO:
    """Create PDF invoice."""
    buffer = io.BytesIO()
    try:
        doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=1.0 * inch, rightMargin=1.0 * inch, topMargin=1.0 * inch, bottomMargin=1.0 * inch)
        # ... (rest same, use Image(io.BytesIO(logo_bytes), ...))
        img = Image(io.BytesIO(logo_bytes), width=0.6 * inch, height=0.6 * inch)
        # ... (build table)
        doc.build(elements)
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        st.error("PDF generation failed. Please try again.")
    buffer.seek(0)
    return buffer

# --- Streamlit App ---
st.title("LEDES Invoice Generator")
st.write("Generate and optionally email LEDES and PDF invoices.")

with st.expander("Help & FAQs"):
    st.markdown("""
    ### What is Spend Agent mode?
    Ensures specific mandatory line items are included for testing or compliance.

    ### How to format custom tasks CSV?
    Columns: TASK_CODE, ACTIVITY_CODE, DESCRIPTION
    Example:
    L100,A101,Legal Research: Analyze legal precedents
    """)

# Sidebar
st.sidebar.title("Quick Links")
sample_timekeeper = pd.DataFrame({
    "TIMEKEEPER_NAME": ["Tom Delaganis", "Ryan Kinsey"],
    "TIMEKEEPER_CLASSIFICATION": ["Partner", "Associate"],
    "TIMEKEEPER_ID": ["TD001", "RK001"],
    "RATE": [250.0, 200.0]
})
csv_timekeeper = sample_timekeeper.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download Sample Timekeeper CSV", csv_timekeeper, "sample_timekeeper.csv", "text/csv")

sample_custom = pd.DataFrame({
    "TASK_CODE": ["L100"],
    "ACTIVITY_CODE": ["A101"],
    "DESCRIPTION": ["Legal Research: Analyze legal precedents"]
})
csv_custom = sample_custom.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download Sample Custom Tasks CSV", csv_custom, "sample_custom_tasks.csv", "text/csv")

# ... (rest of UI, with dynamic tabs, logo upload if include_pdf, multiselect if spend_agent, etc.)

with tab2:
    # ...
    if spend_agent:
        selected_items = st.multiselect("Mandatory Items to Include", list(MANDATORY_ITEMS.keys()), default=list(MANDATORY_ITEMS.keys()))
    else:
        selected_items = []
    if include_pdf:
        uploaded_logo = st.file_uploader("Upload Custom Logo (JPG/PNG)", type=["jpg", "png", "jpeg"])
    # ...

# In generation loop
with st.status("Generating invoices...") as status:
    attachments_list = []
    for i in range(num_invoices):
        status.update(label=f"Generating Invoice {i+1}/{num_invoices} for period {billing_start_date} to {billing_end_date}")
        # generate rows, if spend_agent: rows = _ensure_mandatory_lines(..., selected_items)
        # generate ledes, pdf with logo_bytes = _get_logo_bytes(uploaded_logo, law_firm_id)
        attachments_to_send = [(ledes_filename, ledes_content.encode('utf-8'))]
        if include_pdf:
            attachments_to_send.append((pdf_filename, pdf_buffer.getvalue()))
        if send_email:
            try:
                _send_email_with_attachment(recipient_email, subject.format(matter_number=current_matter_number), body.format(matter_number=current_matter_number), attachments_to_send)
            except Exception as e:
                st.error(f"Email for invoice {i+1} failed: {e}. Providing download instead.")
                for filename, data in attachments_to_send:
                    st.download_button(f"Download {filename}", data, filename)
        else:
            attachments_list.extend(attachments_to_send)
    if not send_email and num_invoices > 1:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zip_file:
            for filename, data in attachments_list:
                zip_file.writestr(filename, data)
        zip_buf.seek(0)
        st.download_button("Download All Invoices ZIP", zip_buf, "invoices.zip", "application/zip")
    elif not send_email:
        for filename, data in attachments_list:
            st.download_button(f"Download {filename}", data, filename)

# For LEDES, in _create_ledes_line_1998b:
    # str(row.get("DESCRIPTION", "")).replace("|", " - ")

</parameter
</xai:function_call
