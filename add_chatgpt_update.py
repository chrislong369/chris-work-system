from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from work_system import UPDATE_FILE, WORKBOOK_FILE, ensure_layout


ROOT = Path(__file__).resolve().parent


def read_json_from_prompt() -> tuple[dict | None, str, str]:
    print("Paste one ChatGPT JSON update, then press Enter.")
    print("Compact one-line JSON imports immediately.")
    print("For multi-line JSON, paste the full object and it will import once complete.")
    print("Nothing will be appended unless the JSON is valid.")
    lines: list[str] = []
    last_error = ""
    while True:
        try:
            line = input("> " if not lines else "")
        except EOFError:
            break
        if not line.strip() and lines:
            break
        lines.append(line)
        raw_text = "\n".join(lines).strip()
        if not raw_text:
            continue
        if raw_text[0] not in "{[":
            return None, raw_text, "JSON must start with an object."
        try:
            packet = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            continue
        if not isinstance(packet, dict):
            return None, raw_text, "the update must be one JSON object."
        return packet, raw_text, ""

    raw_text = "\n".join(lines).strip()
    if not raw_text:
        return None, raw_text, "No JSON entered."
    try:
        packet = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, raw_text, last_error or str(exc)
    if not isinstance(packet, dict):
        return None, raw_text, "the update must be one JSON object."
    return packet, raw_text, ""


def main() -> int:
    ensure_layout()
    packet, _raw_input_text, error = read_json_from_prompt()
    if error or packet is None:
        print(f"INVALID JSON: {error}")
        print(f"Nothing was appended to {UPDATE_FILE}")
        return 1

    UPDATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with UPDATE_FILE.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")

    print(f"Appended update to {UPDATE_FILE}")
    print("Running import...")
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
        print(f"IMPORT FAILED with exit code {result.returncode}.")
        print("The JSON line remains in the import file so you can fix and rerun.")
        return result.returncode

    if not WORKBOOK_FILE.exists():
        print("IMPORT FAILED: workbook export did not create the expected file.")
        print(f"Missing workbook: {WORKBOOK_FILE}")
        return 1

    print("IMPORT PASSED.")
    print(f"Workbook updated: {WORKBOOK_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
