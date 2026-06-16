from __future__ import annotations

from collections import Counter

from work_system import (
    DATA_DIR,
    deterministic_update_id,
    ensure_layout,
    normalize_customer,
    packet_validation_errors,
    parse_jsonl,
    parse_number,
    read_csv,
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
BACKLOG_PRIORITIES = {"high", "medium-high", "medium", "low-medium", "low", ""}


def run_validation() -> int:
    ensure_layout()
    raw_rows = read_csv("raw_updates.csv")
    customers = read_csv("customers.csv")
    ledger = read_csv("ledger_transactions.csv")
    calendar = read_csv("calendar_queue.csv")
    tasks = read_csv("tasks.csv")
    backlog = read_csv("outstanding_jobs.csv")
    packets = {
        deterministic_update_id(packet): packet
        for _, packet, parse_error in parse_jsonl()
        if not parse_error
    }
    update_counts = Counter(row.get("update_id", "") for row in raw_rows)
    transactions_by_raw: dict[str, list[dict[str, str]]] = {}
    for transaction in ledger:
        transactions_by_raw.setdefault(transaction.get("raw_update_id", ""), []).append(transaction)

    flagged = 0
    for raw in raw_rows:
        existing = [
            item.strip()
            for item in raw.get("validation_errors", "").split(";")
            if item.strip() and (
                "likely duplicate" in item
                or "invalid JSON" in item
                or "unsupported update_type" in item
            )
        ]
        packet = packets.get(raw.get("update_id", ""), {})
        _, _, customer_error = normalize_customer(raw.get("customer"), customers)
        if raw.get("update_type") in {"general_note", "lead", "follow_up", "backlog", "backlog_update"} and customer_error == "missing customer":
            customer_error = ""
        errors = existing + packet_validation_errors(packet or raw, customers, customer_error)

        if update_counts[raw.get("update_id", "")] > 1:
            errors.append("duplicate update_id")

        for transaction in transactions_by_raw.get(raw.get("raw_update_id", ""), []):
            amount = parse_number(transaction.get("amount"))
            quantity = parse_number(transaction.get("quantity"))
            rate = parse_number(transaction.get("rate"))
            transaction_type = transaction.get("transaction_type")
            if transaction_type == "labor_charge" and None not in (amount, quantity, rate):
                if round(quantity * rate, 2) != round(amount, 2):
                    errors.append("labor amount mismatch")
            if transaction_type in {"labor_charge", "material_expense"} and amount is not None and amount < 0:
                errors.append(f"invalid negative amount for {transaction_type}")
            if transaction_type == "payment_received":
                if amount is not None and amount > 0:
                    errors.append("invalid positive amount for payment_received")
                if not transaction.get("transaction_date"):
                    errors.append("payment present without date")

        errors = unique(errors)
        raw["validation_errors"] = "; ".join(errors)
        if errors:
            raw["validation_status"] = "rejected" if any("invalid JSON" in item for item in errors) else "needs_review"
            flagged += 1
        else:
            raw["validation_status"] = "valid"

    meet_rows = []
    for row in calendar:
        combined = " ".join(row.values()).lower()
        if "meet.google.com" in combined:
            meet_rows.append(row.get("raw_update_id", ""))
    if meet_rows:
        for raw in raw_rows:
            if raw.get("raw_update_id") in meet_rows:
                errors = unique([
                    *[item.strip() for item in raw.get("validation_errors", "").split(";") if item.strip()],
                    "Google Meet link accidentally created",
                ])
                raw["validation_errors"] = "; ".join(errors)
                raw["validation_status"] = "needs_review"

    open_task_keys = [
        (row.get("customer_id"), row.get("job_id"), row.get("task", "").strip().lower())
        for row in tasks
        if row.get("status") in {"open", "scheduled"}
    ]
    duplicate_open_tasks = sum(count - 1 for count in Counter(open_task_keys).values() if count > 1)

    backlog_errors: list[str] = []
    active_backlog_keys = []
    for row in backlog:
        label = row.get("backlog_id") or row.get("task_description") or "(unknown backlog row)"
        status = row.get("status", "").strip().lower()
        priority = row.get("priority", "").strip().lower()
        if not row.get("task_description", "").strip():
            backlog_errors.append(f"{label}: missing task_description")
        if status not in BACKLOG_STATUSES:
            backlog_errors.append(f"{label}: invalid status '{row.get('status', '')}'")
        if priority not in BACKLOG_PRIORITIES:
            backlog_errors.append(f"{label}: invalid priority '{row.get('priority', '')}'")
        if status not in {"scheduled", "completed", "cancelled"}:
            active_backlog_keys.append((
                row.get("customer_id") or row.get("customer_name", "").strip().lower(),
                row.get("job_id") or row.get("job_name", "").strip().lower(),
                row.get("task_description", "").strip().lower(),
            ))
    duplicate_active_backlog = sum(
        count - 1 for count in Counter(active_backlog_keys).values() if count > 1
    )

    write_csv(DATA_DIR / "raw_updates.csv", raw_rows)
    print(f"Validation scanned {len(raw_rows)} raw updates and {len(ledger)} transactions.")
    print(f"Flagged raw updates: {flagged}; duplicate open tasks: {duplicate_open_tasks}.")
    print(
        f"Backlog rows: {len(backlog)}; backlog errors: {len(backlog_errors)}; "
        f"duplicate active backlog rows: {duplicate_active_backlog}."
    )
    for error in backlog_errors:
        print(f"Backlog validation error: {error}")
    return flagged + len(backlog_errors) + duplicate_active_backlog


if __name__ == "__main__":
    raise SystemExit(1 if run_validation() else 0)
