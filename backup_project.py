from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKUPS_DIR = ROOT / "backups"
WORKBOOK = ROOT / "exports" / "Chris_Work_System.xlsx"


def add_file(zip_handle: zipfile.ZipFile, path: Path) -> None:
    if path.exists() and path.is_file():
        zip_handle.write(path, path.relative_to(ROOT))


def add_tree(zip_handle: zipfile.ZipFile, directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.rglob("*"):
        if path.is_file():
            zip_handle.write(path, path.relative_to(ROOT))


def create_backup() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = BACKUPS_DIR / f"chris_work_system_backup_{timestamp}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for pattern in ("*.py", "*.cjs", "*.bat"):
            for path in ROOT.glob(pattern):
                add_file(archive, path)
        add_file(archive, ROOT / ".gitignore")
        add_tree(archive, ROOT / "docs")
        for path in (ROOT / "data").glob("*.csv"):
            add_file(archive, path)
        add_file(archive, WORKBOOK)
    return output


if __name__ == "__main__":
    print(create_backup())
