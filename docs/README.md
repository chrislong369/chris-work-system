# Chris Work System

This Phase 1 system turns ChatGPT JSON update packets into a local CSV ledger and a refreshed Excel workbook. CSV files in `data/` are the source of truth. The workbook is an export, not the place to edit source data.

## Daily Use

Fast daily path:

1. Ask ChatGPT for a job update JSON.
2. Double-click `daily_update.bat`.
3. Paste the JSON.
4. Press Enter.
5. Open the workbook if needed.

The helper validates that the pasted text is valid JSON before appending it to `data/imports/chatgpt_updates.jsonl`. If the JSON is invalid, nothing is appended. If the import or workbook export fails, the helper prints the error.

Manual path:

1. Paste one complete JSON object per line into `data/imports/chatgpt_updates.jsonl`.
2. From the project root, run:

   ```powershell
   python import_chatgpt_updates.py
   ```

3. Review `exports/Chris_Work_System.xlsx`.

The main importer seeds missing starter customers, imports new packets, validates data, and refreshes the workbook.

## Before Live Use

1. Run QA.
2. Fix any missing folders.
3. Run:

   ```powershell
   python reset_for_live.py
   ```

4. Confirm the Dashboard shows `$0` total money owed.
5. Begin entering real ChatGPT updates in `data/imports/chatgpt_updates.jsonl`.

## Important Paths

- Future ChatGPT packets: `data/imports/chatgpt_updates.jsonl`
- CSV source of truth: `data/`
- Outstanding/unscheduled backlog: `data/outstanding_jobs.csv`
- Processed GitHub inbox tracker: `data/processed_github_inbox.csv`
- Receipt files/future receipt photos: `receipts/`
- Excel export: `exports/Chris_Work_System.xlsx`
- Daily Markdown summary: `exports/daily_summary.md`
- Packet examples: `docs/UPDATE_FORMAT.md`

## Dashboard Totals

- Total money owed is the sum of posted ledger transaction amounts.
- Labor and material charges are positive.
- Payments and credits are negative.
- Money owed by customer and job is calculated from the same ledger transactions.
- Hours come from `labor_charge` quantities.
- Unreimbursed materials are material expenses net of linked correction adjustments.
- Corrections remain visible as `adjustment` transactions.
- Outstanding / Unscheduled Jobs lists active leads, follow-ups, and unscheduled work that is not completed, cancelled, scheduled, or parked until a future follow-up date.

## Outstanding / Unscheduled Jobs

Use `data/outstanding_jobs.csv` for work that has been mentioned but is not completed and not scheduled. This includes loose leads, customer follow-ups, remaining work, and jobs that need a date picked.

Backlog rows stay visible on the Dashboard until one of these happens:

- Status changes to `completed`.
- Status changes to `scheduled`, or a matching future row exists in `data/calendar_queue.csv`.
- Status changes to `cancelled`.
- `parked_until` is set to a future follow-up date.

The importer automatically creates or updates backlog rows from approved packets when it sees explicit backlog fields, `remaining_task`, task packets, lead/follow-up packets, or natural-language phrases such as `I still need to`, `remind me`, `I have to reach out`, `not scheduled yet`, `potential job`, `Ken mentioned`, or `needs to get done`.

For state changes, prefer structured `backlog_action` packets instead of relying on wording. Supported actions are `mark_completed`, `mark_scheduled`, `mark_cancelled`, `park_until_date`, `change_priority`, and `add_follow_up_note`.

Supported backlog statuses are `lead`, `needs follow-up`, `needs scheduling`, `scheduled`, `in progress`, `blocked`, `completed`, and `cancelled`.

## Duplicate Protection

- An existing `update_id` is skipped.
- A missing `update_id` receives a deterministic ID derived from the packet.
- Similar work logs with the same customer, date, and hours are saved to Raw Updates as `needs_review` and are not double-counted.
- Skipped duplicate imports are recorded in `data/duplicate_audit.csv` and exported on the `Duplicate Audit` workbook tab.

## Fixing Mistakes

Do not delete or rewrite old ledger transactions. Add an approved `correction` packet with an `adjustment_amount`. Positive adjustments increase the amount owed; negative adjustments reduce it. Run the importer again.

## Customers and Default Rates

Run `python seed_customers.py` to add any missing starter customers. To add a new customer, add a row to `data/customers.csv` with a unique `customer_id`, name, default rate if known, active status, and notes.

The importer normalizes confident Funfgeld voice variants. Unknown or close customer names are flagged for review instead of guessed.

## Backfilling Old Jobs

Add approved historical packets to `data/imports/chatgpt_updates.jsonl`, one JSON object per line. Use the actual historical `work_date` and a unique `update_id`, then run the main importer.

## Calendar Queue

Only future scheduled work with `calendar_needed: true` enters `data/calendar_queue.csv`. Completed work logs do not create calendar items. If a packet includes `calendar_event_id`, its queue status is `created_by_chatgpt`; otherwise it is `queued`.

The queue tracks the side-work Google Calendar ID. It does not create events, send email, or add Google Meet links.

## Other Commands

```powershell
python add_chatgpt_update.py
python validate_data.py
python export_workbook.py
python export_daily_summary.py
python rebuild_dashboard.py
```

`rebuild_dashboard.py` refreshes the Dashboard tab by rebuilding the workbook export. It does not build or launch a browser UI.

## Windows Double-Click Helpers

- `daily_update.bat` runs `python add_chatgpt_update.py`.
- `run_import.bat` runs `python import_chatgpt_updates.py`.
- `open_workbook.bat` opens `exports/Chris_Work_System.xlsx`.
- `backup_project.bat` creates a timestamped zip in `backups/` containing scripts, docs, data CSV files, and the exported workbook.
- `sync_and_import.bat` runs `python sync_github_inbox.py`.

Daily-use scripts do not run `reset_for_live.py`.

## GitHub Inbox Workflow

This is the lower-friction workflow when the project is connected to a private GitHub repo:

1. Tell ChatGPT the job update.
2. ChatGPT writes one JSON object per line to `github_inbox/chatgpt_updates.jsonl` in the private GitHub repo.
3. On this computer, double-click `sync_and_import.bat`.
4. The script pulls the repo when Git is configured, reads `github_inbox/chatgpt_updates.jsonl`, appends new unprocessed inbox items into `data/imports/chatgpt_updates.jsonl`, and records processed inbox hashes in `data/processed_github_inbox.csv`.
5. The normal importer runs and refreshes `exports/Chris_Work_System.xlsx`.

Safety rules:

- Use a private GitHub repo if `github_inbox/chatgpt_updates.jsonl` contains real customer, job, schedule, receipt, or money data.
- Never use a public repo for real customer/job/money updates.
- If the inbox is empty, the sync script does nothing.
- Each inbox line is tracked by a stable hash in `data/processed_github_inbox.csv`, so old inbox lines are not repeatedly logged every 15 minutes.
- Duplicate `update_id` values are marked processed once and are not repeatedly appended to `data/github_sync_log.csv`.
- Scheduled auto-sync skips safely when tracked local Git changes exist, logs a `warning_dirty_repo` row, and avoids `git pull`/import until the tracked changes are resolved.
- If GitHub pull/fetch fails, the script prints a clear error.
- The sync script does not run `reset_for_live.py` and does not delete local data.

If this folder is not a Git repo yet, `sync_github_inbox.py` reads the local `github_inbox/chatgpt_updates.jsonl` file but cannot pull from GitHub until a private remote is configured.

## Public GitHub Safety

If this project is pushed to a public GitHub repo, the public repo should contain only code, docs, helper scripts, and safe templates. Live local data stays on this PC.

Public-safe content:

- Python scripts, batch files, docs, and `.gitignore`.
- `templates/` CSV and JSONL templates.
- `github_inbox/chatgpt_updates.jsonl` only when it is empty or contains sanitized public-safe packets.

Local-only private content:

- Live CSV data under `data/*.csv`.
- `data/private_customer_map.csv`.
- `data/imports/*.jsonl`.
- `data/processed_github_inbox.csv`.
- Exported workbooks under `exports/`.
- `exports/daily_summary.md`.
- Receipts under `receipts/`.
- Backups under `backups/`.
- Archived reset data under `data/archive/`.

When using a public repo, GitHub inbox updates must use `customer_code`, not real customer names. `sync_github_inbox.py` maps `customer_code` values to real local customer names using `data/private_customer_map.csv`, which is ignored by Git and should stay local.

Never commit real ledger data, payment details, addresses, receipts, exported workbooks, or private customer mapping files.

## Git Safety

- Do not commit `receipts/`.
- Do not commit `backups/`.
- Do not commit archived data under `data/archive/`.
- Do not commit `data/imports/chatgpt_updates.jsonl`.
- Do not commit exported workbooks under `exports/`.
- Do not commit private customer/job CSV data unless the repo is private and you intentionally want live data tracked.
- Treat `github_inbox/chatgpt_updates.jsonl` as private customer/job/money data. Track it only in a private repo.

See `.gitignore` for the active ignore rules and the optional `data/*.csv` recommendation.
