from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def run_git_pull_if_available() -> tuple[bool, str]:
    probe = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
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


def sync_inbox() -> tuple[int, int, int]:
    ensure_layout()
    pulled, pull_message = run_git_pull_if_available()
    print(pull_message)

    lines = read_inbox_lines()
    if not lines:
        print(f"Inbox is empty: {GITHUB_INBOX_FILE}")
        return 0, 0, 0

    raw_update_ids = {row["update_id"] for row in read_csv("raw_updates.csv") if row.get("update_id")}
    queued_update_ids = valid_packet_ids_from_import_file()
    customer_map = load_private_customer_map()
    seen_ids = set(raw_update_ids) | set(queued_update_ids)
    sync_log = read_csv("github_sync_log.csv")

    appended = skipped = errors = 0
    with UPDATE_FILE.open("a", encoding="utf-8", newline="\n") as update_file:
        for line_number, line in lines:
            try:
                packet: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                append_log(sync_log, "", "error_invalid_json", f"Line {line_number}: {exc}")
                print(f"Invalid JSON in inbox line {line_number}: {exc}")
                errors += 1
                continue

            if not isinstance(packet, dict):
                append_log(sync_log, "", "error_invalid_json", f"Line {line_number}: not a JSON object")
                print(f"Invalid JSON in inbox line {line_number}: not a JSON object")
                errors += 1
                continue

            localized_packet, map_error = localize_customer_code(packet, customer_map)
            update_id = deterministic_update_id(localized_packet or packet)
            if update_id in seen_ids:
                append_log(
                    sync_log,
                    update_id,
                    "skipped_duplicate",
                    f"Line {line_number}: update_id already imported or queued locally.",
                )
                skipped += 1
                continue

            if map_error or localized_packet is None:
                append_log(sync_log, update_id, "error_customer_code", f"Line {line_number}: {map_error}")
                print(f"Customer code error in inbox line {line_number}: {map_error}")
                errors += 1
                continue

            update_file.write(json.dumps(localized_packet, ensure_ascii=False, separators=(",", ":")))
            update_file.write("\n")
            seen_ids.add(update_id)
            append_log(
                sync_log,
                update_id,
                "appended",
                f"Line {line_number}: appended to data/imports/chatgpt_updates.jsonl.",
            )
            appended += 1

    write_csv("github_sync_log.csv", sync_log)
    print(f"GitHub inbox sync complete: {appended} appended, {skipped} skipped, {errors} errors.")

    if appended == 0:
        if skipped or errors:
            export_workbook()
            print("Workbook refreshed with sync log updates: exports/Chris_Work_System.xlsx")
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
        raise RuntimeError(f"Import failed with exit code {result.returncode}.")

    print("Workbook refreshed: exports/Chris_Work_System.xlsx")
    return appended, skipped, errors


def main() -> int:
    try:
        _appended, _skipped, errors = sync_inbox()
    except RuntimeError as exc:
        print(f"SYNC FAILED: {exc}")
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
