# Data Quality Checker

A small desktop app I built to stop manually eyeballing CSV/Excel files for messy data before doing anything with them.

## Why this exists

Every time I got a new dataset to work with, I ended up doing the same boring checks by hand: are there missing values, duplicate rows, weird dates, negative numbers where they shouldn't be, outliers that don't make sense. Doing this in Excel every single time got old fast, so I built a tool that does it for me in a couple of seconds.

## Features

### Analysis

- Total rows and columns
- Missing values, broken down per column with percentages
- Duplicate rows, and duplicates based on a specific key column (ID, email, etc.)
- Invalid or logically broken dates (e.g. a shipping date earlier than the order date)
- Negative values where they shouldn't exist, with configurable exceptions for columns like profit or margin
- Statistical outliers, calculated using IQR (not an arbitrary threshold)
- Mixed data types inside a single column
- Messy text: stray whitespace, broken encoding, placeholder "missing" values like `N/A`, `null`, `-`
- Format validation for emails and phone numbers

### Interactive table

- Every issue category is a clickable metric card — click "Outliers" and the table filters down to only the rows with outliers
- Full table view, no pagination or inner scrollbars — scroll with your mouse like a normal page
- Problematic cells are highlighted in red, hovering shows exactly what's wrong and how to fix it
- Select and copy individual values, or copy the entire table at once and paste it straight into Excel or Google Sheets as a real table

### Cleaning

- **Quick clean** — one click, applies safe conservative fixes automatically
- **Custom clean** — full control over what happens to each error type: fill missing numbers with median/mean, fill missing text with a placeholder or the most frequent value, drop duplicates, clip or remove outliers, and more
- **Smart fill** — missing numeric values can be filled using the median of a related category column instead of the whole column's median (e.g. filling missing prices using the median price within that specific product category)
- Nothing touches your original file until you choose to save
- Full change log of every modification
- One-click undo for the entire cleanup
- Export the result as CSV, Excel, or JSON

## Tech stack

- **Python** + **pandas** for the data logic
- **pywebview** for the desktop shell
- Plain **HTML/CSS/JS** for the UI — no frameworks
- Packaged into a standalone executable with **PyInstaller**

## Project structure

```
DataQualityTool/
├── core/
│   ├── analyzer.py      # scanning and issue detection
│   └── cleaner.py       # cleaning logic and configs
├── web/
│   └── index.html        # UI (HTML/CSS/JS)
├── app_web.py             # entry point (pywebview + Python bridge)
└── requirements.txt
```

## Running it

```bash
pip install -r requirements.txt
python app_web.py
```

## Building a standalone .exe

```bash
pyinstaller --noconsole --onefile --clean --add-data "web;web" app_web.py
```

## Status

Personal project, built to solve my own day-to-day annoyance with cleaning messy datasets. Still adding features as I run into new kinds of messy data in real files.
