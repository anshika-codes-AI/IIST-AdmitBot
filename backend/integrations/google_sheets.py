"""
Google Sheets integration for IIST AdmitBot lead capture.
Each student conversation creates/updates a lead row in the IIST Leads sheet.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

from backend.config import settings

logger = logging.getLogger(__name__)

# Required Google API scopes
_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Column headers — must match the Google Sheet exactly
LEAD_COLUMNS = [
    "Lead ID",
    "Timestamp",
    "Student Name",
    "Phone Number",
    "City",
    "State",
    "Course Interest",
    "Query Category",
    "JEE / 12th Score",
    "Source Channel",
    "Lead Score",
    "Bot Resolved",
    "Escalated",
    "Response Time (ms)",
    "Assigned To",
    "Lead Status",
    "Notes",
    "Last Updated",
    "Conversation Count",
    "Last Intent Score",
    "Conversation History",
]

INTERACTION_COLUMNS = [
    "Interaction ID",
    "Lead ID",
    "Timestamp",
    "Source Channel",
    "Student Name",
    "Phone Number",
    "Student Message",
    "Bot Reply",
    "Query Category",
    "Intent Score",
    "Lead Score",
    "Needs Escalation",
    "Bot Resolved",
    "Language",
    "Response Time (ms)",
]


def _get_credentials() -> Credentials:
    """Load Google service account credentials from file or environment variable."""
    if settings.google_service_account_json:
        service_account_info = json.loads(settings.google_service_account_json)
        return Credentials.from_service_account_info(service_account_info, scopes=_SCOPES)

    if os.path.exists(settings.google_service_account_file):
        return Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=_SCOPES
        )

    raise RuntimeError(
        "Google service account credentials not found. "
        "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE."
    )


def _get_or_create_worksheet(title: str, headers: list[str]) -> gspread.Worksheet:
    """Open a worksheet by title, creating it with headers if needed."""
    creds = _get_credentials()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.google_sheets_id)
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        # Auto-create the sheet with headers on first run.
        worksheet = spreadsheet.add_worksheet(
            title=title,
            rows=2000,
            cols=max(len(headers), 20),
        )
        worksheet.append_row(headers)
        logger.info("Created new '%s' worksheet with headers", title)
    return worksheet


def _get_leads_sheet() -> gspread.Worksheet:
    return _get_or_create_worksheet(settings.google_sheets_leads_tab, LEAD_COLUMNS)


def _get_interactions_sheet() -> gspread.Worksheet:
    return _get_or_create_worksheet(
        settings.google_sheets_interactions_tab,
        INTERACTION_COLUMNS,
    )


def append_lead(
    lead_id: str,
    phone_number: str,
    student_name: str = "",
    city: str = "",
    state: str = "",
    course_interest: str = "",
    query_category: str = "other",
    jee_score: str = "",
    source_channel: str = "WhatsApp",
    lead_score: str = "Cold",
    bot_resolved: str = "Yes",
    escalated: str = "No",
    response_time_ms: int = 0,
    last_intent_score: str = "Cold",
    conversation_count: int = 1,
    conversation_history: str = "",
) -> bool:
    """
    Append a new lead row to Google Sheets.
    Performs duplicate detection — if phone already exists, updates the row instead.

    Returns True on success, False on failure.
    """
    if not settings.google_sheets_id:
        logger.warning("GOOGLE_SHEETS_ID not configured — skipping lead capture")
        return False

    try:
        sheet = _get_leads_sheet()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Duplicate detection: search for existing phone number
        existing_row = find_lead_by_phone(phone_number, sheet)

        row_data = [
            lead_id,                # Lead ID
            now,                    # Timestamp
            student_name,           # Student Name
            phone_number,           # Phone Number
            city,                   # City
            state,                  # State
            course_interest,        # Course Interest
            query_category,         # Query Category
            jee_score,              # JEE / 12th Score
            source_channel,         # Source Channel
            lead_score,             # Lead Score
            bot_resolved,           # Bot Resolved
            escalated,              # Escalated
            response_time_ms,       # Response Time (ms)
            "",                     # Assigned To (counsellor fills this)
            "New",                  # Lead Status
            "",                     # Notes
            now,                    # Last Updated
            conversation_count,     # Conversation Count
            last_intent_score,      # Last Intent Score
            conversation_history,   # Conversation History
        ]

        if existing_row:
            # Preserve manual fields (Assigned To, Lead Status, Notes) entered by counsellors
            existing_values = sheet.row_values(existing_row)
            row_data[14] = existing_values[14] if len(existing_values) > 14 else ""   # Assigned To
            row_data[15] = existing_values[15] if len(existing_values) > 15 else "New"  # Lead Status
            row_data[16] = existing_values[16] if len(existing_values) > 16 else ""   # Notes
            logger.info("Updating existing lead for phone: %s (row %d)", phone_number, existing_row)
            sheet.update(
                f"A{existing_row}:U{existing_row}",
                [row_data],
                value_input_option="USER_ENTERED",
            )
        else:
            sheet.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info("New lead captured for phone: %s", phone_number)

        return True

    except Exception as exc:
        logger.error("Failed to write lead to Google Sheets: %s", exc)
        return False


def find_lead_by_phone(phone_number: str, sheet: Optional[gspread.Worksheet] = None) -> Optional[int]:
    """
    Find a lead's row index by phone number.
    Returns 1-based row number, or None if not found.
    """
    try:
        if sheet is None:
            sheet = _get_leads_sheet()
        phone_col_index = LEAD_COLUMNS.index("Phone Number") + 1
        cell = sheet.find(phone_number, in_column=phone_col_index)
        return cell.row if cell else None
    except Exception as exc:
        logger.warning("Duplicate check failed: %s", exc)
        return None


def get_daily_summary() -> Dict[str, Any]:
    """
    Retrieve today's lead summary for the HOD daily report.
    Returns counts of total, hot, warm, cold, and enrolled leads.
    """
    summary: Dict[str, Any] = {
        "total": 0,
        "hot": 0,
        "warm": 0,
        "cold": 0,
        "enrolled": 0,
        "sources": {},
    }
    if not settings.google_sheets_id:
        return summary

    try:
        sheet = _get_leads_sheet()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        records = sheet.get_all_records()

        for record in records:
            ts = str(record.get("Timestamp", ""))
            if not ts.startswith(today):
                continue
            summary["total"] += 1
            score = str(record.get("Lead Score", "")).capitalize()
            if score == "Hot":
                summary["hot"] += 1
            elif score == "Warm":
                summary["warm"] += 1
            elif score == "Cold":
                summary["cold"] += 1

            status = str(record.get("Lead Status", ""))
            if status.lower() == "enrolled":
                summary["enrolled"] += 1

            source = str(record.get("Source Channel", "Other"))
            summary["sources"][source] = summary["sources"].get(source, 0) + 1

    except Exception as exc:
        logger.error("Failed to fetch daily summary: %s", exc)

    return summary


def append_interaction(
    interaction_id: str,
    lead_id: str,
    source_channel: str,
    student_name: str,
    phone_number: str,
    student_message: str,
    bot_reply: str,
    query_category: str,
    intent_score: str,
    lead_score: str,
    needs_escalation: bool,
    bot_resolved: bool,
    language: str,
    response_time_ms: int,
) -> bool:
    """Append one chatbot interaction event for analytics and QA monitoring."""
    if not settings.google_sheets_id:
        logger.warning("GOOGLE_SHEETS_ID not configured — skipping interaction capture")
        return False

    try:
        sheet = _get_interactions_sheet()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row_data = [
            interaction_id,
            lead_id,
            now,
            source_channel,
            student_name,
            phone_number,
            student_message,
            bot_reply,
            query_category,
            intent_score,
            lead_score,
            "Yes" if needs_escalation else "No",
            "Yes" if bot_resolved else "No",
            language,
            response_time_ms,
        ]
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
        return True
    except Exception as exc:
        logger.error("Failed to write interaction to Google Sheets: %s", exc)
        return False
