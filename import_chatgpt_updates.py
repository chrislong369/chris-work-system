from __future__ import annotations

from datetime import date
from typing import Any

from export_daily_summary import export_daily_summary
from export_workbook import export_workbook
from seed_customers import seed_customers
from validate_data import run_validation
from work_system import (
    SIDE_WORK_CALENDAR_ID,
    clean_cell,
    deterministic_update_id,
    ensure_layout,
    is_future_or_today,
    iso_now,
    likely_duplicate,
    normalize_customer,
    packet_validation_errors,
    parse_bool,
    parse_jsonl,
    parse_number,
    read_csv,
    stable_id,
    unique,
    write_csv,
)

BACKLOG_STATUSES = {
    "lead",
    "needs follow-up",
    "needs scheduling",
    "scheduled",
    "in progress",
    "blocked",
    "completed",
    "cancelled",
}

BACKLOG_PRIORITY_DEFAULT = "medium"
BACKLOG_TRIGGER_PHRASES = (
    "i still need to",
    "still need to",
    "remind me",
    "i have to reach out",
    "have to reach out",
    "not scheduled yet",
    "potential job",
    "ken mentioned",
    "needs to get done",
)
BACKLOG_DONE_STATUSES = {"scheduled", "completed", "cancelled"}
BACKLOG_ACTIONS = {
    "mark_completed",
    "mark_scheduled",
    "mark_cancelled",
    "park_until_date",
    "change_priority",
    "add_follow_up_note",
}


def get_or_create_job(
    packet: dict[str, Any],
    jobs: list[dict[str, str]],
    customer_id: str,
    customer_name: str,
    default_rate: str,
) -> dict[str, str]:
    job_name = clean_cell(packet.get("job_name")).strip() or "General work"
    job_id = stable_id("job", customer_id, job_name)
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    opened_date = (
        clean_cell(packet.get("work_date")).strip()
        or clean_cell(packet.get("calendar_date")).strip()
        or date.today().isoformat()
    )
    job = {
        "job_id": job_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "job_name": job_name,
        "status": "open",
        "opened_date": opened_date,
        "closed_date": "",
        "default_rate": default_rate,
        "location": clean_cell(packet.get("calendar_location")).strip(),
        "notes": "",
    }
    jobs.append(job)
    return job


def packet_text(packet: dict[str, Any]) -> str:
    return " ".join(
        clean_cell(packet.get(key)).strip()
        for key in (
            "raw_text",
            "work_completed_notes",
            "remaining_task",
            "task",
            "task_description",
            "backlog_task",
            "next_action",
            "notes",
        )
        if clean_cell(packet.get(key)).strip()
    )


def first_packet_value(packet: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean_cell(packet.get(key)).strip()
        if value:
            return value
    return ""


def normalize_backlog_action(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "complete": "mark_completed",
        "completed": "mark_completed",
        "done": "mark_completed",
        "scheduled": "mark_scheduled",
        "schedule": "mark_scheduled",
        "cancel": "mark_cancelled",
        "cancelled": "mark_cancelled",
        "canceled": "mark_cancelled",
        "declined": "mark_cancelled",
        "park": "park_until_date",
        "parked": "park_until_date",
        "park_until": "park_until_date",
        "change_priority": "change_priority",
        "priority": "change_priority",
        "note": "add_follow_up_note",
        "add_note": "add_follow_up_note",
        "follow_up_note": "add_follow_up_note",
    }
    return aliases.get(normalized, normalized)


def normalize_backlog_status(value: str, combined_text: str, update_type: str) -> str:
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    aliases = {
        "follow up": "needs follow-up",
        "needs followup": "needs follow-up",
        "needs follow up": "needs follow-up",
        "needs schedule": "needs scheduling",
        "unscheduled": "needs scheduling",
        "schedule": "needs scheduling",
        "done": "completed",
        "complete": "completed",
        "canceled": "cancelled",
        "declined": "cancelled",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in BACKLOG_STATUSES:
        return normalized
    if update_type == "lead" or "potential job" in combined_text or "ken mentioned" in combined_text:
        return "lead"
    if "reach out" in combined_text or "follow up" in combined_text:
        return "needs follow-up"
    if "not scheduled yet" in combined_text or "schedule" in combined_text:
        return "needs scheduling"
    return "needs scheduling"


def normalize_backlog_priority(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "normal": "medium",
        "med": "medium",
        "mediumhigh": "medium-high",
        "medium-high": "medium-high",
        "medium-low": "medium",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"high", "medium-high", "medium", "low-medium", "low"}:
        return normalized
    return BACKLOG_PRIORITY_DEFAULT


def backlog_task_from_packet(packet: dict[str, Any], task_text: str) -> str:
    return first_packet_value(
        packet,
        "backlog_task",
        "task_description",
        "remaining_task",
        "task",
    ) or task_text


def backlog_action_from_packet(packet: dict[str, Any]) -> str:
    return normalize_backlog_action(
        first_packet_value(packet, "backlog_action", "action", "backlog_update_action")
    )


def should_track_backlog(packet: dict[str, Any], update_type: str, task_text: str) -> bool:
    if backlog_action_from_packet(packet) in BACKLOG_ACTIONS:
        return True
    if first_packet_value(packet, "backlog_task", "task_description", "next_action"):
        return True
    if task_text:
        return True
    if update_type in {"task", "lead", "follow_up", "backlog", "backlog_update"}:
        return True
    combined = packet_text(packet).lower()
    return any(phrase in combined for phrase in BACKLOG_TRIGGER_PHRASES)


def infer_next_action(packet: dict[str, Any], status: str, combined_text: str) -> str:
    explicit = first_packet_value(packet, "next_action", "backlog_next_action")
    if explicit:
        return explicit
    if status == "lead":
        return "Confirm customer, scope, contact info, and preferred timing."
    if status == "needs follow-up" or "reach out" in combined_text:
        return "Reach out and confirm next step."
    if status == "needs scheduling":
        return "Pick a date or confirm timing, then schedule it."
    if status == "blocked":
        return "Resolve blocker or decide whether to park/cancel."
    return ""


def backlog_due_target(packet: dict[str, Any]) -> str:
    return first_packet_value(packet, "due_target", "due_date", "follow_up_date")


def backlog_preferred_timing(packet: dict[str, Any]) -> str:
    return first_packet_value(packet, "preferred_timing", "scheduled_date", "calendar_date")


def backlog_mentioned_at(packet: dict[str, Any], raw_row: dict[str, str]) -> str:
    return (
        clean_cell(packet.get("created_at")).strip()
        or raw_row.get("work_date", "")
        or clean_cell(packet.get("calendar_date")).strip()
        or iso_now()
    )


def append_note(existing: str, addition: str) -> str:
    existing = existing.strip()
    addition = addition.strip()
    if not addition:
        return existing
    if not existing:
        return addition
    if addition.lower() in existing.lower():
        return existing
    return f"{existing} | {addition}"


def matching_backlog_row(
    backlog: list[dict[str, str]],
    backlog_id: str,
    source_update_id: str,
    customer_id: str,
    customer_name: str,
    job_id: str,
    job_name: str,
    task_description: str,
) -> dict[str, str] | None:
    task_key = task_description.strip().lower()
    for row in backlog:
        if row.get("backlog_id") == backlog_id:
            return row
    if source_update_id:
        for row in backlog:
            if row.get("source_update_id") == source_update_id:
                return row
    for row in backlog:
        if row.get("status") in BACKLOG_DONE_STATUSES:
            continue
        same_customer = (
            row.get("customer_id") == customer_id
            if customer_id
            else row.get("customer_name", "").strip().lower() == customer_name.strip().lower()
        )
        same_job = (
            row.get("job_id") == job_id
            if job_id
            else row.get("job_name", "").strip().lower() == job_name.strip().lower()
        )
        same_task = row.get("task_description", "").strip().lower() == task_key
        if same_customer and same_job and same_task:
            return row
    return None


def upsert_backlog_item(
    backlog: list[dict[str, str]],
    packet: dict[str, Any],
    raw_row: dict[str, str],
    customer_id: str,
    customer_name: str,
    job_id: str,
    job_name: str,
    task_description: str,
) -> None:
    task_description = task_description.strip() or packet_text(packet).strip()
    if not task_description:
        return

    combined_text = packet_text(packet).lower()
    status = normalize_backlog_status(
        first_packet_value(packet, "backlog_status", "status"),
        combined_text,
        raw_row.get("update_type", ""),
    )
    priority = normalize_backlog_priority(
        first_packet_value(packet, "backlog_priority", "priority")
    )
    next_action = infer_next_action(packet, status, combined_text)
    due_target = backlog_due_target(packet)
    preferred_timing = backlog_preferred_timing(packet)
    last_mentioned = backlog_mentioned_at(packet, raw_row)
    now = iso_now()
    note = first_packet_value(packet, "backlog_notes", "notes", "raw_text")
    parked_until = first_packet_value(packet, "parked_until", "follow_up_date")
    scheduled_date = first_packet_value(packet, "scheduled_date", "calendar_date")
    completed_date = first_packet_value(packet, "completed_date")
    source_update_id = first_packet_value(packet, "source_update_id", "update_id")
    backlog_id = stable_id("backlog", customer_name, job_name, task_description)

    row = matching_backlog_row(
        backlog, backlog_id, source_update_id, customer_id, customer_name, job_id, job_name, task_description
    )
    if row is None:
        backlog.append({
            "backlog_id": backlog_id,
            "raw_update_id": raw_row.get("raw_update_id", ""),
            "source_update_id": source_update_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "job_id": job_id,
            "job_name": job_name,
            "task_description": task_description,
            "status": status,
            "priority": priority,
            "next_action": next_action,
            "due_target": due_target,
            "preferred_timing": preferred_timing,
            "last_mentioned_at": last_mentioned,
            "last_updated_at": now,
            "parked_until": parked_until,
            "scheduled_date": scheduled_date if status == "scheduled" else "",
            "scheduled_calendar_queue_id": "",
            "completed_date": completed_date if status == "completed" else "",
            "notes": note,
        })
        return

    row["raw_update_id"] = raw_row.get("raw_update_id", row.get("raw_update_id", ""))
    row["source_update_id"] = source_update_id or row.get("source_update_id", "")
    row["customer_id"] = customer_id or row.get("customer_id", "")
    row["customer_name"] = customer_name or row.get("customer_name", "")
    row["job_id"] = job_id or row.get("job_id", "")
    row["job_name"] = job_name or row.get("job_name", "")
    row["task_description"] = task_description or row.get("task_description", "")
    row["status"] = status or row.get("status", "")
    row["priority"] = priority or row.get("priority", "")
    row["next_action"] = next_action or row.get("next_action", "")
    row["due_target"] = due_target or row.get("due_target", "")
    row["preferred_timing"] = preferred_timing or row.get("preferred_timing", "")
    row["last_mentioned_at"] = last_mentioned
    row["last_updated_at"] = now
    row["parked_until"] = parked_until or row.get("parked_until", "")
    row["scheduled_date"] = scheduled_date or row.get("scheduled_date", "")
    row["completed_date"] = completed_date or row.get("completed_date", "")
    row["notes"] = append_note(row.get("notes", ""), note)


def find_or_create_backlog_for_action(
    backlog: list[dict[str, str]],
    packet: dict[str, Any],
    raw_row: dict[str, str],
    customer_id: str,
    customer_name: str,
    job_id: str,
    job_name: str,
    task_description: str,
) -> dict[str, str] | None:
    source_update_id = first_packet_value(packet, "source_update_id", "update_id")
    explicit_id = first_packet_value(packet, "backlog_id")
    backlog_id = explicit_id or stable_id("backlog", customer_name, job_name, task_description)
    row = matching_backlog_row(
        backlog,
        backlog_id,
        source_update_id,
        customer_id,
        customer_name,
        job_id,
        job_name,
        task_description,
    )
    if row is not None:
        return row
    if not task_description:
        return None
    upsert_backlog_item(
        backlog,
        packet,
        raw_row,
        customer_id,
        customer_name,
        job_id,
        job_name,
        task_description,
    )
    return matching_backlog_row(
        backlog,
        backlog_id,
        source_update_id,
        customer_id,
        customer_name,
        job_id,
        job_name,
        task_description,
    )


def apply_backlog_action(
    backlog: list[dict[str, str]],
    packet: dict[str, Any],
    raw_row: dict[str, str],
    customer_id: str,
    customer_name: str,
    job_id: str,
    job_name: str,
    task_description: str,
) -> bool:
    action = backlog_action_from_packet(packet)
    if action not in BACKLOG_ACTIONS:
        return False

    row = find_or_create_backlog_for_action(
        backlog,
        packet,
        raw_row,
        customer_id,
        customer_name,
        job_id,
        job_name,
        task_description,
    )
    if row is None:
        return False

    now = iso_now()
    note = first_packet_value(packet, "backlog_notes", "notes", "raw_text")
    row["raw_update_id"] = raw_row.get("raw_update_id", row.get("raw_update_id", ""))
    row["source_update_id"] = first_packet_value(packet, "source_update_id", "update_id") or row.get("source_update_id", "")
    row["customer_id"] = customer_id or row.get("customer_id", "")
    row["customer_name"] = customer_name or row.get("customer_name", "")
    row["job_id"] = job_id or row.get("job_id", "")
    row["job_name"] = job_name or row.get("job_name", "")
    row["task_description"] = task_description or row.get("task_description", "")
    row["last_mentioned_at"] = backlog_mentioned_at(packet, raw_row)
    row["last_updated_at"] = now

    if action == "mark_completed":
        row["status"] = "completed"
        row["completed_date"] = (
            first_packet_value(packet, "completed_date", "work_date")
            or date.today().isoformat()
        )
        row["next_action"] = ""
    elif action == "mark_scheduled":
        scheduled_date = first_packet_value(packet, "scheduled_date", "calendar_date")
        row["status"] = "scheduled"
        row["scheduled_date"] = scheduled_date
        row["preferred_timing"] = scheduled_date or row.get("preferred_timing", "")
        row["scheduled_calendar_queue_id"] = first_packet_value(
            packet, "calendar_queue_id", "calendar_event_id"
        ) or row.get("scheduled_calendar_queue_id", "")
        row["next_action"] = ""
    elif action == "mark_cancelled":
        row["status"] = "cancelled"
        row["next_action"] = ""
    elif action == "park_until_date":
        row["parked_until"] = first_packet_value(packet, "parked_until", "follow_up_date")
        row["status"] = first_packet_value(packet, "backlog_status", "status") or row.get("status") or "needs follow-up"
        row["next_action"] = first_packet_value(packet, "next_action", "backlog_next_action") or row.get("next_action", "")
    elif action == "change_priority":
        row["priority"] = normalize_backlog_priority(
            first_packet_value(packet, "backlog_priority", "priority")
        )
        row["next_action"] = first_packet_value(packet, "next_action", "backlog_next_action") or row.get("next_action", "")
    elif action == "add_follow_up_note":
        row["next_action"] = first_packet_value(packet, "next_action", "backlog_next_action") or row.get("next_action", "")
        if first_packet_value(packet, "backlog_status", "status"):
            row["status"] = normalize_backlog_status(
                first_packet_value(packet, "backlog_status", "status"),
                packet_text(packet).lower(),
                raw_row.get("update_type", ""),
            )

    row["due_target"] = backlog_due_target(packet) or row.get("due_target", "")
    row["preferred_timing"] = backlog_preferred_timing(packet) or row.get("preferred_timing", "")
    row["notes"] = append_note(row.get("notes", ""), note)
    return True


def mark_backlog_scheduled(
    backlog: list[dict[str, str]],
    customer_id: str,
    customer_name: str,
    job_id: str,
    job_name: str,
    queue_id: str,
    calendar_date: str,
) -> None:
    now = iso_now()
    for row in backlog:
        if row.get("status") in BACKLOG_DONE_STATUSES:
            continue
        same_customer = (
            row.get("customer_id") == customer_id
            if customer_id
            else row.get("customer_name", "").strip().lower() == customer_name.strip().lower()
        )
        same_job = (
            row.get("job_id") == job_id
            if job_id
            else row.get("job_name", "").strip().lower() == job_name.strip().lower()
        )
        if not same_customer or not same_job:
            continue
        row["status"] = "scheduled"
        row["scheduled_calendar_queue_id"] = queue_id
        row["scheduled_date"] = calendar_date or row.get("scheduled_date", "")
        row["preferred_timing"] = calendar_date or row.get("preferred_timing", "")
        row["last_updated_at"] = now
        row["notes"] = append_note(row.get("notes", ""), "Scheduled through calendar queue.")


def import_updates() -> tuple[int, int, int]:
    ensure_layout()
    seed_customers()
    customers = read_csv("customers.csv")
    jobs = read_csv("jobs.csv")
    raw_rows = read_csv("raw_updates.csv")
    ledger = read_csv("ledger_transactions.csv")
    tasks = read_csv("tasks.csv")
    backlog = read_csv("outstanding_jobs.csv")
    calendar = read_csv("calendar_queue.csv")
    receipts = read_csv("receipts.csv")
    duplicate_audit = read_csv("duplicate_audit.csv")

    customer_by_id = {row["customer_id"]: row for row in customers}
    existing_update_ids = {row["update_id"] for row in raw_rows}
    existing_transaction_ids = {row["transaction_id"] for row in ledger}
    existing_task_ids = {row["task_id"] for row in tasks}
    existing_calendar_ids = {row["calendar_queue_id"] for row in calendar}
    existing_receipt_ids = {row["receipt_id"] for row in receipts}

    imported = skipped = review_count = duplicate_audits_created = 0
    for line_number, packet, parse_error in parse_jsonl():
        update_id = deterministic_update_id(packet)
        if update_id in existing_update_ids:
            detected_at = iso_now()
            duplicate_audit.append({
                "duplicate_id": stable_id(
                    "dup", detected_at, update_id, line_number, len(duplicate_audit)
                ),
                "detected_at": detected_at,
                "update_id": update_id,
                "raw_text": clean_cell(packet.get("raw_text")).strip(),
                "customer": clean_cell(packet.get("customer") or packet.get("customer_name")).strip(),
                "job_name": clean_cell(packet.get("job_name")).strip(),
                "work_date": clean_cell(packet.get("work_date")).strip(),
                "update_type": clean_cell(packet.get("update_type")).strip(),
                "reason": "duplicate update_id already imported",
                "action_taken": "skipped; no ledger, task, calendar, or receipt records created",
                "notes": f"Detected from chatgpt_updates.jsonl line {line_number}.",
            })
            duplicate_audits_created += 1
            skipped += 1
            continue

        update_type = clean_cell(packet.get("update_type")).strip()
        customer_value = packet.get("customer") or packet.get("customer_name")
        canonical_customer, customer_id, customer_error = normalize_customer(
            customer_value, customers
        )
        if update_type in {"general_note", "lead", "follow_up", "backlog", "backlog_update"} and customer_error == "missing customer":
            customer_error = ""
        errors = [parse_error] if parse_error else []
        errors.extend(packet_validation_errors(packet, customers, customer_error))
        if customer_id and likely_duplicate(packet, raw_rows, ledger, canonical_customer):
            errors.append("likely duplicate work log")
        errors = unique(errors)

        raw_update_id = stable_id("raw", update_id)
        summary_parts = [
            update_type or "unknown update",
            canonical_customer,
            clean_cell(packet.get("job_name")).strip(),
            clean_cell(packet.get("work_completed_notes")).strip(),
        ]
        raw_row = {
            "raw_update_id": raw_update_id,
            "update_id": update_id,
            "created_at": clean_cell(packet.get("created_at")).strip(),
            "imported_at": iso_now(),
            "source": clean_cell(packet.get("source")).strip() or "ChatGPT",
            "raw_text": clean_cell(packet.get("raw_text")).strip(),
            "parsed_summary": " | ".join(part for part in summary_parts if part),
            "update_type": update_type,
            "customer": canonical_customer,
            "job_name": clean_cell(packet.get("job_name")).strip() or (
                "General work" if customer_id else ""
            ),
            "work_date": clean_cell(packet.get("work_date")).strip(),
            "approval_status": clean_cell(packet.get("approval_status")).strip() or "pending",
            "validation_status": "needs_review" if errors else "valid",
            "validation_errors": "; ".join(errors),
            "notes": clean_cell(packet.get("notes")).strip(),
        }
        raw_rows.append(raw_row)
        existing_update_ids.add(update_id)
        imported += 1
        if errors:
            review_count += 1

        approved = raw_row["approval_status"] == "approved"
        duplicate = "likely duplicate work log" in errors
        task_text = (
            clean_cell(packet.get("remaining_task")).strip()
            or (clean_cell(packet.get("task")).strip() if update_type == "task" else "")
        )
        job: dict[str, str] | None = None
        job_id = ""
        job_name = raw_row["job_name"]
        if approved and not duplicate and not parse_error and should_track_backlog(packet, update_type, task_text):
            if customer_id:
                customer_row = customer_by_id[customer_id]
                job = get_or_create_job(
                    packet, jobs, customer_id, canonical_customer, customer_row["default_rate"]
                )
                job_id = job["job_id"]
                job_name = job["job_name"]
            backlog_task = backlog_task_from_packet(packet, task_text) or raw_row["raw_text"]
            if not apply_backlog_action(
                backlog,
                packet,
                raw_row,
                customer_id,
                canonical_customer,
                job_id,
                job_name,
                backlog_task,
            ):
                upsert_backlog_item(
                    backlog,
                    packet,
                    raw_row,
                    customer_id,
                    canonical_customer,
                    job_id,
                    job_name,
                    backlog_task,
                )

        if not approved or not customer_id or duplicate or parse_error:
            if duplicate:
                detected_at = iso_now()
                duplicate_audit.append({
                    "duplicate_id": stable_id(
                        "dup", detected_at, update_id, "likely_duplicate", len(duplicate_audit)
                    ),
                    "detected_at": detected_at,
                    "update_id": update_id,
                    "raw_text": raw_row["raw_text"],
                    "customer": canonical_customer,
                    "job_name": raw_row["job_name"],
                    "work_date": raw_row["work_date"],
                    "update_type": update_type,
                    "reason": "likely duplicate work log",
                    "action_taken": "raw update saved as needs_review; no ledger, task, calendar, or receipt records created",
                    "notes": "Matched existing customer, work date, hours, and similar text.",
                })
                duplicate_audits_created += 1
            continue

        customer_row = customer_by_id[customer_id]
        if job is None:
            job = get_or_create_job(
                packet, jobs, customer_id, canonical_customer, customer_row["default_rate"]
            )
        job_id = job["job_id"]
        job_name = job["job_name"]
        transaction_date = (
            clean_cell(packet.get("work_date")).strip()
            or clean_cell(packet.get("calendar_date")).strip()
        )
        notes = clean_cell(packet.get("notes")).strip()

        hours = parse_number(packet.get("hours"))
        rate = parse_number(packet.get("hourly_rate"))
        if rate is None:
            rate = parse_number(customer_row.get("default_rate"))
        if hours is not None and rate is not None and hours != 0:
            transaction_id = stable_id("txn", raw_update_id, "labor_charge")
            if transaction_id not in existing_transaction_ids:
                ledger.append({
                    "transaction_id": transaction_id,
                    "raw_update_id": raw_update_id,
                    "transaction_date": transaction_date,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "transaction_type": "labor_charge",
                    "description": clean_cell(packet.get("work_completed_notes")).strip() or "Labor",
                    "quantity": hours,
                    "rate": rate,
                    "amount": round(hours * rate, 2),
                    "reimbursable": "",
                    "paid": "false",
                    "payment_method": "",
                    "status": "posted",
                    "linked_transaction_id": "",
                    "notes": notes,
                })
                existing_transaction_ids.add(transaction_id)

        expense = parse_number(packet.get("expense_amount"))
        if expense is not None and expense != 0:
            transaction_id = stable_id("txn", raw_update_id, "material_expense")
            if transaction_id not in existing_transaction_ids:
                reimbursable = parse_bool(packet.get("reimbursable"))
                ledger.append({
                    "transaction_id": transaction_id,
                    "raw_update_id": raw_update_id,
                    "transaction_date": transaction_date,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "transaction_type": "material_expense",
                    "description": clean_cell(packet.get("expense_description")).strip() or "Materials",
                    "quantity": "1",
                    "rate": abs(expense),
                    "amount": abs(expense),
                    "reimbursable": reimbursable,
                    "paid": "false",
                    "payment_method": "",
                    "status": "posted",
                    "linked_transaction_id": "",
                    "notes": notes,
                })
                existing_transaction_ids.add(transaction_id)
            receipt_id = stable_id("receipt", raw_update_id, transaction_id)
            if receipt_id not in existing_receipt_ids:
                receipts.append({
                    "receipt_id": receipt_id,
                    "raw_update_id": raw_update_id,
                    "transaction_id": transaction_id,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "receipt_date": transaction_date,
                    "vendor": clean_cell(packet.get("vendor")).strip(),
                    "amount": abs(expense),
                    "file_path": clean_cell(packet.get("receipt_file_path")).strip(),
                    "reimbursable": parse_bool(packet.get("reimbursable")),
                    "reimbursed": parse_bool(packet.get("reimbursed")) or False,
                    "notes": clean_cell(packet.get("expense_description")).strip(),
                })
                existing_receipt_ids.add(receipt_id)

        payment = parse_number(packet.get("payment_amount"))
        if payment is not None and payment != 0:
            transaction_id = stable_id("txn", raw_update_id, "payment_received")
            if transaction_id not in existing_transaction_ids:
                ledger.append({
                    "transaction_id": transaction_id,
                    "raw_update_id": raw_update_id,
                    "transaction_date": transaction_date,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "transaction_type": "payment_received",
                    "description": "Payment received",
                    "quantity": "",
                    "rate": "",
                    "amount": -abs(payment),
                    "reimbursable": "",
                    "paid": "true",
                    "payment_method": clean_cell(packet.get("payment_method")).strip(),
                    "status": "posted",
                    "linked_transaction_id": "",
                    "notes": notes,
                })
                existing_transaction_ids.add(transaction_id)

        if update_type == "correction":
            adjustment = parse_number(packet.get("adjustment_amount"))
            if adjustment is not None and adjustment != 0:
                linked = clean_cell(packet.get("linked_transaction_id")).strip()
                reason = clean_cell(packet.get("correction_reason")).strip()
                if not linked and "reimburs" in reason.lower():
                    matches = [
                        row for row in ledger
                        if row.get("customer_id") == customer_id
                        and row.get("job_id") == job_id
                        and row.get("transaction_type") == "material_expense"
                    ]
                    if matches:
                        linked = matches[-1]["transaction_id"]
                transaction_id = stable_id("txn", raw_update_id, "adjustment")
                if transaction_id not in existing_transaction_ids:
                    ledger.append({
                        "transaction_id": transaction_id,
                        "raw_update_id": raw_update_id,
                        "transaction_date": transaction_date,
                        "customer_id": customer_id,
                        "customer_name": canonical_customer,
                        "job_id": job_id,
                        "job_name": job_name,
                        "transaction_type": "adjustment",
                        "description": reason or "Correction adjustment",
                        "quantity": "",
                        "rate": "",
                        "amount": adjustment,
                        "reimbursable": "",
                        "paid": "",
                        "payment_method": "",
                        "status": "posted",
                        "linked_transaction_id": linked,
                        "notes": clean_cell(packet.get("raw_text")).strip(),
                    })
                    existing_transaction_ids.add(transaction_id)

        if task_text:
            task_id = stable_id("task", customer_id, job_id, task_text)
            duplicate_open = any(
                row.get("customer_id") == customer_id
                and row.get("job_id") == job_id
                and row.get("task", "").strip().lower() == task_text.lower()
                and row.get("status") in {"open", "scheduled"}
                for row in tasks
            )
            if task_id not in existing_task_ids and not duplicate_open:
                tasks.append({
                    "task_id": task_id,
                    "raw_update_id": raw_update_id,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "task": task_text,
                    "due_date": clean_cell(packet.get("due_date")).strip(),
                    "priority": clean_cell(packet.get("priority")).strip() or "normal",
                    "status": "open",
                    "created_at": clean_cell(packet.get("created_at")).strip() or iso_now(),
                    "completed_at": "",
                    "notes": notes,
                })
                existing_task_ids.add(task_id)

        calendar_needed = parse_bool(packet.get("calendar_needed")) is True
        calendar_date = clean_cell(packet.get("calendar_date")).strip()
        calendar_complete = all(clean_cell(packet.get(key)).strip() for key in (
            "calendar_title", "calendar_date", "calendar_start_time", "calendar_end_time"
        ))
        if (
            update_type == "schedule"
            and calendar_needed
            and calendar_complete
            and is_future_or_today(calendar_date)
        ):
            queue_id = stable_id("cal", raw_update_id, calendar_date, packet.get("calendar_start_time"))
            if queue_id not in existing_calendar_ids:
                event_id = clean_cell(packet.get("calendar_event_id")).strip()
                calendar.append({
                    "calendar_queue_id": queue_id,
                    "raw_update_id": raw_update_id,
                    "customer_id": customer_id,
                    "customer_name": canonical_customer,
                    "job_id": job_id,
                    "job_name": job_name,
                    "title": clean_cell(packet.get("calendar_title")).strip(),
                    "date": calendar_date,
                    "start_time": clean_cell(packet.get("calendar_start_time")).strip(),
                    "end_time": clean_cell(packet.get("calendar_end_time")).strip(),
                    "timezone": "America/New_York",
                    "location": clean_cell(packet.get("calendar_location")).strip(),
                    "description": clean_cell(packet.get("calendar_description")).strip(),
                    "status": "created_by_chatgpt" if event_id else "queued",
                    "google_calendar_id": SIDE_WORK_CALENDAR_ID,
                    "google_calendar_event_id": event_id,
                    "created_at": clean_cell(packet.get("created_at")).strip() or iso_now(),
                    "notes": "No Google Meet link.",
                })
                existing_calendar_ids.add(queue_id)
                mark_backlog_scheduled(
                    backlog,
                    customer_id,
                    canonical_customer,
                    job_id,
                    job_name,
                    queue_id,
                    calendar_date,
                )

    write_csv("raw_updates.csv", raw_rows)
    write_csv("jobs.csv", jobs)
    write_csv("ledger_transactions.csv", ledger)
    write_csv("tasks.csv", tasks)
    write_csv("outstanding_jobs.csv", backlog)
    write_csv("calendar_queue.csv", calendar)
    write_csv("receipts.csv", receipts)
    write_csv("duplicate_audit.csv", duplicate_audit)
    return imported, skipped, review_count, duplicate_audits_created


def main() -> int:
    imported, skipped, reviews, duplicate_audits_created = import_updates()
    validation_errors = run_validation()
    export_workbook()
    export_daily_summary()
    print(
        f"Import complete: {imported} imported, {skipped} duplicate update_id rows skipped, "
        f"{reviews} initially needing review."
    )
    print(f"Duplicate audit rows written: {duplicate_audits_created}.")
    print(f"Validation complete: {validation_errors} flagged raw updates.")
    print("Workbook refreshed: exports/Chris_Work_System.xlsx")
    print("Daily summary refreshed: exports/daily_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
