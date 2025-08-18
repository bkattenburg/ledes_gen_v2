import streamlit as st
import pandas as pd
import random
import datetime
import io
import os
import logging
import re
import smtplib
from typing import Optional, List, Dict, Any, Tuple
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
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constants ---
CONFIG = {
    'EXPENSE_CODES': {
        "Copying": "E101", "Outside printing": "E102", "Word processing": "E103",
        "Facsimile": "E104", "Telephone": "E105", "Online research": "E106",
        "Delivery services/messengers": "E107", "Postage": "E108", "Local travel": "E109",
        "Out-of-town travel": "E110", "Meals": "E111", "Court fees": "E112",
        "Subpoena fees": "E113", "Witness fees": "E114", "Deposition transcripts": "E115",
        "Trial transcripts": "E116", "Trial exhibits": "E117",
        "Litigation support vendors": "E118", "Experts": "E119",
        "Private investigators": "E120", "Arbitrators/mediators": "E121",
        "Local counsel": "E122", "Other professionals": "E123", "Other": "E124",
    },
    'DEFAULT_TASK_ACTIVITY_DESC': [
        ("L100", "A101", "Legal Research: Analyze legal precedents"),
        ("L110", "A101", "Legal Research: Review statutes and regulations"),
        ("L120", "A101", "Legal Research: Draft research memorandum"),
        ("L130", "A102", "Case Assessment: Initial case evaluation"),
        ("L140", "A102", "Case Assessment: Develop case strategy"),
        ("L150", "A102", "Case Assessment: Identify key legal issues"),
        ("L160", "A103", "Fact Investigation: Interview witnesses"),
        ("L190", "A104", "Pleadings: Draft complaint/petition"),
        ("L200", "A104", "Pleadings: Prepare answer/response"),
        ("L210", "A104", "Pleadings: File motion to dismiss"),
        ("L220", "A105", "Discovery: Draft interrogatories"),
        ("L230", "A105", "Discovery: Prepare requests for production"),
        ("L240", "A105", "Discovery: Review opposing party's discovery responses"),
        ("L250", "A106", "Depositions: Prepare for deposition"),
        ("L260", "A106", "Depositions: Attend deposition"),
        ("L300", "A107", "Motions: Argue motion in court"),
        ("L310", "A108", "Settlement/Mediation: Prepare for mediation"),
        ("L320", "A108", "Settlement/Mediation: Attend mediation"),
        ("L330", "A108", "Settlement/Mediation: Draft settlement agreement"),
        ("L340", "A109", "Trial Preparation: Prepare witness for trial"),
        ("L350", "A109", "Trial Preparation: Organize trial exhibits"),
        ("L390", "A110", "Trial: Present closing argument"),
        ("L400", "A111", "Appeals: Research appellate issues"),
        ("L410", "A111", "Appeals: Draft appellate brief"),
        ("L420", "A111", "Appeals: Argue before appellate court"),
        ("L430", "A112", "Client Communication: Client meeting"),
        ("L440", "A112", "Client Communication: Phone call with client"),
        ("L450", "A112", "Client Communication: Email correspondence with client"),
    ],
    'MAJOR_TASK_CODES': {"L110", "L120", "L130", "L140", "L150", "L160", "L170", "L180", "L190"},
    'DEFAULT_CLIENT_ID': "02-4388252",
    'DEFAULT_LAW_FIRM_ID': "02-1234567",
    'DEFAULT_INVOICE_DESCRIPTION': "Monthly Legal Services",
    'MANDATORY_ITEMS': {
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
}
EXPENSE_DESCRIPTIONS = list(CONFIG['EXPENSE_CODES'].keys())
OTHER_EXPENSE_DESCRIPTIONS = [desc for desc in EXPENSE_DESCRIPTIONS if CONFIG['EXPENSE_CODES'][desc] != "E101"]

# --- Helper Functions ---
def _find_timekeeper_by_name(timekeepers: List[Dict], name: str) -> Optional[Dict]:
    """Find a timekeeper by name (case-insensitive)."""
    if not timekeepers:
        return None
    for tk in timekeepers:
        if str(tk.get("TIMEKEEPER_NAME", "")).strip().lower() == str(name).strip().lower():
            return tk
    return None

def _force_timekeeper_on_row(row: Dict, forced_name: str, timekeepers: List[Dict]) -> Dict:
    """Assign timekeeper details to a row if applicable."""
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
    except Exception as e:
        logging.error(f"Error setting timekeeper rate: {e}")
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

def _is_valid_client_id(client_id: str) -> bool:
    """Validate Client ID format (XX-XXXXXXX)."""
    pattern = r"^\d{2}-\d{7}$"
    return bool(re.match(pattern, client_id))

def _is_valid_law_firm_id(law_firm_id: str) -> bool:
    """Validate Law Firm ID format (XX-XXXXXXX)."""
    pattern = r"^\d{2}-\d{7}$"
    return bool(re.match(pattern, law_firm_id))

def _calculate_max_fees(timekeeper_data: Optional[List[Dict]], billing_start_date: datetime.date, billing_end_date: datetime.date, max_daily_hours: int) -> int:
    """Calculate maximum feasible fee lines based on timekeeper data and billing period."""
    if not timekeeper_data:
        return 1
    num_timekeepers = len(timekeeper_data)
    delta = billing_end_date - billing_start_date
    num_days = max(1, delta.days + 1)
    max_lines = int((num_timekeepers * num_days * max_daily_hours) / 0.5)
    return max(1, min(200, max_lines))

def _load_timekeepers(uploaded_file: Optional[Any]) -> Optional[List[Dict]]:
    """Load timekeepers from CSV file."""
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
        logging.error(f"Timekeeper load error: {e}")
        return None

def _load_custom_task_activity_data(uploaded_file: Optional[Any]) -> Optional[List[Tuple[str, str, str]]]:
    """Load custom task/activity data from CSV."""
    if uploaded_file is None:
        return None
    try:
        df = pd.read_csv(uploaded_file)
        required_cols = ["TASK_CODE", "ACTIVITY_CODE", "DESCRIPTION"]
        if not all(col in df.columns for col in required_cols):
            st.error(f"Custom Task/Activity CSV must contain the following columns: {', '.join(required_cols)}")
            return None
        if df.empty:
            st.warning("Custom Task/Activity CSV file is empty.")
            return []
        custom_tasks = []
        for _, row in df.iterrows():
            custom_tasks.append((str(row["TASK_CODE"]), str(row["ACTIVITY_CODE"]), str(row["DESCRIPTION"])))
        return custom_tasks
    except Exception as e:
        st.error(f"Error loading custom tasks file: {e}")
        logging.error(f"Custom tasks load error: {e}")
        return None

def _create_ledes_line_1998b(row: Dict, line_no: int, inv_total: float, bill_start: datetime.date, bill_end: datetime.date, invoice_number: str, matter_number: str) -> List[str]:
    """Create a single LEDES 1998B line."""
    try:
        date_obj = datetime.datetime.strptime(row["LINE_ITEM_DATE"], "%Y-%m-%d").date()
        hours = float(row["HOURS"])
        rate = float(row["RATE"])
        line_total = float(row["LINE_ITEM_TOTAL"])
        is_expense = bool(row["EXPENSE_CODE"])
        adj_type = "E" if is_expense else "F"
        task_code = "" if is_expense else row.get("TASK_CODE", "")
        activity_code = "" if is_expense else row.get("ACTIVITY_CODE", "")
        expense_code = row.get("EXPENSE_CODE", "") if is_expense else ""
        timekeeper_id = "" if is_expense else row.get("TIMEKEEPER_ID", "")
        timekeeper_class = "" if is_expense else row.get("TIMEKEEPER_CLASSIFICATION", "")
        timekeeper_name = "" if is_expense else row.get("TIMEKEEPER_NAME", "")
        description = str(row.get("DESCRIPTION", "")).replace("|", " - ")
        return [
            bill_end.strftime("%Y%m%d"),
            invoice_number,
            str(row.get("CLIENT_ID", "")),
            matter_number,
            f"{inv_total:.2f}",
            bill_start.strftime("%Y%m%d"),
            bill_end.strftime("%Y%m%d"),
            str(row.get("INVOICE_DESCRIPTION", "")),
            str(line_no),
            adj_type,
            f"{hours:.1f}" if adj_type == "F" else f"{int(hours)}",
            "0.00",
            f"{line_total:.2f}",
            date_obj.strftime("%Y%m%d"),
            task_code,
            expense_code,
            activity_code,
            timekeeper_id,
            description,
            str(row.get("LAW_FIRM_ID", "")),
            f"{rate:.2f}",
            timekeeper_name,
            timekeeper_class,
            matter_number
        ]
    except Exception as e:
        logging.error(f"Error creating LEDES line: {e}")
        return []

def _create_ledes_1998b_content(rows: List[Dict], inv_total: float, bill_start: datetime.date, bill_end: datetime.date, invoice_number: str, matter_number: str) -> str:
    """Generate LEDES 1998B content from invoice rows."""
    header = "LEDES1998B[]"
    fields = ("INVOICE_DATE|INVOICE_NUMBER|CLIENT_ID|LAW_FIRM_MATTER_ID|INVOICE_TOTAL|BILLING_START_DATE|"
              "BILLING_END_DATE|INVOICE_DESCRIPTION|LINE_ITEM_NUMBER|EXP/FEE/INV_ADJ_TYPE|"
              "LINE_ITEM_NUMBER_OF_UNITS|LINE_ITEM_ADJUSTMENT_AMOUNT|LINE_ITEM_TOTAL|LINE_ITEM_DATE|"
              "LINE_ITEM_TASK_CODE|LINE_ITEM_EXPENSE_CODE|LINE_ITEM_ACTIVITY_CODE|TIMEKEEPER_ID|"
              "LINE_ITEM_DESCRIPTION|LAW_FIRM_ID|LINE_ITEM_UNIT_COST|TIMEKEEPER_NAME|"
              "TIMEKEEPER_CLASSIFICATION|CLIENT_MATTER_ID[]")
    lines = [header, fields]
    for i, row in enumerate(rows, start=1):
        line = _create_ledes_line_1998b(row, i, inv_total, bill_start, bill_end, invoice_number, matter_number)
        if line:
            lines.append("|".join(map(str, line)) + "[]")
    return "\n".join(lines)

def _generate_fees(fee_count: int, timekeeper_data: List[Dict], billing_start_date: datetime.date, billing_end_date: datetime.date, task_activity_desc: List[Tuple[str, str, str]], major_task_codes: set, max_hours_per_tk_per_day: int, faker_instance: Faker, client_id: str, law_firm_id: str, invoice_desc: str) -> List[Dict]:
    """Generate fee line items for an invoice."""
    rows = []
    delta = billing_end_date - billing_start_date
    num_days = max(1, delta.days + 1)
    major_items = [item for item in task_activity_desc if item[0] in major_task_codes]
    other_items = [item for item in task_activity_desc if item[0] not in major_task_codes]
    daily_hours_tracker = {}
    MAX_DAILY_HOURS = max_hours_per_tk_per_day

    for _ in range(fee_count):
        if not task_activity_desc:
            break
        tk_row = random.choice(timekeeper_data)
        timekeeper_id = tk_row["TIMEKEEPER_ID"]
        if major_items and random.random() < 0.7:
            task_code, activity_code, description = random.choice(major_items)
        elif other_items:
            task_code, activity_code, description = random.choice(other_items)
        else:
            continue
        random_day_offset = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=random_day_offset)
        line_item_date_str = line_item_date.strftime("%Y-%m-%d")
        current_billed_hours = daily_hours_tracker.get((line_item_date_str, timekeeper_id), 0)
        remaining_hours_capacity = MAX_DAILY_HOURS - current_billed_hours
        if remaining_hours_capacity <= 0:
            continue
        hours_to_bill = round(random.uniform(0.5, min(8.0, remaining_hours_capacity)), 1)
        if hours_to_bill == 0:
            continue
        hourly_rate = tk_row["RATE"]
        line_item_total = round(hours_to_bill * hourly_rate, 2)
        daily_hours_tracker[(line_item_date_str, timekeeper_id)] = current_billed_hours + hours_to_bill
        description = _process_description(description, faker_instance)
        row = {
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": line_item_date_str, "TIMEKEEPER_NAME": tk_row["TIMEKEEPER_NAME"],
            "TIMEKEEPER_CLASSIFICATION": tk_row["TIMEKEEPER_CLASSIFICATION"],
            "TIMEKEEPER_ID": timekeeper_id, "TASK_CODE": task_code,
            "ACTIVITY_CODE": activity_code, "EXPENSE_CODE": "", "DESCRIPTION": description,
            "HOURS": hours_to_bill, "RATE": hourly_rate, "LINE_ITEM_TOTAL": line_item_total
        }
        rows.append(row)
    return rows

def _generate_expenses(expense_count: int, billing_start_date: datetime.date, billing_end_date: datetime.date, client_id: str, law_firm_id: str, invoice_desc: str) -> List[Dict]:
    """Generate expense line items for an invoice."""
    rows = []
    delta = billing_end_date - billing_start_date
    num_days = max(1, delta.days + 1)
    e101_actual_count = random.randint(1, min(3, expense_count))
    for _ in range(e101_actual_count):
        description = "Copying"
        expense_code = "E101"
        hours = random.randint(1, 200)
        rate = round(random.uniform(0.14, 0.25), 2)
        random_day_offset = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=random_day_offset)
        line_item_total = round(hours * rate, 2)
        row = {
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": "",
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "", "TASK_CODE": "",
            "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
            "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": line_item_total
        }
        rows.append(row)
    
    for _ in range(expense_count - e101_actual_count):
        description = random.choice(OTHER_EXPENSE_DESCRIPTIONS)
        expense_code = CONFIG['EXPENSE_CODES'][description]
        hours = random.randint(1, 100)
        rate = round(random.uniform(5.0, 100.0), 2)
        random_day_offset = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=random_day_offset)
        line_item_total = round(hours * rate, 2)
        row = {
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": "",
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "", "TASK_CODE": "",
            "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
            "HOURS": hours, "RATE": rate, "LINE_ITEM_TOTAL": line_item_total
        }
        rows.append(row)
    return rows

def _generate_invoice_data(fee_count: int, expense_count: int, timekeeper_data: List[Dict], client_id: str, law_firm_id: str, invoice_desc: str, billing_start_date: datetime.date, billing_end_date: datetime.date, task_activity_desc: List[Tuple[str, str, str]], major_task_codes: set, max_hours_per_tk_per_day: int, include_block_billed: bool, faker_instance: Faker) -> Tuple[List[Dict], float]:
    """Generate invoice data with fees and expenses."""
    rows = []
    rows.extend(_generate_fees(fee_count, timekeeper_data, billing_start_date, billing_end_date, task_activity_desc, major_task_codes, max_hours_per_tk_per_day, faker_instance, client_id, law_firm_id, invoice_desc))
    rows.extend(_generate_expenses(expense_count, billing_start_date, billing_end_date, client_id, law_firm_id, invoice_desc))
    total_amount = sum(float(row["LINE_ITEM_TOTAL"]) for row in rows)
    
    if include_block_billed and rows:
        block_billed_rows = []
        block_size = random.randint(2, 5)
        selected_rows = random.sample(rows, min(block_size, len(rows)))
        total_hours = sum(float(row["HOURS"]) for row in selected_rows)
        total_amount_block = sum(float(row["LINE_ITEM_TOTAL"]) for row in selected_rows)
        descriptions = [row["DESCRIPTION"] for row in selected_rows]
        block_description = "; ".join(descriptions)
        block_row = {
            "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
            "LINE_ITEM_DATE": selected_rows[0]["LINE_ITEM_DATE"], "TIMEKEEPER_NAME": selected_rows[0]["TIMEKEEPER_NAME"],
            "TIMEKEEPER_CLASSIFICATION": selected_rows[0]["TIMEKEEPER_CLASSIFICATION"],
            "TIMEKEEPER_ID": selected_rows[0]["TIMEKEEPER_ID"], "TASK_CODE": selected_rows[0]["TASK_CODE"],
            "ACTIVITY_CODE": selected_rows[0]["ACTIVITY_CODE"], "EXPENSE_CODE": "",
            "DESCRIPTION": block_description, "HOURS": total_hours, "RATE": selected_rows[0]["RATE"],
            "LINE_ITEM_TOTAL": total_amount_block
        }
        rows = [row for row in rows if row not in selected_rows]
        rows.append(block_row)
        total_amount = sum(float(row["LINE_ITEM_TOTAL"]) for row in rows)
    
    return rows, total_amount

def _ensure_mandatory_lines(rows: List[Dict], timekeeper_data: List[Dict], invoice_desc: str, client_id: str, law_firm_id: str, billing_start_date: datetime.date, billing_end_date: datetime.date, selected_items: List[str]) -> List[Dict]:
    """Ensure mandatory line items are included."""
    delta = billing_end_date - billing_start_date
    num_days = max(1, delta.days + 1)
    for item_name in selected_items:
        item = CONFIG['MANDATORY_ITEMS'][item_name]
        random_day_offset = random.randint(0, num_days - 1)
        line_item_date = billing_start_date + datetime.timedelta(days=random_day_offset)
        if item['is_expense']:
            row = {
                "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
                "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": "",
                "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "", "TASK_CODE": "",
                "ACTIVITY_CODE": "", "EXPENSE_CODE": item['expense_code'], "DESCRIPTION": item['desc'],
                "HOURS": random.randint(1, 10), "RATE": round(random.uniform(5.0, 100.0), 2)
            }
            row["LINE_ITEM_TOTAL"] = round(row["HOURS"] * row["RATE"], 2)
        else:
            row = {
                "INVOICE_DESCRIPTION": invoice_desc, "CLIENT_ID": client_id, "LAW_FIRM_ID": law_firm_id,
                "LINE_ITEM_DATE": line_item_date.strftime("%Y-%m-%d"), "TIMEKEEPER_NAME": item['tk_name'],
                "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "", "TASK_CODE": item['task'],
                "ACTIVITY_CODE": item['activity'], "EXPENSE_CODE": "", "DESCRIPTION": item['desc'],
                "HOURS": round(random.uniform(0.5, 8.0), 1), "RATE": 0.0
            }
            row = _force_timekeeper_on_row(row, item['tk_name'], timekeeper_data)
        rows.append(row)
    return rows

def _validate_image_bytes(image_bytes: bytes) -> bool:
    """Validate that the provided bytes represent a valid image."""
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        img.verify()
        return True
    except Exception:
        return False

def _get_logo_bytes(uploaded_logo: Optional[Any], law_firm_id: str) -> bytes:
    """Get logo bytes from uploaded file or default path."""
    if uploaded_logo:
        try:
            logo_bytes = uploaded_logo.read()
            if _validate_image_bytes(logo_bytes):
                return logo_bytes
            st.warning("Uploaded logo is not a valid JPEG or PNG. Using default logo.")
        except Exception as e:
            logging.error(f"Error reading uploaded logo: {e}")
            st.warning("Failed to read uploaded logo. Using default logo.")
    
    logo_file_name = "nelsonmurdock2.jpg" if law_firm_id == CONFIG['DEFAULT_LAW_FIRM_ID'] else "icon.jpg"
    script_dir = os.path.dirname(__file__)
    logo_path = os.path.join(script_dir, "assets", logo_file_name)
    try:
        with open(logo_path, "rb") as f:
            logo_bytes = f.read()
        if _validate_image_bytes(logo_bytes):
            return logo_bytes
        st.warning(f"Default logo ({logo_file_name}) is not a valid JPEG or PNG. Using placeholder.")
    except Exception as e:
        logging.error(f"Logo load failed: {e}")
        st.warning(f"Logo file ({logo_file_name}) not found or invalid. Using placeholder.")
    
    img = PILImage.new("RGB", (128, 128), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 20), "Logo", font=font, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

def _create_pdf_invoice(df: pd.DataFrame, total_amount: float, invoice_number: str, invoice_date: datetime.date, billing_start_date: datetime.date, billing_end_date: datetime.date, client_id: str, law_firm_id: str, logo_bytes: bytes, include_logo: bool = True) -> io.BytesIO:
    """Generate a PDF invoice."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    heading_style = ParagraphStyle(name='Heading', fontSize=12, leading=14, alignment=TA_LEFT)
    right_align_style = ParagraphStyle(name='RightAlign', fontSize=10, leading=12, alignment=TA_RIGHT)
    
    law_firm_info = "Nelson & Murdock, Attorneys at Law<br/>315 W 45th St, New York, NY 10036" if law_firm_id == CONFIG['DEFAULT_LAW_FIRM_ID'] else "Generic Law Firm<br/>123 Main St, Anytown, USA"
    law_firm_para = Paragraph(law_firm_info, normal_style)
    header_left_content = law_firm_para
    if include_logo:
        try:
            if not _validate_image_bytes(logo_bytes):
                raise ValueError("Invalid logo bytes")
            img = Image(io.BytesIO(logo_bytes), width=0.6 * inch, height=0.6 * inch, kind='direct', hAlign='LEFT')
            img._restrictSize(0.6 * inch, 0.6 * inch)
            img.alt = "Law Firm Logo"
            inner_table_data = [[img, law_firm_para]]
            inner_table = Table(inner_table_data, colWidths=[0.7 * inch, None])
            inner_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (1, 0), (1, 0), 6),
            ]))
            header_left_content = inner_table
        except Exception as e:
            logging.error(f"Error adding logo to PDF: {e}")
            st.warning("Could not add logo to PDF. Using text instead.")
    
    client_info = f"Client ID: {client_id}<br/>Attn: Billing Department"
    client_para = Paragraph(client_info, normal_style)
    invoice_info = f"Invoice #: {invoice_number}<br/>Invoice Date: {invoice_date.strftime('%Y-%m-%d')}<br/>Billing Period: {billing_start_date.strftime('%Y-%m-%d')} to {billing_end_date.strftime('%Y-%m-%d')}"
    invoice_para = Paragraph(invoice_info, right_align_style)
    header_data = [[header_left_content, invoice_para]]
    header_table = Table(header_data, colWidths=[4.5 * inch, 3.5 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.25 * inch))
    
    elements.append(Paragraph("Invoice", heading_style))
    elements.append(Spacer(1, 0.1 * inch))
    
    data = [["Date", "Description", "Timekeeper", "Hours/Units", "Rate", "Total"]]
    for _, row in df.iterrows():
        date = row["LINE_ITEM_DATE"]
        description = row["DESCRIPTION"]
        timekeeper = row["TIMEKEEPER_NAME"] if row["TIMEKEEPER_NAME"] else "N/A"
        hours = f"{row['HOURS']:.1f}" if not row["EXPENSE_CODE"] else f"{int(row['HOURS'])}"
        rate = f"${row['RATE']:.2f}" if row["RATE"] else "N/A"
        total = f"${row['LINE_ITEM_TOTAL']:.2f}"
        data.append([date, description, timekeeper, hours, rate, total])
    
    table = Table(data, colWidths=[1 * inch, 2.5 * inch, 1.5 * inch, 1 * inch, 1 * inch, 1 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    
    elements.append(Spacer(1, 0.25 * inch))
    total_para = Paragraph(f"Total: ${total_amount:.2f}", right_align_style)
    elements.append(total_para)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def _customize_email_body(matter_number: str, invoice_number: str) -> Tuple[str, str]:
    """Customize email subject and body with matter and invoice number."""
    subject = st.session_state.get("email_subject", f"LEDES Invoice for {matter_number} (Invoice #{invoice_number})")
    body = st.session_state.get("email_body", f"Please find the attached invoice files for matter {matter_number}.\n\nBest regards,\nYour Law Firm")
    subject = subject.format(matter_number=matter_number, invoice_number=invoice_number)
    body = body.format(matter_number=matter_number, invoice_number=invoice_number)
    return subject, body

def _send_email_with_attachment(recipient_email: str, subject: str, body: str, attachments: List[Tuple[str, bytes]]) -> bool:
    """Send email with attachments."""
    try:
        sender_email = st.secrets.email.email_from
        password = st.secrets.email.email_password
    except AttributeError:
        st.error("Email credentials not configured in secrets.toml")
        return False
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))
    for filename, data in attachments:
        part = MIMEApplication(data, Name=filename)
        part['Content-Disposition'] = f'attachment; filename="{filename}"'
        msg.attach(part)
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
        st.success(f"Email sent successfully to {recipient_email}!")
        return True
    except Exception as e:
        st.error(f"Error sending email: {e}")
        logging.error(f"Email sending failed: {e}")
        return False

# --- Streamlit App ---
st.markdown("<h1 style='color: #1E1E1E;'>LEDES Invoice Generator</h1>", unsafe_allow_html=True)
st.markdown("Generate and optionally email LEDES and PDF invoices.", unsafe_allow_html=True)

# Initialize send_email in session state
if "send_email" not in st.session_state:
    st.session_state.send_email = False

# Callback for updating send_email state
def update_send_email():
    st.session_state.send_email = st.session_state.send_email_checkbox
    logging.debug(f"Updated st.session_state.send_email to {st.session_state.send_email}")

with st.expander("Help & FAQs"):
    st.markdown("""
    ### FAQs
    - **What is Spend Agent mode?** Ensures specific mandatory line items (e.g., KBCG, John Doe, Uber E110) are included for testing or compliance. Select items in the Advanced Settings tab.
    - **How to format timekeeper CSV?** Columns: TIMEKEEPER_NAME, TIMEKEEPER_CLASSIFICATION, TIMEKEEPER_ID, RATE  
      Example: "John Doe,Partner,TK001,300.0"
    - **How to format custom tasks CSV?** Columns: TASK_CODE, ACTIVITY_CODE, DESCRIPTION  
      Example: "L100,A101,Legal Research: Analyze legal precedents"
    - **How to use a custom logo?** Upload a valid JPG or PNG image file in the Advanced Settings tab when PDF output is enabled. Only JPEG and PNG formats are supported. Other formats (e.g., GIF, BMP) will be converted to PNG. Maximum file size is 5MB. Ensure the image is not corrupted and displays correctly in an image viewer. If no logo is uploaded, the default logo (assets/nelsonmurdock2.jpg or assets/icon.jpg) or a placeholder will be used.
    - **What if my logo doesn’t appear in the PDF?** Check that the file is a valid JPEG or PNG, not corrupted, and under 5MB. Try re-saving the image using an image editor. If issues persist, enable logging to debug (see Advanced Settings for custom default logo path).
    """)

st.markdown("<h3 style='color: #1E1E1E;'>Output & Delivery Options</h3>", unsafe_allow_html=True)
st.checkbox(
    "Send Invoices via Email",
    value=st.session_state.send_email,
    key="send_email_checkbox",
    on_change=update_send_email
)

# Sidebar
st.sidebar.markdown("<h2 style='color: #1E1E1E;'>Quick Links</h2>", unsafe_allow_html=True)
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

# Dynamic Tabs
tabs = ["File Upload", "Invoice Inputs", "Advanced Settings"]
if st.session_state.send_email:
    tabs.append("Email Configuration")
tab_objects = st.tabs(tabs)

with tab_objects[0]:
    st.markdown("<h3 style='color: #1E1E1E;'>File Upload</h3>", unsafe_allow_html=True)
    uploaded_timekeeper_file = st.file_uploader("Upload Timekeeper CSV (tk_info.csv)", type="csv")
    timekeeper_data = _load_timekeepers(uploaded_timekeeper_file)

    use_custom_tasks = st.checkbox("Use Custom Line Item Details?", value=True)
    uploaded_custom_tasks_file = None
    if use_custom_tasks:
        uploaded_custom_tasks_file = st.file_uploader("Upload Custom Line Items CSV (custom_details.csv)", type="csv")
    
    task_activity_desc = CONFIG['DEFAULT_TASK_ACTIVITY_DESC']
    if use_custom_tasks and uploaded_custom_tasks_file:
        custom_tasks_data = _load_custom_task_activity_data(uploaded_custom_tasks_file)
        if custom_tasks_data:
            task_activity_desc = custom_tasks_data

with tab_objects[1]:
    st.markdown("<h2 style='color: #1E1E1E;'>Invoice Details</h2>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #1E1E1E;'>Billing Information</h3>", unsafe_allow_html=True)
    client_id = st.text_input("Client ID:", CONFIG['DEFAULT_CLIENT_ID'], help="Format: XX-XXXXXXX (e.g., 02-4388252)")
    law_firm_id = st.text_input("Law Firm ID:", CONFIG['DEFAULT_LAW_FIRM_ID'], help="Format: XX-XXXXXXX (e.g., 02-1234567)")
    matter_number_base = st.text_input("Matter Number:", "2025-XXXXXX")
    invoice_number_base = st.text_input("Invoice Number (Base):", "2025MMM-XXXXXX")
    LEDES_OPTIONS = ["1998B", "XML 2.1"]
    ledes_version = st.selectbox(
        "LEDES Version:",
        LEDES_OPTIONS,
        key="ledes_version",
        help="XML 2.1 export is not implemented yet; please use 1998B."
    )

    if ledes_version == "XML 2.1":
        st.warning("This is not yet implemented - please use 1998B")

    st.markdown("<h3 style='color: #1E1E1E;'>Invoice Dates & Description</h3>", unsafe_allow_html=True)
    today = datetime.date.today()
    first_day_of_current_month = today.replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - datetime.timedelta(days=1)
    first_day_of_previous_month = last_day_of_previous_month.replace(day=1)
    billing_start_date = st.date_input("Billing Start Date", value=first_day_of_previous_month)
    billing_end_date = st.date_input("Billing End Date", value=last_day_of_previous_month)
    invoice_desc = st.text_area(
        "Invoice Description (One per period, each on a new line)",
        value="Professional Services Rendered",
        height=150
    )

with tab_objects[2]:
    st.markdown("<h2 style='color: #1E1E1E;'>Generation Settings</h2>", unsafe_allow_html=True)
    spend_agent = st.checkbox("Spend Agent", value=False, help="Ensures selected mandatory line items are included; configure below.")
    
    if timekeeper_data is None:
        st.error("Please upload a valid timekeeper CSV file to configure fee and expense settings.")
        fees = 0
        expenses = 0
    else:
        max_fees = _calculate_max_fees(timekeeper_data, billing_start_date, billing_end_date, 16)
        st.caption(f"Maximum fee lines allowed: {max_fees} (based on timekeepers and billing period)")
        fees = st.slider(
            "Number of Fee Line Items",
            min_value=1,
            max_value=max_fees,
            value=min(20, max_fees),
            format="%d"
        )
        st.caption("Number of expense line items to generate")
        expenses = st.slider(
            "Number of Expense Line Items",
            min_value=0,
            max_value=50,
            value=5,
            format="%d"
        )
    max_daily_hours = st.number_input("Max Daily Timekeeper Hours:", min_value=1, max_value=24, value=16, step=1)
    
    if spend_agent:
        st.markdown("<h3 style='color: #1E1E1E;'>Mandatory Items</h3>", unsafe_allow_html=True)
        selected_items = st.multiselect("Select Mandatory Items to Include", list(CONFIG['MANDATORY_ITEMS'].keys()), default=list(CONFIG['MANDATORY_ITEMS'].keys()))
    else:
        selected_items = []
    
    st.markdown("<h3 style='color: #1E1E1E;'>Output Settings</h3>", unsafe_allow_html=True)
    include_block_billed = st.checkbox("Include Block Billed Line Items", value=True)
    include_pdf = st.checkbox("Include PDF Invoice", value=False)
    
    uploaded_logo = None
    logo_width = None
    logo_height = None
    
    if include_pdf:
        include_logo = st.checkbox("Include Logo in PDF", value=True, help="Uncheck to exclude logo from PDF header, using only law firm text.")
        if include_logo:
            default_logo_path = st.text_input("Custom Default Logo Path (Optional):", help="Enter the path to a custom default logo (JPEG/PNG). Leave blank to use assets/nelsonmurdock2.jpg or assets/icon.jpg.")
            uploaded_logo = st.file_uploader(
                "Upload Custom Logo (JPG/PNG)",
                type=["jpg", "png", "jpeg"],
                help="Upload a valid JPG or PNG image file (e.g., logo.jpg or logo.png). Only JPEG and PNG formats are supported."
            )
            logo_width = st.slider("Logo Width (inches):", 0.5, 2.0, 0.6, step=0.1)
            logo_height = st.slider("Logo Height (inches):", 0.5, 2.0, 0.6, step=0.1)
    
    generate_multiple = st.checkbox("Generate Multiple Invoices", help="Create more than one invoice.")
    num_invoices = 1
    multiple_periods = False
    if generate_multiple:
        multiple_periods = st.checkbox("Multiple Billing Periods", help="Backfills one invoice per prior month from the given end date, newest to oldest.")
        if multiple_periods:
            num_periods = st.number_input("How Many Billing Periods:", min_value=2, max_value=6, value=2, step=1, help="Number of month-long periods to create (overrides Number of Invoices).")
            num_invoices = num_periods
        else:
            num_invoices = st.number_input("Number of Invoices to Create:", min_value=1, value=1, step=1, help="Creates N invoices. When 'Multiple Billing Periods' is enabled, one invoice per period.")

# Email Configuration Tab (only created if send_email is True)
if st.session_state.send_email:
    email_tab_index = len(tabs) - 1  # Index of Email Configuration tab
    with tab_objects[email_tab_index]:
        st.markdown("<h2 style='color: #1E1E1E;'>Email Configuration</h2>", unsafe_allow_html=True)
        recipient_email = st.text_input("Recipient Email Address:")
        try:
            sender_email = st.secrets.email.email_from
            st.caption(f"Sender Email will be from: {sender_email}")
        except AttributeError:
            st.caption("Sender Email: Not configured (check secrets.toml)")
        st.text_input("Email Subject Template:", value=f"LEDES Invoice for {matter_number_base} (Invoice #{{invoice_number}})", key="email_subject")
        st.text_area("Email Body Template:", value=f"Please find the attached invoice files for matter {{matter_number}}.\n\nBest regards,\nYour Law Firm", height=150, key="email_body")
else:
    recipient_email = ""  # Initialize to avoid undefined variable in validation

# Validation Logic
is_valid_input = True
if timekeeper_data is None:
    st.error("Please upload a valid timekeeper CSV file.")
    is_valid_input = False
if billing_start_date >= billing_end_date:
    st.error("Billing start date must be before end date.")
    is_valid_input = False
if not _is_valid_client_id(client_id):
    st.error("Client ID must be in format XX-XXXXXXX (e.g., 02-4388252).")
    is_valid_input = False
if not _is_valid_law_firm_id(law_firm_id):
    st.error("Law Firm ID must be in format XX-XXXXXXX (e.g., 02-1234567).")
    is_valid_input = False
if st.session_state.send_email and not recipient_email:
    st.error("Please provide a recipient email address.")
    is_valid_input = False

st.markdown("---")
generate_button = st.button("Generate Invoice(s)", disabled=not is_valid_input)

# Main App Logic
if generate_button:
    if ledes_version == "XML 2.1":
        st.error("LEDES XML 2.1 is not yet implemented. Please switch to 1998B.")
        st.stop()
    
    faker = Faker()
    descriptions = [d.strip() for d in invoice_desc.split('\n') if d.strip()]
    num_invoices = int(num_invoices)
    
    if multiple_periods and len(descriptions) != num_invoices:
        st.warning(f"You have selected to generate {num_invoices} invoices, but provided {len(descriptions)} descriptions. Please provide one description per period.")
    else:
        attachments_list = []
        with st.status("Generating invoices...") as status:
            for i in range(num_invoices):
                current_start_date = billing_start_date
                current_end_date = billing_end_date
                if multiple_periods:
                    current_end_date = billing_end_date - datetime.timedelta(days=i * 30)
                    current_start_date = current_end_date.replace(day=1)
                status.update(label=f"Generating Invoice {i+1}/{num_invoices} for period {current_start_date} to {current_end_date}")
                
                current_invoice_desc = descriptions[i] if multiple_periods and i < len(descriptions) else descriptions[0]
                fees_used = max(0, fees - (2 if spend_agent and selected_items else 0))
                expenses_used = max(0, expenses - (1 if spend_agent and 'Uber E110' in selected_items else 0))
                
                rows, total_amount = _generate_invoice_data(
                    fees_used, expenses_used, timekeeper_data, client_id, law_firm_id,
                    current_invoice_desc, current_start_date, current_end_date,
                    task_activity_desc, CONFIG['MAJOR_TASK_CODES'], max_daily_hours, include_block_billed, faker
                )
                if spend_agent:
                    rows = _ensure_mandatory_lines(rows, timekeeper_data, current_invoice_desc, client_id, law_firm_id, current_start_date, current_end_date, selected_items)
                
                df_invoice = pd.DataFrame(rows)
                current_invoice_number = f"{invoice_number_base}-{i+1}"
                current_matter_number = matter_number_base
                ledes_content = _create_ledes_1998b_content(rows, total_amount, current_start_date, current_end_date, current_invoice_number, current_matter_number)
                
                attachments_to_send = []
                ledes_filename = f"LEDES_1998B_{current_invoice_number}.txt"
                attachments_to_send.append((ledes_filename, ledes_content.encode('utf-8')))
                
                if include_pdf:
                    logo_bytes = _get_logo_bytes(uploaded_logo, law_firm_id)
                    pdf_buffer = _create_pdf_invoice(df_invoice, total_amount, current_invoice_number, current_end_date, current_start_date, current_end_date, client_id, law_firm_id, logo_bytes, include_logo)
                    pdf_filename = f"Invoice_{current_invoice_number}.pdf"
                    attachments_to_send.append((pdf_filename, pdf_buffer.getvalue()))
                
                if st.session_state.send_email:
                    subject, body = _customize_email_body(current_matter_number, current_invoice_number)
                    if not _send_email_with_attachment(recipient_email, subject, body, attachments_to_send):
                        st.subheader(f"Invoice {i + 1} (Failed to Email)")
                        for filename, data in attachments_to_send:
                            st.download_button(
                                label=f"Download {filename}",
                                data=data,
                                file_name=filename,
                                mime="text/plain" if filename.endswith(".txt") else "application/pdf",
                                key=f"download_{filename}_{i}"
                            )
                else:
                    attachments_list.extend(attachments_to_send)
                
                if multiple_periods:
                    billing_end_date = current_start_date - datetime.timedelta(days=1)
                    billing_start_date = billing_end_date.replace(day=1)
            
            if not st.session_state.send_email and num_invoices > 1:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filename, data in attachments_list:
                        zip_file.writestr(filename, data)
                zip_buf.seek(0)
                st.download_button(
                    label="Download All Invoices as ZIP",
                    data=zip_buf.getvalue(),
                    file_name="invoices.zip",
                    mime="application/zip",
                    key="download_zip"
                )
            elif not st.session_state.send_email:
                st.subheader("Generated Invoice(s)")
                for filename, data in attachments_list:
                    st.download_button(
                        label=f"Download {filename}",
                        data=data,
                        file_name=filename,
                        mime="text/plain" if filename.endswith(".txt") else "application/pdf",
                        key=f"download_{filename}"
                    )
            status.update(label="Invoice generation complete!", state="complete")
