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
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
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
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
            "TASK_CODE": "", "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
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
            "TIMEKEEPER_CLASSIFICATION": "", "TIMEKEEPER_ID": "",
            "TASK_CODE": "", "ACTIVITY_CODE": "", "EXPENSE_CODE": expense_code, "DESCRIPTION": description,
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
    """Generate a PDF invoice matching the provided format."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Define new styles
    header_info_style = ParagraphStyle(
        'HeaderInfo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        alignment=TA_LEFT
    )
    client_info_style = ParagraphStyle(
        'ClientInfo',
        parent=header_info_style,
        alignment=TA_RIGHT
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        alignment=TA_CENTER,
        wordWrap='CJK'
    )
    table_data_style = ParagraphStyle(
        'TableData',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=12,
        alignment=TA_LEFT,
        wordWrap='CJK'
    )
    right_align_style = styles['Heading4']

    # Header with Law Firm on left and Client on right
    law_firm_info = f"Nelson and Murdock<br/>{law_firm_id}<br/>One Park Avenue<br/>Manhattan, NY 10003"
    client_info = f"A Onit Inc.<br/>{client_id}<br/>1360 Post Oak Blvd<br/>Houston, TX 77056"
    law_firm_para = Paragraph(law_firm_info, header_info_style)
    client_para = Paragraph(client_info, client_info_style)

    header_left_content = law_firm_para
    if include_logo:
        try:
            if not _validate_image_bytes(logo_bytes):
                raise ValueError("Invalid logo bytes")
            img = Image(io.BytesIO(logo_bytes), width=0.6 * inch, height=0.6 * inch, kind='direct', hAlign='LEFT')
            img._restrictSize(0.6 * inch, 0.6 * inch)
            img.alt = "Law Firm Logo"
            inner_table_data = [[img, law_firm_para]]
            header_left_content = Table(inner_table_data, colWidths=[0.8 * inch, 3 * inch], style=[('VALIGN', (0, 0), (-1, -1), 'MIDDLE')])
        except Exception:
            pass

    header_table_data = [
        [header_left_content, client_para]
    ]
    header_table = Table(header_table_data, colWidths=[4 * inch, 3 * inch], hAlign='LEFT')
    elements.append(header_table)

    # Invoice details
    invoice_details_data = [
        ['Invoice Number:', invoice_number],
        ['Date:', invoice_date.strftime('%Y-%m-%d')],
        ['Matter:', f'{client_id}'],
        ['Period:', f"{billing_start_date.strftime('%b %d, %Y')} - {billing_end_date.strftime('%b %d, %Y')}"]
    ]
    invoice_details_table = Table(invoice_details_data, colWidths=[1.5 * inch, 2.5 * inch])
    invoice_details_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.darkslategray)
    ]))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(invoice_details_table)
    elements.append(Spacer(1, 0.4*inch))

    # Data Table
    df_fees = df[df['EXPENSE_CODE'] == '']
    df_expenses = df[df['EXPENSE_CODE'] != '']

    fee_rows = df_fees[['LINE_ITEM_DATE', 'TIMEKEEPER_NAME', 'TASK_CODE', 'DESCRIPTION', 'HOURS', 'LINE_ITEM_TOTAL']].values.tolist()
    expense_rows = df_expenses[['LINE_ITEM_DATE', 'EXPENSE_CODE', 'DESCRIPTION', 'HOURS', 'LINE_ITEM_TOTAL']].values.tolist()

    data_table_headers = [
        Paragraph("Date", table_header_style),
        Paragraph("Timekeeper/Expense", table_header_style),
        Paragraph("Code", table_header_style),
        Paragraph("Description", table_header_style),
        Paragraph("Hours/Units", table_header_style),
        Paragraph("Total", table_header_style)
    ]

    table_data = [data_table_headers]
    
    # Add fees to table
    for row in fee_rows:
        table_data.append([
            Paragraph(str(row[0]), table_data_style),
            Paragraph(str(row[1]), table_data_style),
            Paragraph(str(row[2]), table_data_style),
            Paragraph(str(row[3]), table_data_style),
            Paragraph(f"{float(row[4]):.1f}", styles['Normal']),
            Paragraph(f"${float(row[5]):,.2f}", right_align_style)
        ])
    
    # Add expenses to table
    if not df_fees.empty and not df_expenses.empty:
        table_data.append([Paragraph("Expenses:", table_header_style), '', '', '', '', ''])

    for row in expense_rows:
        table_data.append([
            Paragraph(str(row[0]), table_data_style),
            Paragraph(f"({str(row[1])})", table_data_style),
            '',
            Paragraph(str(row[2]), table_data_style),
            Paragraph(f"{float(row[3]):.0f}", styles['Normal']),
            Paragraph(f"${float(row[4]):,.2f}", right_align_style)
        ])

    table = Table(table_data, colWidths=[0.8*inch, 1.5*inch, 0.8*inch, 2.5*inch, 0.8*inch, 1.0*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
        ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
        ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
        ('RIGHTPADDING', (4, 1), (5, -1), 12),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('SPAN', (1, len(fee_rows) + 1), (5, len(fee_rows) + 1))
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.2*inch))

    # Totals Section
    total_fees = df_fees['LINE_ITEM_TOTAL'].sum() if not df_fees.empty else 0.00
    total_expenses = df_expenses['LINE_ITEM_TOTAL'].sum() if not df_expenses.empty else 0.00
    
    totals_data = [
        ['Total Fees:', f"${total_fees:,.2f}"],
        ['Total Expenses:', f"${total_expenses:,.2f}"],
        ['Invoice Total:', f"${total_amount:,.2f}"]
    ]
    
    totals_table = Table(totals_data, colWidths=[2*inch, 1*inch])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('BOX', (0, 0), (-1, -1), 0.25, colors.black)
    ]))
    
    # Create a wrapper table to align the totals table to the right
    wrapper_table = Table([
        ['', totals_table]
    ], colWidths=[5.5*inch, 1.5*inch])
    
    wrapper_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT')
    ]))

    elements.append(wrapper_table)
    elements.append(Spacer(1, 0.4*inch))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def _send_email_with_attachments(to_email: str, subject: str, body: str, attachments: List[Tuple[str, bytes]], from_email: str, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str):
    """Sends an email with multiple attachments."""
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body))
    
    for filename, filedata in attachments:
        part = MIMEApplication(filedata, Name=filename)
        part['Content-Disposition'] = f'attachment; filename="{filename}"'
        msg.attach(part)
    
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

def main():
    st.title("LEDES 1998B Invoice Generator")
    st.markdown("""
        Generate a sample LEDES 1998B file and a PDF invoice.
        The tool uses a base set of timekeepers and tasks, but you can upload your own.
        """)

    with st.expander("Configuration", expanded=False):
        # ... (unchanged)
        st.subheader("General Settings")
        invoice_number = st.text_input("Invoice Number", value=f"INV-{random.randint(1000, 9999)}-{datetime.date.today().strftime('%Y%m%d')}")
        invoice_description = st.text_input("Invoice Description", value=CONFIG['DEFAULT_INVOICE_DESCRIPTION'])
        matter_number = st.text_input("Matter Number", value="MATT-001")
        client_id = st.text_input("Client ID (e.g., 02-4388252)", value=CONFIG['DEFAULT_CLIENT_ID'])
        law_firm_id = st.text_input("Law Firm ID (e.g., 02-1234567)", value=CONFIG['DEFAULT_LAW_FIRM_ID'])
        if not _is_valid_client_id(client_id):
            st.error("Client ID format must be XX-XXXXXXX")
        if not _is_valid_law_firm_id(law_firm_id):
            st.error("Law Firm ID format must be XX-XXXXXXX")
        
        col1, col2 = st.columns(2)
        with col1:
            billing_start_date = st.date_input("Billing Period Start", datetime.date.today() - datetime.timedelta(days=30))
        with col2:
            billing_end_date = st.date_input("Billing Period End", datetime.date.today())

        st.subheader("Invoice Content")
        num_invoices = st.number_input("Number of Invoices to Generate", min_value=1, max_value=10, value=1)
        multiple_periods = st.checkbox("Generate invoices for consecutive monthly periods", value=False)
        st.markdown("_e.g., if you select 3 invoices, they will be for the past 3 months._")
        fee_line_count = st.number_input("Number of Fee Lines", min_value=1, max_value=200, value=10, step=5)
        expense_line_count = st.number_input("Number of Expense Lines", min_value=0, max_value=50, value=2)
        max_daily_hours = st.number_input("Max daily hours per timekeeper", min_value=1, max_value=24, value=8)
        include_block_billed = st.checkbox("Include Block Billed Line Item", value=False)
        
        st.subheader("Mandatory Line Items")
        mandatory_items = list(CONFIG['MANDATORY_ITEMS'].keys())
        selected_mandatory_items = st.multiselect("Select Mandatory Line Items to Include", mandatory_items, default=mandatory_items)

    with st.expander("Upload Custom Data", expanded=False):
        uploaded_timekeepers = st.file_uploader("Upload Timekeeper CSV (Optional)", type=['csv'], help="Requires TIMEKEEPER_NAME, TIMEKEEPER_CLASSIFICATION, TIMEKEEPER_ID, RATE columns.")
        uploaded_tasks = st.file_uploader("Upload Custom Task/Activity CSV (Optional)", type=['csv'], help="Requires TASK_CODE, ACTIVITY_CODE, DESCRIPTION columns.")
        uploaded_logo = st.file_uploader("Upload a Firm Logo (Optional)", type=['jpg', 'jpeg', 'png'])

    with st.expander("Email Settings (Optional)", expanded=False):
        send_email = st.checkbox("Send Invoices via Email")
        st.session_state.send_email = send_email
        if send_email:
            st.warning("Sending emails from this app requires an SMTP server configured. Please ensure you have the necessary credentials and a valid host/port.")
            smtp_host = st.text_input("SMTP Host")
            smtp_port = st.number_input("SMTP Port", value=587)
            smtp_user = st.text_input("SMTP Username")
            smtp_pass = st.text_input("SMTP Password", type="password")
            to_email = st.text_input("Recipient Email")
            email_subject = st.text_input("Email Subject", value="Your Legal Invoice")
            email_body = st.text_area("Email Body", value="Dear Client,\n\nPlease find your monthly legal invoice attached.\n\nSincerely,\nNelson and Murdock")

    if st.button("Generate Invoice"):
        if not _is_valid_client_id(client_id) or not _is_valid_law_firm_id(law_firm_id):
            st.error("Please correct the Client ID and Law Firm ID formats before generating the invoice.")
            st.stop()
            
        status = st.status("Generating invoice...", expanded=True)
        status.update(label="Loading data...", state="running")
        
        faker = Faker()
        timekeeper_data = _load_timekeepers(uploaded_timekeepers)
        if timekeeper_data is None:
            timekeeper_data = [{'TIMEKEEPER_NAME': f.name(), 'TIMEKEEPER_CLASSIFICATION': 'Partner', 'TIMEKEEPER_ID': f.uuid4(), 'RATE': round(random.uniform(250, 750), 2)} for f in [Faker() for _ in range(5)]]
            status.write("Using default timekeeper data.")
        
        custom_tasks = _load_custom_task_activity_data(uploaded_tasks)
        task_activity_desc = custom_tasks if custom_tasks is not None else CONFIG['DEFAULT_TASK_ACTIVITY_DESC']
        if custom_tasks is None:
            status.write("Using default task/activity data.")

        logo_bytes = _get_logo_bytes(uploaded_logo, law_firm_id)
        
        attachments_list = []
        current_start_date = billing_start_date
        current_end_date = billing_end_date
        
        for i in range(num_invoices):
            if multiple_periods and i > 0:
                # Adjust dates for the previous month
                last_day_of_prev_month = current_start_date - datetime.timedelta(days=1)
                first_day_of_prev_month = last_day_of_prev_month.replace(day=1)
                current_start_date = first_day_of_prev_month
                current_end_date = last_day_of_prev_month
                invoice_number = f"INV-{random.randint(1000, 9999)}-{current_end_date.strftime('%Y%m%d')}"
            
            invoice_rows, total_amount = _generate_invoice_data(fee_line_count, expense_line_count, timekeeper_data, client_id, law_firm_id, invoice_description, current_start_date, current_end_date, task_activity_desc, CONFIG['MAJOR_TASK_CODES'], max_daily_hours, include_block_billed, faker)
            invoice_rows = _ensure_mandatory_lines(invoice_rows, timekeeper_data, invoice_description, client_id, law_firm_id, current_start_date, current_end_date, selected_mandatory_items)
            df = pd.DataFrame(invoice_rows)
            df = df.sort_values(by="LINE_ITEM_DATE", ascending=True)
            df['LINE_ITEM_TOTAL'] = df['LINE_ITEM_TOTAL'].apply(lambda x: f"{x:.2f}")

            status.write(f"Generating LEDES and PDF for invoice {invoice_number}...")
            
            ledes_content = _create_ledes_1998b_content(df.to_dict(orient='records'), total_amount, current_start_date, current_end_date, invoice_number, matter_number)
            pdf_buffer = _create_pdf_invoice(df, total_amount, invoice_number, datetime.date.today(), current_start_date, current_end_date, client_id, law_firm_id, logo_bytes, include_logo=bool(uploaded_logo))

            attachments_to_send = []
            
            ledes_filename = f"invoice_{invoice_number}.txt"
            pdf_filename = f"invoice_{invoice_number}.pdf"
            
            attachments_to_send.append((ledes_filename, ledes_content.encode('utf-8')))
            attachments_to_send.append((pdf_filename, pdf_buffer.getvalue()))
            
            if st.session_state.send_email:
                status.write(f"Sending email for invoice {invoice_number}...")
                success, error_message = _send_email_with_attachments(to_email, email_subject, email_body, attachments_to_send, smtp_user, smtp_host, smtp_port, smtp_user, smtp_pass)
                if success:
                    status.success(f"Successfully sent invoice {invoice_number} to {to_email}!")
                else:
                    status.error(f"Failed to send email for invoice {invoice_number}: {error_message}")
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
    
if __name__ == "__main__":
    main()
