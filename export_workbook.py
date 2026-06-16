from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from work_system import (
    DATA_DIR,
    ROOT,
    SCHEMAS,
    WORKBOOK_FILE,
    ensure_layout,
    parse_number,
    read_csv,
)


SHEET_FILES = [
    ("Raw Updates", "raw_updates.csv"),
    ("Duplicate Audit", "duplicate_audit.csv"),
    ("GitHub Sync Log", "github_sync_log.csv"),
    ("Ledger Transactions", "ledger_transactions.csv"),
    ("Customers", "customers.csv"),
    ("Jobs", "jobs.csv"),
    ("Tasks", "tasks.csv"),
    ("Calendar Queue", "calendar_queue.csv"),
    ("Receipts", "receipts.csv"),
]

NUMERIC_FIELDS = {
    "default_rate", "quantity", "rate", "amount",
}


def typed_value(header: str, value: str) -> Any:
    if header in NUMERIC_FIELDS and value != "":
        number = parse_number(value)
        return number if number is not None else value
    if header.endswith("_at") and value:
        return value[:16].replace("T", " ")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def dashboard_snapshot() -> dict[str, Any]:
    ledger = read_csv("ledger_transactions.csv")
    raw = read_csv("raw_updates.csv")
    tasks = read_csv("tasks.csv")
    calendar = read_csv("calendar_queue.csv")
    posted = [row for row in ledger if row.get("status") != "void"]

    total_owed = sum(parse_number(row.get("amount")) or 0 for row in posted)
    owed_by_customer: dict[str, float] = defaultdict(float)
    owed_by_job: dict[str, float] = defaultdict(float)
    hours_by_customer: dict[str, float] = defaultdict(float)
    for row in posted:
        amount = parse_number(row.get("amount")) or 0
        owed_by_customer[row.get("customer_name") or "(Unknown)"] += amount
        job_label = f"{row.get('customer_name') or '(Unknown)'} - {row.get('job_name') or 'General work'}"
        owed_by_job[job_label] += amount
        if row.get("transaction_type") == "labor_charge":
            hours_by_customer[row.get("customer_name") or "(Unknown)"] += (
                parse_number(row.get("quantity")) or 0
            )

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    hours_this_week = 0.0
    for row in posted:
        if row.get("transaction_type") != "labor_charge":
            continue
        try:
            transaction_date = date.fromisoformat(row.get("transaction_date", ""))
        except ValueError:
            continue
        if week_start <= transaction_date <= today:
            hours_this_week += parse_number(row.get("quantity")) or 0

    adjustments_by_link: dict[str, float] = defaultdict(float)
    for row in posted:
        if row.get("transaction_type") == "adjustment" and row.get("linked_transaction_id"):
            adjustments_by_link[row["linked_transaction_id"]] += parse_number(row.get("amount")) or 0
    unreimbursed_expenses = 0.0
    for row in posted:
        if row.get("transaction_type") != "material_expense" or row.get("paid") == "true":
            continue
        expense_net = (parse_number(row.get("amount")) or 0) + adjustments_by_link[row["transaction_id"]]
        unreimbursed_expenses += max(0, expense_net)

    payments_received = abs(sum(
        parse_number(row.get("amount")) or 0
        for row in posted
        if row.get("transaction_type") == "payment_received"
    ))
    open_tasks = [
        row for row in tasks if row.get("status") in {"open", "scheduled"}
    ]
    upcoming = []
    for row in calendar:
        if row.get("status") not in {"queued", "created_by_chatgpt"}:
            continue
        try:
            if date.fromisoformat(row.get("date", "")) >= today:
                upcoming.append(row)
        except ValueError:
            continue
    reviews = [row for row in raw if row.get("validation_status") == "needs_review"]
    validation_errors = [
        row for row in raw if row.get("validation_errors", "").strip()
    ]

    return {
        "as_of": today.isoformat(),
        "kpis": [
            ["Total money owed", round(total_owed, 2), "currency"],
            ["Hours worked this week", round(hours_this_week, 2), "number"],
            ["Expenses/materials not reimbursed", round(unreimbursed_expenses, 2), "currency"],
            ["Payments received", round(payments_received, 2), "currency"],
            ["Open tasks", len(open_tasks), "integer"],
            ["Upcoming scheduled jobs", len(upcoming), "integer"],
            ["Raw updates needing review", len(reviews), "integer"],
            ["Validation errors", len(validation_errors), "integer"],
        ],
        "owed_by_customer": [
            [name, round(amount, 2)]
            for name, amount in sorted(owed_by_customer.items(), key=lambda item: (-item[1], item[0]))
        ],
        "owed_by_job": [
            [name, round(amount, 2)]
            for name, amount in sorted(owed_by_job.items(), key=lambda item: (-item[1], item[0]))
        ],
        "hours_by_customer": [
            [name, round(hours, 2)]
            for name, hours in sorted(hours_by_customer.items(), key=lambda item: (-item[1], item[0]))
        ],
        "open_tasks": [
            [row.get("customer_name"), row.get("job_name"), row.get("task"), row.get("due_date"), row.get("status")]
            for row in open_tasks
        ],
        "upcoming": [
            [
                row.get("date"), row.get("start_time"), row.get("end_time"),
                row.get("customer_name"), row.get("title"), row.get("location"), row.get("status"),
            ]
            for row in upcoming
        ],
        "review_rows": [
            [row.get("update_id"), row.get("customer"), row.get("update_type"), row.get("validation_errors")]
            for row in reviews
        ],
    }


def build_snapshot() -> dict[str, Any]:
    sheets = []
    for sheet_name, filename in SHEET_FILES:
        headers = SCHEMAS[filename]
        rows = read_csv(filename)
        sheets.append({
            "name": sheet_name,
            "headers": headers,
            "rows": [
                [typed_value(header, row.get(header, "")) for header in headers]
                for row in rows
            ],
        })
    return {"dashboard": dashboard_snapshot(), "sheets": sheets}


def find_node_runtime() -> tuple[Path, Path]:
    dependency_root = (
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime"
        / "dependencies" / "node"
    )
    node = dependency_root / "bin" / "node.exe"
    modules = dependency_root / "node_modules"
    artifact = modules / "@oai" / "artifact-tool"
    if node.exists() and artifact.exists():
        return node, modules
    raise RuntimeError(
        "The bundled Codex Node runtime with @oai/artifact-tool was not found. "
        "Run this export from Codex Desktop or configure the bundled workspace dependencies."
    )


def export_workbook(preview_dir: Path | None = None) -> Path:
    ensure_layout()
    node, modules = find_node_runtime()
    snapshot = build_snapshot()
    with tempfile.TemporaryDirectory(prefix="chris-work-system-") as temp_name:
        snapshot_file = Path(temp_name) / "snapshot.json"
        snapshot_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        command = [
            str(node),
            str(ROOT / "workbook_export.cjs"),
            str(snapshot_file),
            str(WORKBOOK_FILE),
        ]
        if preview_dir:
            preview_dir.mkdir(parents=True, exist_ok=True)
            command.append(str(preview_dir))
        environment = os.environ.copy()
        environment["NODE_PATH"] = str(modules)
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                "Workbook export failed.\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        if result.stdout.strip():
            print(result.stdout.strip())
    return WORKBOOK_FILE


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Chris Work System workbook.")
    parser.add_argument(
        "--preview-dir",
        type=Path,
        help="Optional directory for rendered workbook sheet previews.",
    )
    args = parser.parse_args()
    path = export_workbook(args.preview_dir)
    print(f"Workbook exported to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
