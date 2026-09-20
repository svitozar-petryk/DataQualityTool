import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from core.analyzer import load_data, analyze_dataframe


def print_report(file_name: str, metrics: dict):
    status = "CLEAN" if metrics["is_clean"] else "NEEDS CLEANING"
    print("=" * 40)
    print("      DATA QUALITY REPORT (CLI)")
    print("=" * 40)
    print(f"File Target:            {file_name}")
    print(f"Total Rows:             {metrics['total_rows']}")
    print(f"Total Columns:          {metrics['total_cols']}")
    print("-" * 40)
    print(f"Missing Values:         {metrics['total_missing']}")
    print(f"Duplicate Rows:         {metrics['duplicate_rows']}")
    print(f"Invalid Dates:          {metrics['invalid_dates']}")
    print(f"Logical Date Errors:    {metrics['logical_date_errors']}")
    print(f"Negative Values:        {metrics['negative_values']}")
    print(f"Potential Outliers:     {metrics['potential_outliers']}")
    print("-" * 40)
    print(f"OVERALL STATUS:         {status}")
    print("=" * 40)


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        file_path = Path(sys.argv[1])
    else:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askopenfilename(
            title="Выберите CSV файл для проверки",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not selected:
            print("Файл не выбран.")
            return
        file_path = Path(selected)

    df = load_data(file_path)
    if df is None:
        print(f"Ошибка: не удалось загрузить файл '{file_path}'")
        return

    metrics = analyze_dataframe(df)
    print_report(file_path.name, metrics)


if __name__ == "__main__":
    main()
