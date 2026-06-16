from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from export_workbook import export_workbook
from seed_customers import seed_customers
from work_system import DATA_DIR, SCHEMAS, UPDATE_FILE, WORKBOOK_FILE, ensure_layout, write_csv


CLEAR_CSVS = [
    "raw_updates.csv",
    "ledger_transactions.csv",
    "jobs.csv",
    "tasks.csv",
    "outstanding_jobs.csv",
    "calendar_queue.csv",
    "receipts.csv",
    "duplicate_audit.csv",
    "github_sync_log.csv",
    "processed_github_inbox.csv",
]


def archive_current_state() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = DATA_DIR / "archive" / timestamp
    archive_dir.mkdir(parents=True, exist_ok=False)
    for filename in SCHEMAS:
        source = DATA_DIR / filename
        if source.exists():
            shutil.copy2(source, archive_dir / filename)
    if WORKBOOK_FILE.exists():
        shutil.copy2(WORKBOOK_FILE, archive_dir / WORKBOOK_FILE.name)
    if UPDATE_FILE.exists():
        imports_archive = archive_dir / "imports"
        imports_archive.mkdir(parents=True, exist_ok=True)
        shutil.copy2(UPDATE_FILE, imports_archive / UPDATE_FILE.name)
    return archive_dir


def reset_for_live() -> Path:
    ensure_layout()
    archive_dir = archive_current_state()
    seed_customers()
    for filename in CLEAR_CSVS:
        write_csv(filename, [], SCHEMAS[filename])
    UPDATE_FILE.write_text("", encoding="utf-8")
    export_workbook()
    return archive_dir


if __name__ == "__main__":
    archive = reset_for_live()
    print(f"Archived previous test/live data to {archive}")
    print("Reset complete. Customer seed defaults were preserved.")
