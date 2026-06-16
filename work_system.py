from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
IMPORTS_DIR = DATA_DIR / "imports"
EXPORTS_DIR = ROOT / "exports"
DOCS_DIR = ROOT / "docs"
RECEIPTS_DIR = ROOT / "receipts"
GITHUB_INBOX_DIR = ROOT / "github_inbox"
GITHUB_INBOX_FILE = GITHUB_INBOX_DIR / "chatgpt_updates.jsonl"
UPDATE_FILE = IMPORTS_DIR / "chatgpt_updates.jsonl"
WORKBOOK_FILE = EXPORTS_DIR / "Chris_Work_System.xlsx"

SCHEMAS: dict[str, list[str]] = {
    "raw_updates.csv": [
        "raw_update_id", "update_id", "created_at", "imported_at", "source",
        "raw_text", "parsed_summary", "update_type", "customer", "job_name",
        "work_date", "approval_status", "validation_status",
        "validation_errors", "notes",
    ],
    "ledger_transactions.csv": [
        "transaction_id", "raw_update_id", "transaction_date", "customer_id",
        "customer_name", "job_id", "job_name", "transaction_type",
        "description", "quantity", "rate", "amount", "reimbursable", "paid",
        "payment_method", "status", "linked_transaction_id", "notes",
    ],
    "customers.csv": [
        "customer_id", "customer_name", "default_rate", "default_payment_route",
        "default_location", "active", "notes",
    ],
    "jobs.csv": [
        "job_id", "customer_id", "customer_name", "job_name", "status",
        "opened_date", "closed_date", "default_rate", "location", "notes",
    ],
    "tasks.csv": [
        "task_id", "raw_update_id", "customer_id", "customer_name", "job_id",
        "job_name", "task", "due_date", "priority", "status", "created_at",
        "completed_at", "notes",
    ],
    "calendar_queue.csv": [
        "calendar_queue_id", "raw_update_id", "customer_id", "customer_name",
        "job_id", "job_name", "title", "date", "start_time", "end_time",
        "timezone", "location", "description", "status", "google_calendar_id",
        "google_calendar_event_id", "created_at", "notes",
    ],
    "receipts.csv": [
        "receipt_id", "raw_update_id", "transaction_id", "customer_id",
        "customer_name", "job_id", "job_name", "receipt_date", "vendor",
        "amount", "file_path", "reimbursable", "reimbursed", "notes",
    ],
    "duplicate_audit.csv": [
        "duplicate_id", "detected_at", "update_id", "raw_text", "customer",
        "job_name", "work_date", "update_type", "reason", "action_taken",
        "notes",
    ],
    "github_sync_log.csv": [
        "sync_id", "synced_at", "update_id", "source", "action", "notes",
    ],
}

SEED_CUSTOMERS = [
    ("Larry", "35"),
    ("Funkel", "40"),
    ("Suzanne", "40"),
    ("Collins", "40"),
    ("Nate", "40"),
    ("Leanne", ""),
    ("Jackie", ""),
    ("Luanne", ""),
]

CUSTOMER_ALIASES = {
    "funkels": "Funkel",
    "funkel's": "Funkel",
    "fungle": "Funkel",
    "funko": "Funkel",
}

SUPPORTED_UPDATE_TYPES = {
    "job_update", "expense", "payment", "task", "schedule", "correction",
    "general_note",
}

SIDE_WORK_CALENDAR_ID = (
    "a44000a85c7a65c96e5e9ea61e2fe8b1c75ee8302041f90f6273a8376b235071"
    "@group.calendar.google.com"
)


def ensure_layout() -> None:
    for directory in (
        DATA_DIR,
        IMPORTS_DIR,
        EXPORTS_DIR,
        DOCS_DIR,
        RECEIPTS_DIR,
        GITHUB_INBOX_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for filename, headers in SCHEMAS.items():
        path = DATA_DIR / filename
        if not path.exists():
            write_csv(path, [], headers)
    UPDATE_FILE.touch(exist_ok=True)
    GITHUB_INBOX_FILE.touch(exist_ok=True)


def read_csv(path_or_name: str | Path) -> list[dict[str, str]]:
    path = Path(path_or_name)
    if not path.is_absolute():
        path = DATA_DIR / path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path_or_name: str | Path,
    rows: Iterable[dict[str, Any]],
    headers: list[str] | None = None,
) -> None:
    path = Path(path_or_name)
    if not path.is_absolute():
        path = DATA_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    if headers is None:
        headers = SCHEMAS[path.name]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: clean_cell(row.get(header, "")) for header in headers})


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value)


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    joined = "|".join(clean_cell(part).strip().lower() for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return result or "unknown"


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_customer(
    value: Any, customers: list[dict[str, str]]
) -> tuple[str, str, str]:
    raw = clean_cell(value).strip()
    if not raw:
        return "", "", "missing customer"
    lower = raw.lower()
    if lower in CUSTOMER_ALIASES:
        raw = CUSTOMER_ALIASES[lower]
        lower = raw.lower()
    by_lower = {row["customer_name"].lower(): row for row in customers}
    if lower in by_lower:
        row = by_lower[lower]
        return row["customer_name"], row["customer_id"], ""
    matches = get_close_matches(lower, list(by_lower), n=1, cutoff=0.72)
    if matches:
        return raw, "", f"unknown customer close to existing customer: {by_lower[matches[0]]['customer_name']}"
    return raw, "", "unknown customer"


def deterministic_update_id(packet: dict[str, Any]) -> str:
    existing = clean_cell(packet.get("update_id")).strip()
    if existing:
        return existing
    return stable_id(
        "update",
        packet.get("created_at"),
        packet.get("customer"),
        packet.get("update_type"),
        packet.get("work_date"),
        packet.get("raw_text"),
        length=20,
    )


def parse_jsonl(path: Path = UPDATE_FILE) -> list[tuple[int, dict[str, Any], str]]:
    parsed: list[tuple[int, dict[str, Any], str]] = []
    if not path.exists():
        return parsed
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("JSON value is not an object")
            parsed.append((line_number, value, ""))
        except (json.JSONDecodeError, ValueError) as exc:
            parsed.append((line_number, {"raw_text": line}, f"invalid JSON on line {line_number}: {exc}"))
    return parsed


def packet_validation_errors(
    packet: dict[str, Any],
    customers: list[dict[str, str]],
    customer_error: str = "",
) -> list[str]:
    errors: list[str] = []
    update_type = clean_cell(packet.get("update_type")).strip()
    if update_type not in SUPPORTED_UPDATE_TYPES:
        errors.append(f"unsupported update_type: {update_type or '(blank)'}")
    if update_type != "general_note" and not clean_cell(packet.get("customer")).strip():
        errors.append("missing customer")
    if customer_error:
        errors.append(customer_error)
    if update_type == "job_update" and not clean_cell(packet.get("work_date")).strip():
        errors.append("missing work_date on job update")
    hours = parse_number(packet.get("hours"))
    if hours is not None and parse_number(packet.get("hourly_rate")) is None:
        errors.append("hours present but hourly_rate missing")
    expense = parse_number(packet.get("expense_amount"))
    if expense is not None and expense != 0 and parse_bool(packet.get("reimbursable")) is None:
        errors.append("expense present but reimbursable/reimbursed unclear")
    payment = parse_number(packet.get("payment_amount"))
    if payment is not None and payment != 0 and not clean_cell(packet.get("work_date")).strip():
        errors.append("payment present without date")
    if parse_bool(packet.get("calendar_needed")) is True:
        required = {
            "calendar_title": packet.get("calendar_title"),
            "calendar_date": packet.get("calendar_date"),
            "calendar_start_time": packet.get("calendar_start_time"),
            "calendar_end_time": packet.get("calendar_end_time"),
        }
        missing = [key for key, value in required.items() if not clean_cell(value).strip()]
        if missing:
            errors.append("calendar_needed true but missing " + ", ".join(missing))
    combined = " ".join(clean_cell(value) for value in packet.values()).lower()
    if "meet.google.com" in combined:
        errors.append("Google Meet link accidentally created")
    return unique(errors)


def likely_duplicate(
    packet: dict[str, Any],
    raw_rows: list[dict[str, str]],
    ledger_rows: list[dict[str, str]],
    canonical_customer: str,
) -> bool:
    hours = parse_number(packet.get("hours"))
    work_date = clean_cell(packet.get("work_date")).strip()
    raw_text = clean_cell(packet.get("raw_text") or packet.get("work_completed_notes")).strip().lower()
    if hours is None or not work_date or not canonical_customer or not raw_text:
        return False
    labor_by_raw = {
        row["raw_update_id"]: row
        for row in ledger_rows
        if row.get("transaction_type") == "labor_charge"
    }
    for row in raw_rows:
        if row.get("customer") != canonical_customer or row.get("work_date") != work_date:
            continue
        labor = labor_by_raw.get(row.get("raw_update_id", ""))
        if not labor or parse_number(labor.get("quantity")) != hours:
            continue
        old_text = (row.get("raw_text") or row.get("parsed_summary") or "").lower()
        if SequenceMatcher(None, raw_text, old_text).ratio() >= 0.72:
            return True
    return False


def unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def is_future_or_today(value: str) -> bool:
    try:
        return date.fromisoformat(value) >= date.today()
    except ValueError:
        return False
