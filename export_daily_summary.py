from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from work_system import EXPORTS_DIR, ensure_layout, parse_number, read_csv


SUMMARY_FILE = EXPORTS_DIR / "daily_summary.md"
ACTIVE_CALENDAR_STATUSES = {"queued", "created_by_chatgpt"}
INACTIVE_BACKLOG_STATUSES = {"scheduled", "completed", "cancelled"}


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def money(value: float) -> str:
    return f"${value:,.2f}"


def customer_job(row: dict[str, str]) -> str:
    parts = [row.get("customer_name", "").strip(), row.get("job_name", "").strip()]
    label = " - ".join(part for part in parts if part)
    return label or "(Unknown)"


def bullet_rows(rows: Iterable[str]) -> list[str]:
    rendered = [f"- {row}" for row in rows]
    return rendered or ["- None"]


def future_calendar_keys(calendar: list[dict[str, str]], today: date) -> set[tuple[str, str, str, str]]:
    keys = set()
    for row in calendar:
        if row.get("status") not in ACTIVE_CALENDAR_STATUSES:
            continue
        scheduled_date = parse_iso_date(row.get("date", ""))
        if scheduled_date is None or scheduled_date < today:
            continue
        keys.add((
            row.get("customer_id", ""),
            row.get("job_id", ""),
            row.get("customer_name", "").strip().lower(),
            row.get("job_name", "").strip().lower(),
        ))
    return keys


def matching_future_calendar(row: dict[str, str], keys: set[tuple[str, str, str, str]]) -> bool:
    key = (
        row.get("customer_id", ""),
        row.get("job_id", ""),
        row.get("customer_name", "").strip().lower(),
        row.get("job_name", "").strip().lower(),
    )
    return key in keys or bool(row.get("scheduled_calendar_queue_id", "").strip())


def parked_until_future(row: dict[str, str], today: date) -> bool:
    parked_until = parse_iso_date(row.get("parked_until", ""))
    return parked_until is not None and parked_until > today


def backlog_priority_sort(row: dict[str, str]) -> tuple[int, str, str]:
    priority_order = {"high": 0, "medium-high": 1, "medium": 2, "low-medium": 3, "low": 4}
    return (
        priority_order.get(row.get("priority", "").strip().lower(), 5),
        row.get("customer_name", ""),
        row.get("job_name", ""),
    )


def active_unscheduled_backlog(
    backlog: list[dict[str, str]],
    calendar: list[dict[str, str]],
    today: date,
) -> list[dict[str, str]]:
    keys = future_calendar_keys(calendar, today)
    return sorted(
        [
            row for row in backlog
            if row.get("status", "").strip().lower() not in INACTIVE_BACKLOG_STATUSES
            and not parked_until_future(row, today)
            and not matching_future_calendar(row, keys)
        ],
        key=backlog_priority_sort,
    )


def scheduled_rows(
    calendar: list[dict[str, str]],
    today: date,
    today_only: bool,
) -> list[dict[str, str]]:
    rows = []
    for row in calendar:
        if row.get("status") not in ACTIVE_CALENDAR_STATUSES:
            continue
        scheduled_date = parse_iso_date(row.get("date", ""))
        if scheduled_date is None:
            continue
        if today_only and scheduled_date == today:
            rows.append(row)
        elif not today_only and scheduled_date > today:
            rows.append(row)
    return sorted(rows, key=lambda item: (item.get("date", ""), item.get("start_time", "")))


def money_totals(
    ledger: list[dict[str, str]],
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    by_customer: dict[str, float] = defaultdict(float)
    by_job: dict[str, float] = defaultdict(float)
    for row in ledger:
        if row.get("status") == "void":
            continue
        amount = parse_number(row.get("amount")) or 0
        by_customer[row.get("customer_name") or "(Unknown)"] += amount
        by_job[customer_job(row)] += amount
    customer_rows = sorted(by_customer.items(), key=lambda item: (-item[1], item[0]))
    job_rows = sorted(by_job.items(), key=lambda item: (-item[1], item[0]))
    return customer_rows, job_rows


def recent_updates(raw_rows: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    return sorted(
        raw_rows,
        key=lambda row: row.get("imported_at") or row.get("created_at") or "",
        reverse=True,
    )[:limit]


def sync_warnings(sync_log: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    rows = [
        row for row in sync_log
        if "error" in row.get("action", "").lower()
        or "warning" in row.get("action", "").lower()
    ]
    return sorted(rows, key=lambda row: row.get("synced_at", ""), reverse=True)[:limit]


def export_daily_summary(path: Path = SUMMARY_FILE) -> Path:
    ensure_layout()
    today = date.today()
    ledger = read_csv("ledger_transactions.csv")
    raw = read_csv("raw_updates.csv")
    backlog = read_csv("outstanding_jobs.csv")
    calendar = read_csv("calendar_queue.csv")
    sync_log = read_csv("github_sync_log.csv")

    today_jobs = scheduled_rows(calendar, today, today_only=True)
    upcoming_jobs = scheduled_rows(calendar, today, today_only=False)
    outstanding = active_unscheduled_backlog(backlog, calendar, today)
    follow_ups = [
        row for row in outstanding
        if row.get("status", "").strip().lower() == "needs follow-up"
    ]
    parked_due = sorted(
        [
            row for row in backlog
            if row.get("status", "").strip().lower() not in INACTIVE_BACKLOG_STATUSES
            and (parse_iso_date(row.get("parked_until", "")) or date.max) <= today
        ],
        key=backlog_priority_sort,
    )
    owed_by_customer, owed_by_job = money_totals(ledger)
    warnings = sync_warnings(sync_log)

    lines = [
        f"# Chris Work System Daily Summary - {today.isoformat()}",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## Today's Scheduled Jobs",
        *bullet_rows(
            f"{row.get('start_time') or '?'}-{row.get('end_time') or '?'} {customer_job(row)}"
            for row in today_jobs
        ),
        "",
        "## Upcoming Scheduled Jobs",
        *bullet_rows(
            f"{row.get('date')} {row.get('start_time') or '?'} {customer_job(row)}"
            for row in upcoming_jobs[:15]
        ),
        "",
        "## Outstanding / Unscheduled Jobs",
        *bullet_rows(
            f"[{row.get('priority') or 'medium'}] {customer_job(row)}: "
            f"{row.get('task_description')} | next: {row.get('next_action') or 'decide next action'}"
            for row in outstanding
        ),
        "",
        "## Jobs Needing Follow-Up",
        *bullet_rows(
            f"{customer_job(row)}: {row.get('next_action') or row.get('task_description')}"
            for row in follow_ups
        ),
        "",
        "## Parked Jobs Due Or Overdue",
        *bullet_rows(
            f"{row.get('parked_until')} {customer_job(row)}: {row.get('task_description')}"
            for row in parked_due
        ),
        "",
        "## Money Owed By Customer",
        *bullet_rows(f"{name}: {money(amount)}" for name, amount in owed_by_customer if round(amount, 2) != 0),
        "",
        "## Money Owed By Job",
        *bullet_rows(f"{name}: {money(amount)}" for name, amount in owed_by_job if round(amount, 2) != 0),
        "",
        "## Recent Imported Updates",
        *bullet_rows(
            f"{row.get('imported_at') or row.get('created_at')} "
            f"{row.get('update_id')} {row.get('customer')} {row.get('update_type')}"
            for row in recent_updates(raw)
        ),
        "",
        "## Sync Warnings / Errors",
        *bullet_rows(
            f"{row.get('synced_at')} {row.get('action')}: {row.get('notes')}"
            for row in warnings
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(export_daily_summary())
