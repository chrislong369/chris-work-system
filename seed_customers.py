from __future__ import annotations

from work_system import DATA_DIR, SCHEMAS, SEED_CUSTOMERS, ensure_layout, read_csv, slug, write_csv


CUSTOMER_RENAMES = {
    "funkel": "Funfgeld",
    "funkgeld": "Funfgeld",
}


def seed_customers() -> tuple[int, int]:
    ensure_layout()
    rows = read_csv("customers.csv")
    by_name = {row["customer_name"].strip().lower(): row for row in rows}
    added = 0
    updated = 0
    for old_key, new_name in CUSTOMER_RENAMES.items():
        new_key = new_name.lower()
        if old_key in by_name and new_key not in by_name:
            by_name[old_key]["customer_name"] = new_name
            by_name[new_key] = by_name.pop(old_key)
            updated += 1
    for name, rate in SEED_CUSTOMERS:
        key = name.lower()
        if key not in by_name:
            row = {
                "customer_id": f"cust_{slug(name)}",
                "customer_name": name,
                "default_rate": rate,
                "default_payment_route": "",
                "default_location": "",
                "active": "true",
                "notes": "Seed customer",
            }
            rows.append(row)
            by_name[key] = row
            added += 1
        elif not by_name[key].get("default_rate") and rate:
            by_name[key]["default_rate"] = rate
            updated += 1
    write_csv("customers.csv", rows)
    update_customer_name_references()
    return added, updated


def update_customer_name_references() -> None:
    rename_by_lower = {old: new for old, new in CUSTOMER_RENAMES.items()}
    for filename, headers in SCHEMAS.items():
        if filename == "customers.csv":
            continue
        path = DATA_DIR / filename
        if not path.exists():
            continue
        rows = read_csv(filename)
        changed = False
        for row in rows:
            for field in ("customer", "customer_name"):
                value = row.get(field, "").strip()
                replacement = rename_by_lower.get(value.lower())
                if replacement:
                    row[field] = replacement
                    changed = True
        if changed:
            write_csv(filename, rows, headers)


if __name__ == "__main__":
    added_count, updated_count = seed_customers()
    print(f"Seed customers complete: {added_count} added, {updated_count} updated.")
