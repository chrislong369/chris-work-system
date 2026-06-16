from __future__ import annotations

from work_system import SEED_CUSTOMERS, ensure_layout, read_csv, slug, write_csv


def seed_customers() -> tuple[int, int]:
    ensure_layout()
    rows = read_csv("customers.csv")
    by_name = {row["customer_name"].strip().lower(): row for row in rows}
    added = 0
    updated = 0
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
    return added, updated


if __name__ == "__main__":
    added_count, updated_count = seed_customers()
    print(f"Seed customers complete: {added_count} added, {updated_count} updated.")

