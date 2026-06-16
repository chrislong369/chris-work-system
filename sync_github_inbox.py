from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from export_daily_summary import export_daily_summary
from export_workbook import export_workbook
from work_system import (
    GITHUB_INBOX_FILE,
    ROOT,
    UPDATE_FILE,
    clean_cell,
    deterministic_update_id,
    ensure_layout,
    iso_now,
    parse_jsonl,
    read_csv,
    stable_id,
    write_csv,
)


SOURCE = "github_inbox/chatgpt_updates.jsonl"
PRIVATE_CUSTOMER_MAP_FILE = ROOT / "data" / "private_customer_map.csv"


def is_git_repo() -> bool:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def tracked_local_changes() -> list[str]:
    if not is_git_repo():
        return []
    result = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ["unable to read git status"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def run_git_pull_if_available() -> tuple[bool, str]:
    if not is_git_repo():
        return False, "No Git repo found here; skipped GitHub pull and read local inbox file only."

    result = subprocess.run(
        ["git", "-C", str(ROOT), "pull", "--ff-only"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        raise RuntimeError(
            "GitHub fetch/pull failed. Fix the Git remote/upstream or authentication, then rerun.\n"
            + output
        )
    return True, output or "Git pull completed."


def valid_packet_ids_from_import_file() -> set[str]:
    ids: set[str] = set()
    for _line_number, packet, parse_error in parse_jsonl(UPDATE_FILE):
        if parse_error:
            continue
        ids.add(deterministic_update_id(packet))
    return ids


def load_private_customer_map() -> dict[str, dict[str, str]]:
    if not PRIVATE_CUSTOMER_MAP_FILE.exists():
        return {}
    rows = read_csv(PRIVATE_CUSTOMER_MAP_FILE)
    return {
        row.get("customer_code", "").strip(): row
        for row in rows
        if row.get("customer_code", "").strip()
    }


def localize_customer_code(
    packet: dict[str, Any],
    customer_map: dict[str, dict[str, str]],
) -> tuple[dict[str, Any] | None, str]:
    customer_code = clean_cell(packet.get("customer_code")).strip()
    if not customer_code:
        return packet, ""
    mapped = customer_map.get(customer_code)
    if not mapped:
        return None, f"unknown customer_code: {customer_code}"

    localized = dict(packet)
    localized["customer"] = mapped.get("customer_name", "").strip()
    if not clean_cell(localized.get("hourly_rate")).strip() and mapped.get("default_rate"):
        localized["hourly_rate"] = mapped["default_rate"]
    if (
        localized.get("update_type") == "schedule"
        and not clean_cell(localized.get("calendar_location")).strip()
        and mapped.get("default_location")
    ):
        localized["calendar_location"] = mapped["default_location"]
    return localized, ""


def read_inbox_lines() -> list[tuple[int, str]]:
    if not GITHUB_INBOX_FILE.exists():
        return []
    return [
        (line_number, line)
        for line_number, line in enumerate(
            GITHUB_INBOX_FILE.read_text(encoding="utf-8-sig").splitlines(), 1
        )
        if line.strip()
    ]


def inbox_line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def append_log(
    log_rows: list[dict[str, str]],
    update_id: str,
    action: str,
    notes: str,
) -> None:
    synced_at = iso_now()
    log_rows.append({
        "sync_id": stable_id("sync", synced_at, update_id, action, len(log_rows)),
        "synced_at": synced_at,
        "update_id": update_id,
        "source": SOURCE,
        "action": action,
        "notes": notes,
    })


def append_processed(
    processed_rows: list[dict[str, str]],
    inbox_hash: str,
    update_id: str,
    line_number: int,
    action: str,
    status: str,
    notes: str,
) -> None:
    processed_at = iso_now()
    processed_rows.append({
        "processed_id": stable_id("pinbox", inbox_hash),
        "processed_at": processed_at,
        "inbox_hash": inbox_hash,
        "update_id": update_id,
        "source": SOURCE,
        "line_number": str(line_number),
        "action": action,
        "status": status,
        "notes": notes,
    })


def write_exports_after_sync_change() -> None:
    export_workbook()
    export_daily_summary()


def sync_inbox(auto: bool = False) -> tuple[int, int, int]:
    ensure_layout()
    sync_log = read_csv("github_sync_log.csv")

    if auto:
        dirty = tracked_local_changes()
        if dirty:
            warning = (
                "Auto-sync skipped because tracked local changes exist. "
                "Commit/stash/discard tracked changes, then rerun sync. "
                f"First entries: {' | '.join(dirty[:8])}"
            )
            print(f"SYNC WARNING: {warning}")
            append_log(sync_log, "", "warning_dirty_repo", warning)
            write_csv("github_sync_log.csv", sync_log)
            write_exports_after_sync_change()
            return 0, 0, 1

    _pulled, pull_message = run_git_pull_if_available()
    print(pull_message)

    lines = read_inbox_lines()
    if not lines:
        print(f"Inbox is empty: {GITHUB_INBOX_FILE}")
        return 0, 0, 0

    raw_update_ids = {row["update_id"] for row in read_csv("raw_updates.csv") if row.get("update_id")}
    queued_update_ids = valid_packet_ids_from_import_file()
    customer_map = load_private_customer_map()
    seen_ids = set(raw_update_ids) | set(queued_update_ids)
    processed_rows = read_csv("processed_github_inbox.csv")
    processed_hashes = {
        row.get("inbox_hash", "").strip()
        for row in processed_rows
        if row.get("inbox_hash", "").strip()
    }

    appended = skipped = errors = already_processed = newly_tracked = 0
    with UPDATE_FILE.open("a", encoding="utf-8", newline="\n") as update_file:
        for line_number, line in lines:
            item_hash = inbox_line_hash(line)
            if item_hash in processed_hashes:
                already_processed += 1
                continue

            try:
                packet: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                notes = f"Line {line_number}: {exc}"
                append_processed(
                    processed_rows, item_hash, "", line_number,
                    "rejected_invalid_json", "rejected", notes,
                )
                processed_hashes.add(item_hash)
                append_log(sync_log, "", "error_invalid_json", notes)
                print(f"Invalid JSON in inbox line {line_number}: {exc}")
                errors += 1
                newly_tracked += 1
                continue

            if not isinstance(packet, dict):
                notes = f"Line {line_number}: not a JSON object"
                append_processed(
                    processed_rows, item_hash, "", line_number,
                    "rejected_invalid_json", "rejected", notes,
                )
                processed_hashes.add(item_hash)
                append_log(sync_log, "", "error_invalid_json", notes)
                print(f"Invalid JSON in inbox line {line_number}: not a JSON object")
                errors += 1
                newly_tracked += 1
                continue

            localized_packet, map_error = localize_customer_code(packet, customer_map)
            update_id = deterministic_update_id(localized_packet or packet)
            if update_id in seen_ids:
                notes = f"Line {line_number}: update_id already imported or queued locally."
                append_processed(
                    processed_rows, item_hash, update_id, line_number,
                    "duplicate_already_imported", "processed", notes,
                )
                processed_hashes.add(item_hash)
                skipped += 1
                newly_tracked += 1
                continue

            if map_error or localized_packet is None:
                notes = f"Line {line_number}: {map_error}"
                append_processed(
                    processed_rows, item_hash, update_id, line_number,
                    "rejected_customer_code", "rejected", notes,
                )
                processed_hashes.add(item_hash)
                append_log(sync_log, update_id, "error_customer_code", notes)
                print(f"Customer code error in inbox line {line_number}: {map_error}")
                errors += 1
                newly_tracked += 1
                continue

            update_file.write(json.dumps(localized_packet, ensure_ascii=False, separators=(",", ":")))
            update_file.write("\n")
            seen_ids.add(update_id)
            notes = f"Line {line_number}: appended to data/imports/chatgpt_updates.jsonl."
            append_processed(
                processed_rows, item_hash, update_id, line_number,
                "appended", "processed", notes,
            )
            processed_hashes.add(item_hash)
            append_log(sync_log, update_id, "appended", notes)
            appended += 1
            newly_tracked += 1

    write_csv("processed_github_inbox.csv", processed_rows)
    write_csv("github_sync_log.csv", sync_log)
    print(
        "GitHub inbox sync complete: "
        f"{appended} appended, {skipped} duplicates marked processed, "
        f"{already_processed} already processed, {errors} errors."
    )

    if appended == 0:
        if newly_tracked or errors:
            write_exports_after_sync_change()
            print("Workbook and daily summary refreshed with sync state updates.")
        print("No new updates appended; importer was not run.")
        return appended, skipped, errors

    print("Running import_chatgpt_updates.py...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "import_chatgpt_updates.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print("ERROR OUTPUT:")
        print(result.stderr.rstrip())
    if result.returncode != 0:
        sync_log = read_csv("github_sync_log.csv")
        append_log(sync_log, "", "error_import_failed", f"Import failed with exit code {result.returncode}.")
        write_csv("github_sync_log.csv", sync_log)
        write_exports_after_sync_change()
        raise RuntimeError(f"Import failed with exit code {result.returncode}.")

    export_daily_summary()
    print("Workbook refreshed: exports/Chris_Work_System.xlsx")
    print("Daily summary refreshed: exports/daily_summary.md")
    return appended, skipped, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GitHub inbox updates into the local import queue.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run in scheduled-task mode with dirty tracked repo protection.",
    )
    args = parser.parse_args()
    try:
        _appended, _skipped, errors = sync_inbox(auto=args.auto)
    except RuntimeError as exc:
        print(f"SYNC FAILED: {exc}")
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
