import re
import unicodedata
import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================
# КОНФИГУРАЦИЯ ПРОВЕРОК
# ============================================================

NEGATIVE_ALLOWED_COLUMNS = {"profit", "margin", "discount", "delta", "change", "variance"}
MISSING_TOKENS = {"n/a", "na", "null", "none", "-", "?", "nan", "undefined"}
UNIQUE_KEY_CANDIDATES = ["orderid", "customerid", "email", "id"]

FORMAT_PATTERNS = {
    "email": re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    "phone": re.compile(r'^\+?[\d\s\-\(\)]{7,15}$'),
}
COLUMN_FORMAT_MAP = {
    "email": "email",
    "phone": "phone",
    "phonenumber": "phone",
}

VALUE_RANGES = {
    "customerage": (18, 100),
    "unitprice": (0, 10000),
    "discount": (0, 1),
}

IQR_MULTIPLIER = 1.5


# ============================================================
# ЗАГРУЗКА
# ============================================================

def load_data(file_path: Path) -> pd.DataFrame | None:
    if not file_path.exists():
        return None

    suffix = file_path.suffix.lower()
    try:
        if suffix == '.csv':
            return pd.read_csv(str(file_path))
        elif suffix in ('.xlsx', '.xls'):
            return pd.read_excel(str(file_path))
        elif suffix == '.json':
            return pd.read_json(str(file_path))
        else:
            return None
    except Exception:
        return None


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ПРОВЕРКИ
# ============================================================

def _is_missing_token(val) -> bool:
    if pd.isna(val):
        return False
    if not isinstance(val, str):
        return False
    return val.strip().lower() in MISSING_TOKENS or val.strip() == ""


def _has_whitespace_issue(val) -> bool:
    if not isinstance(val, str):
        return False
    return val != val.strip()


def _has_mojibake(val) -> bool:
    if not isinstance(val, str):
        return False
    if "\ufffd" in val:
        return True
    mojibake_markers = ("Ã", "â€", "Ð", "\x81", "\x8d", "\x8f", "\x90", "\x9d")
    return any(m in val for m in mojibake_markers)


def _looks_numeric(val: str) -> bool:
    return bool(re.fullmatch(r'-?\d+([.,]\d+)?', val.strip()))


def _looks_date(val: str) -> bool:
    parsed = pd.to_datetime(val, errors='coerce')
    return pd.notna(parsed)


def _classify_text_type(val: str) -> str:
    if _looks_numeric(val):
        return "numeric"
    if _looks_date(val):
        return "date"
    return "text"


def _column_is_negative_allowed(col: str) -> bool:
    return col.lower() in NEGATIVE_ALLOWED_COLUMNS


def _iqr_bounds(series: pd.Series) -> tuple[float, float]:
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return q1 - IQR_MULTIPLIER * iqr, q3 + IQR_MULTIPLIER * iqr


# ============================================================
# ГЛАВНЫЙ АНАЛИЗ (Сводные метрики)
# ============================================================

def analyze_dataframe(df: pd.DataFrame) -> dict:
    n_rows = len(df)
    columns = list(df.columns)

    missing_by_column = {}
    for col in columns:
        real_na = df[col].isna().sum()
        token_na = df[col].apply(_is_missing_token).sum()
        total_na = int(real_na + token_na)
        missing_by_column[col] = {
            "count": total_na,
            "pct": round(total_na / n_rows * 100, 1) if n_rows else 0.0
        }
    total_missing = sum(v["count"] for v in missing_by_column.values())

    duplicate_rows = int(df.duplicated().sum())

    key_duplicates = {}
    for col in columns:
        if col.lower() in UNIQUE_KEY_CANDIDATES:
            dup_count = int(df[col].dropna().duplicated().sum())
            if dup_count > 0:
                key_duplicates[col] = dup_count

    date_cols = [c for c in columns if 'date' in c.lower()]
    parsed_dates = {c: pd.to_datetime(df[c], errors='coerce') for c in date_cols}
    invalid_dates = sum(
        int((df[c].notna() & parsed_dates[c].isna()).sum()) for c in date_cols
    )
    logical_date_errors = 0
    if 'OrderDate' in columns and 'ShippingDate' in columns:
        p_o, p_s = parsed_dates.get('OrderDate'), parsed_dates.get('ShippingDate')
        if p_o is not None and p_s is not None:
            logical_date_errors = int(((p_s < p_o) & p_o.notna() & p_s.notna()).sum())

    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    negative_values = 0
    for col in numeric_cols:
        if col.lower().endswith('id'):
            continue
        if _column_is_negative_allowed(col):
            continue
        negative_values += int((df[col] < 0).sum())

    outliers = 0
    outlier_details = {}
    for col in numeric_cols:
        if col.lower().endswith('id'):
            continue
        series = df[col].dropna()
        if len(series) < 4:
            continue
        low, high = _iqr_bounds(series)
        col_outliers = int(((df[col] < low) | (df[col] > high)).sum())
        if col_outliers > 0:
            outlier_details[col] = {"count": col_outliers, "lower": round(low, 2), "upper": round(high, 2)}
        outliers += col_outliers

    range_violations = 0
    for col, (lo, hi) in VALUE_RANGES.items():
        matched_col = next((c for c in columns if c.lower() == col), None)
        if matched_col is None:
            continue
        s = df[matched_col]
        cond = pd.Series(False, index=df.index)
        if lo is not None:
            cond |= (s < lo)
        if hi is not None:
            cond |= (s > hi)
        range_violations += int(cond.sum())

    mixed_type_counts = {}
    for col in columns:
        if df[col].dtype != object:
            continue
        non_missing = df[col].dropna().astype(str)
        non_missing = non_missing[~non_missing.apply(_is_missing_token)]
        if non_missing.empty:
            continue
        types = non_missing.apply(_classify_text_type)
        majority_type = types.value_counts().idxmax()
        majority_share = types.value_counts(normalize=True).max()
        if majority_share >= 0.6:
            minority_count = int((types != majority_type).sum())
            if minority_count > 0:
                mixed_type_counts[col] = {"majority_type": majority_type, "outliers": minority_count}

    whitespace_issues = 0
    mojibake_issues = 0
    for col in columns:
        if df[col].dtype != object:
            continue
        whitespace_issues += int(df[col].dropna().apply(_has_whitespace_issue).sum())
        mojibake_issues += int(df[col].dropna().apply(_has_mojibake).sum())

    format_violations = 0
    for col in columns:
        fmt_key = COLUMN_FORMAT_MAP.get(col.lower())
        if not fmt_key:
            continue
        pattern = FORMAT_PATTERNS[fmt_key]
        s = df[col].dropna().astype(str)
        bad = s[~s.apply(lambda v: bool(pattern.match(v.strip())))]
        format_violations += len(bad)

    total_issues = (
        total_missing + duplicate_rows + invalid_dates + logical_date_errors +
        negative_values + outliers + range_violations +
        sum(v["outliers"] for v in mixed_type_counts.values()) +
        whitespace_issues + mojibake_issues + format_violations +
        sum(key_duplicates.values())
    )

    return {
        "total_rows": n_rows,
        "total_cols": len(columns),
        "total_missing": total_missing,
        "missing_by_column": missing_by_column,
        "duplicate_rows": duplicate_rows,
        "key_duplicates": key_duplicates,
        "invalid_dates": invalid_dates,
        "logical_date_errors": logical_date_errors,
        "negative_values": negative_values,
        "potential_outliers": outliers,
        "outlier_details": outlier_details,
        "range_violations": range_violations,
        "mixed_type_counts": mixed_type_counts,
        "whitespace_issues": whitespace_issues,
        "mojibake_issues": mojibake_issues,
        "format_violations": format_violations,
        "total_issues": total_issues,
        "is_clean": total_issues == 0,
    }


# ============================================================
# ПОСТРОЕНИЕ ТАБЛИЦЫ ДЛЯ UI (Оптимизированная версия)
# ============================================================

def build_table_data(df: pd.DataFrame) -> dict:
    columns = list(df.columns)
    n_rows = len(df)
    if n_rows == 0:
        return {"columns": columns, "rows": []}

    date_cols = [c for c in columns if 'date' in c.lower()]
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

    parsed_dates = {c: pd.to_datetime(df[c], errors='coerce') for c in date_cols}
    dup_mask = df.duplicated(keep=False).to_numpy()

    key_dup_masks = {
        col: (df[col].duplicated(keep=False) & df[col].notna()).to_numpy()
        for col in columns if col.lower() in UNIQUE_KEY_CANDIDATES
    }

    iqr_bounds = {}
    for col in numeric_cols:
        if not col.lower().endswith('id'):
            series = df[col].dropna()
            if len(series) >= 4:
                iqr_bounds[col] = _iqr_bounds(series)

    majority_types = {}
    for col in columns:
        if df[col].dtype == object:
            non_missing = df[col].dropna().astype(str)
            non_missing = non_missing[~non_missing.apply(_is_missing_token)]
            if not non_missing.empty:
                types = non_missing.apply(_classify_text_type)
                share = types.value_counts(normalize=True)
                if share.max() >= 0.6:
                    majority_types[col] = share.idxmax()

    raw_values = df.to_numpy()
    str_matrix = df.fillna("").astype(str).to_numpy()

    col_reasons = [[[] for _ in range(n_rows)] for _ in range(len(columns))]

    for col_idx, col in enumerate(columns):
        s = df[col]
        col_arr = raw_values[:, col_idx]
        reasons_list = col_reasons[col_idx]

        na_mask = s.isna().to_numpy()
        for i in np.where(na_mask)[0]:
            reasons_list[i].append(("missing", "Пропущено значение. Заполните ячейку или удалите строку."))

        if s.dtype == object:
            pseudo_mask = s.apply(_is_missing_token).to_numpy()
            for i in np.where(pseudo_mask)[0]:
                reasons_list[i].append(("missing", f"Текстовый псевдо-пропуск ('{col_arr[i]}'). Замените на реальное значение или NaN."))

            fmt_key = COLUMN_FORMAT_MAP.get(col.lower())
            pattern = FORMAT_PATTERNS.get(fmt_key) if fmt_key else None
            expected_type = majority_types.get(col)

            non_na_indices = np.where(~na_mask)[0]
            for i in non_na_indices:
                val = col_arr[i]
                if isinstance(val, str):
                    if not _is_missing_token(val):
                        if expected_type:
                            actual_type = _classify_text_type(val)
                            if actual_type != expected_type:
                                reasons_list[i].append(("mixed_type", f"Тип значения ({actual_type}) не совпадает с преобладающим типом столбца ({expected_type})."))

                        if pattern and not pattern.match(val.strip()):
                            reasons_list[i].append(("format", f"Не соответствует формату {fmt_key}."))

                    if _has_whitespace_issue(val):
                        reasons_list[i].append(("whitespace", "Есть лишние пробелы по краям значения."))

                    if _has_mojibake(val):
                        reasons_list[i].append(("mojibake", "Похоже на битую кодировку. Проверьте кодировку файла (UTF-8 vs Latin-1)."))

        if dup_mask.any():
            for i in np.where(dup_mask)[0]:
                reasons_list[i].append(("duplicate_row", "Строка дублируется целиком в другом месте файла."))

        if col in key_dup_masks:
            km = key_dup_masks[col]
            for i in np.where(km)[0]:
                reasons_list[i].append(("key_duplicate", f"Значение '{col_arr[i]}' повторяется в столбце {col}, хотя должно быть уникальным."))

        if col in date_cols:
            invalid_date_mask = (s.notna() & parsed_dates[col].isna()).to_numpy()
            for i in np.where(invalid_date_mask)[0]:
                reasons_list[i].append(("invalid_date", f"'{col_arr[i]}' не распознаётся как дата. Проверьте формат (ГГГГ-ММ-ДД)."))

        if col in ('OrderDate', 'ShippingDate') and 'OrderDate' in columns and 'ShippingDate' in columns:
            p_o, p_s = parsed_dates.get('OrderDate'), parsed_dates.get('ShippingDate')
            if p_o is not None and p_s is not None:
                logic_mask = ((p_s < p_o) & p_o.notna() & p_s.notna()).to_numpy()
                for i in np.where(logic_mask)[0]:
                    reasons_list[i].append(("logical_date", "Дата доставки раньше даты заказа."))

        if col in numeric_cols and not col.lower().endswith('id') and not _column_is_negative_allowed(col):
            neg_mask = (s < 0).fillna(False).to_numpy()
            for i in np.where(neg_mask)[0]:
                reasons_list[i].append(("negative", f"Отрицательное значение ({col_arr[i]}) недопустимо для этого столбца."))

        lo_hi = VALUE_RANGES.get(col.lower())
        if lo_hi:
            lo, hi = lo_hi
            cond = pd.Series(False, index=df.index)
            if lo is not None:
                cond |= (s < lo)
            if hi is not None:
                cond |= (s > hi)
            cond_mask = cond.fillna(False).to_numpy()
            for i in np.where(cond_mask)[0]:
                reasons_list[i].append(("range", f"Значение {col_arr[i]} выходит за допустимый диапазон [{lo}, {hi}]."))

        if col in iqr_bounds:
            low, high = iqr_bounds[col]
            out_mask = (((s < low) | (s > high)) & s.notna()).to_numpy()
            for i in np.where(out_mask)[0]:
                reasons_list[i].append(("outlier", f"Статистический выброс (IQR): {col_arr[i]} вне [{round(low, 2)}, {round(high, 2)}]."))

    rows = []
    for row_idx in range(n_rows):
        row_cells = {}
        row_categories = set()
        row_has_error = False

        for col_idx, col in enumerate(columns):
            reasons = col_reasons[col_idx][row_idx]
            has_cell_err = bool(reasons)

            if has_cell_err:
                row_has_error = True
                for cat, _ in reasons:
                    row_categories.add(cat)

            row_cells[col] = {
                "value": str_matrix[row_idx, col_idx],
                "error": has_cell_err,
                "reason": " ".join(text for _, text in reasons),
                "categories": [cat for cat, _ in reasons]
            }

        rows.append({
            "cells": row_cells,
            "has_error": row_has_error,
            "categories": sorted(row_categories)
        })

    return {"columns": columns, "rows": rows}