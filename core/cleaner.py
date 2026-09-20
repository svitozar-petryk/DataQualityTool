# core/cleaner.py
import re
import numpy as np
import pandas as pd
from pathlib import Path

MISSING_TOKENS = {"n/a", "na", "null", "none", "-", "?", "nan", "undefined"}
NEGATIVE_ALLOWED_COLUMNS = {"profit", "margin", "discount", "delta", "change", "variance"}
UNIQUE_KEY_CANDIDATES = ["orderid", "customerid", "email", "id"]
IQR_MULTIPLIER = 1.5
MIN_GROUP_CARDINALITY = 2
MAX_GROUP_CARDINALITY = 50


def _is_missing_token(val):
    if pd.isna(val):
        return False
    if not isinstance(val, str):
        return False
    return val.strip().lower() in MISSING_TOKENS or val.strip() == ""


def _iqr_bounds(series):
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return q1 - IQR_MULTIPLIER * iqr, q3 + IQR_MULTIPLIER * iqr


def _eta_squared(df, num_col, cat_col):
    sub = df[[num_col, cat_col]].dropna()
    if sub[cat_col].nunique() < MIN_GROUP_CARDINALITY or sub[cat_col].nunique() > MAX_GROUP_CARDINALITY:
        return -1
    if len(sub) < 10:
        return -1
    grand_mean = sub[num_col].mean()
    ss_total = ((sub[num_col] - grand_mean) ** 2).sum()
    if ss_total == 0:
        return -1
    ss_between = 0
    for _, g in sub.groupby(cat_col):
        ss_between += len(g) * (g[num_col].mean() - grand_mean) ** 2
    return ss_between / ss_total


def find_best_group_column(df, num_col, candidate_cols):
    best_col, best_score = None, -1
    for c in candidate_cols:
        if c == num_col:
            continue
        if df[c].dtype == object or str(df[c].dtype).startswith("category"):
            score = _eta_squared(df, num_col, c)
            if score > best_score:
                best_score, best_col = score, c
    return best_col, best_score


def get_column_types(df):
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = [c for c in df.columns if df[c].dtype == object]
    return numeric_cols, categorical_cols


def build_default_config(df, mode):
    numeric_cols, categorical_cols = get_column_types(df)
    config = {
        "mode": mode,
        "pseudo_missing": {"action": "to_nan"},
        "whitespace": {"action": "trim"},
        "missing": {},
        "duplicate_rows": {"action": "keep_first"},
        "key_duplicates": {},
        "outliers": {},
        "negatives": {},
        "smart_group_override": {},
    }

    for col in numeric_cols:
        if col.lower().endswith("id"):
            continue
        config["missing"][col] = {"action": "median"}
        series = df[col].dropna()
        if len(series) >= 4:
            config["outliers"][col] = {"action": "flag"}
        if col.lower() not in NEGATIVE_ALLOWED_COLUMNS:
            config["negatives"][col] = {"action": "abs"}

    for col in categorical_cols:
        config["missing"][col] = {"action": "mode"}

    for col in df.columns:
        if col.lower() in UNIQUE_KEY_CANDIDATES:
            config["key_duplicates"][col] = {"action": "keep_first"}

    if mode == "smart":
        for col in numeric_cols:
            if col.lower().endswith("id"):
                continue
            best_col, score = find_best_group_column(df, col, categorical_cols)
            if best_col and score > 0.06:
                config["missing"][col] = {
                    "action": "median_group",
                    "group_col": best_col,
                    "score": round(float(score), 3)
                }

    return config


def preview_cleaning(df, config):
    working = df.copy()
    log = []
    numeric_cols, categorical_cols = get_column_types(working)

    if config.get("pseudo_missing", {}).get("action") == "to_nan":
        for col in working.columns:
            if working[col].dtype != object:
                continue
            mask = working[col].apply(_is_missing_token)
            n = int(mask.sum())
            if n:
                working.loc[mask, col] = np.nan
                log.append(f"Столбец '{col}': {n} псевдо-пропусков ('N/A','-' и т.п.) заменено на NaN")

    if config.get("whitespace", {}).get("action") == "trim":
        for col in working.columns:
            if working[col].dtype != object:
                continue
            before = working[col].copy()
            working[col] = working[col].apply(
                lambda v: re.sub(r"\s+", " ", v.strip()) if isinstance(v, str) else v
            )
            changed = int((before.astype(str) != working[col].astype(str)).sum())
            if changed:
                log.append(f"Столбец '{col}': обрезаны пробелы в {changed} значениях")

    missing_cfg = config.get("missing", {})
    for col, rule in missing_cfg.items():
        if col not in working.columns:
            continue
        action = rule.get("action")
        na_mask = working[col].isna()
        n_na = int(na_mask.sum())
        if n_na == 0 or action == "skip":
            continue

        if action == "zero":
            working.loc[na_mask, col] = 0
            log.append(f"Столбец '{col}': {n_na} пропусков заполнено значением 0")

        elif action == "mean":
            val = working[col].mean()
            working.loc[na_mask, col] = val
            log.append(f"Столбец '{col}': {n_na} пропусков заполнено средним ({round(val,2)})")

        elif action == "median":
            val = working[col].median()
            working.loc[na_mask, col] = val
            log.append(f"Столбец '{col}': {n_na} пропусков заполнено медианой ({round(val,2)})")

        elif action == "median_group":
            group_col = config.get("smart_group_override", {}).get(col, rule.get("group_col"))
            if group_col and group_col in working.columns:
                group_medians = working.groupby(group_col)[col].median()
                global_median = working[col].median()
                filled_rows = []
                for idx in working[na_mask].index:
                    g = working.at[idx, group_col]
                    fill_val = group_medians.get(g, np.nan)
                    if pd.isna(fill_val):
                        fill_val = global_median
                        note = "глобальная медиана (fallback)"
                    else:
                        note = f"медиана по {group_col}='{g}'"
                    working.at[idx, col] = fill_val
                    filled_rows.append(f"Строка {idx}, [{col}]: NaN -> {round(fill_val,2)} ({note})")
                log.extend(filled_rows[:50])
                if len(filled_rows) > 50:
                    log.append(f"... и ещё {len(filled_rows)-50} строк аналогично для '{col}'")

        elif action == "mode":
            m = working[col].mode()
            if len(m):
                working.loc[na_mask, col] = m.iloc[0]
                log.append(f"Столбец '{col}': {n_na} пропусков заполнено модой ('{m.iloc[0]}')")

        elif action == "unknown_text":
            working.loc[na_mask, col] = "Н/Д"
            log.append(f"Столбец '{col}': {n_na} пропусков заполнено 'Н/Д'")

        elif action == "drop_row":
            working = working[~working[col].isna()]
            log.append(f"Столбец '{col}': удалено {n_na} строк с пропуском")

    neg_cfg = config.get("negatives", {})
    for col, rule in neg_cfg.items():
        if col not in working.columns:
            continue
        action = rule.get("action")
        if action == "skip":
            continue
        mask = working[col] < 0
        n = int(mask.sum())
        if n == 0:
            continue
        if action == "abs":
            working.loc[mask, col] = working.loc[mask, col].abs()
            log.append(f"Столбец '{col}': {n} отрицательных значений заменено на модуль")
        elif action == "zero":
            working.loc[mask, col] = 0
            log.append(f"Столбец '{col}': {n} отрицательных значений заменено на 0")
        elif action == "to_nan":
            working.loc[mask, col] = np.nan
            log.append(f"Столбец '{col}': {n} отрицательных значений заменено на NaN")
        elif action == "drop_row":
            working = working[~mask]
            log.append(f"Столбец '{col}': удалено {n} строк с отрицательным значением")

    outlier_cfg = config.get("outliers", {})
    for col, rule in outlier_cfg.items():
        if col not in working.columns:
            continue
        action = rule.get("action")
        if action in ("skip", "flag"):
            continue
        series = working[col].dropna()
        if len(series) < 4:
            continue
        low, high = _iqr_bounds(series)
        mask = (working[col] < low) | (working[col] > high)
        n = int(mask.sum())
        if n == 0:
            continue
        if action == "clip":
            working[col] = working[col].clip(lower=low, upper=high)
            log.append(f"Столбец '{col}': {n} выбросов обрезано до границ IQR [{round(low,2)},{round(high,2)}]")
        elif action == "to_nan":
            working.loc[mask, col] = np.nan
            log.append(f"Столбец '{col}': {n} выбросов заменено на NaN")
        elif action == "drop_row":
            working = working[~mask]
            log.append(f"Столбец '{col}': удалено {n} строк-выбросов")

    dup_action = config.get("duplicate_rows", {}).get("action", "skip")
    if dup_action != "skip":
        mask = working.duplicated(keep=False)
        n = int(mask.sum())
        if n:
            if dup_action == "keep_first":
                working = working.drop_duplicates(keep="first")
            elif dup_action == "keep_last":
                working = working.drop_duplicates(keep="last")
            log.append(f"Полных дубликатов строк обработано: {n}")

    key_cfg = config.get("key_duplicates", {})
    for col, rule in key_cfg.items():
        if col not in working.columns:
            continue
        action = rule.get("action", "skip")
        if action == "skip":
            continue
        mask = working[col].duplicated(keep=False) & working[col].notna()
        n = int(mask.sum())
        if n == 0:
            continue
        if action == "keep_first":
            working = working.drop_duplicates(subset=[col], keep="first")
        elif action == "keep_last":
            working = working.drop_duplicates(subset=[col], keep="last")
        elif action == "drop_all":
            working = working[~mask]
        log.append(f"Столбец '{col}': {n} дублей ключа обработано ({action})")

    working = working.reset_index(drop=True)
    return working, log


def save_cleaned(df, original_path: Path, target_format: str) -> Path:
    out_path = original_path.with_name(original_path.stem + "_cleaned")
    if target_format == "csv":
        out_path = out_path.with_suffix(".csv")
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
    elif target_format == "xlsx":
        out_path = out_path.with_suffix(".xlsx")
        df.to_excel(out_path, index=False)
    elif target_format == "json":
        out_path = out_path.with_suffix(".json")
        df.to_json(out_path, orient="records", force_ascii=False, indent=2)
    return out_path


def save_log(log_lines, original_path: Path) -> Path:
    out_path = original_path.with_name(original_path.stem + "_clean_log.txt")
    out_path.write_text("\n".join(log_lines), encoding="utf-8")
    return out_path

# core/cleaner.py — добавить в конец файла

def build_quick_config(df):
    numeric_cols, categorical_cols = get_column_types(df)
    config = {
        "mode": "quick",
        "pseudo_missing": {"action": "to_nan"},
        "whitespace": {"action": "trim"},
        "missing": {},
        "duplicate_rows": {"action": "keep_first"},
        "key_duplicates": {},
        "outliers": {},
        "negatives": {},
        "smart_group_override": {},
    }

    for col in numeric_cols:
        if col.lower().endswith("id"):
            continue
        config["missing"][col] = {"action": "median"}
        config["outliers"][col] = {"action": "flag"}
        if col.lower() not in NEGATIVE_ALLOWED_COLUMNS:
            config["negatives"][col] = {"action": "skip"}

    for col in categorical_cols:
        config["missing"][col] = {"action": "unknown_text"}

    for col in df.columns:
        if col.lower() in UNIQUE_KEY_CANDIDATES:
            config["key_duplicates"][col] = {"action": "skip"}

    return config