from export_workbook import export_workbook


if __name__ == "__main__":
    path = export_workbook()
    print(f"Dashboard rebuilt in {path}")
