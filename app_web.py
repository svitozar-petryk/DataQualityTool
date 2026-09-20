import sys
from pathlib import Path
import webview
from core.analyzer import load_data, analyze_dataframe, build_table_data
from core.cleaner import (
    build_default_config,
    build_quick_config,
    preview_cleaning,
    save_cleaned,
    save_log,
)


class Api:
    def __init__(self):
        self.window = None
        self.current_df = None
        self.current_path = None
        self.cleaned_df = None
        self.clean_log = []

    def select_and_analyze(self):
        if self.window is None:
            return None

        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(
                'Data files (*.csv;*.xlsx;*.xls;*.json)',
                'CSV Files (*.csv)',
                'Excel Files (*.xlsx;*.xls)',
                'JSON Files (*.json)',
                'All files (*.*)'
            )
        )
        if not result:
            return None

        file_path = Path(result[0])
        df = load_data(file_path)
        if df is None:
            return None

        self.current_df = df
        self.current_path = file_path
        self.cleaned_df = None
        self.clean_log = []

        metrics = analyze_dataframe(df)
        table = build_table_data(df)
        return {"file_name": file_path.name, "metrics": metrics, "table": table}

    def get_clean_config(self, mode):
        if self.current_df is None:
            return None
        config = build_default_config(self.current_df, mode)
        return config

    def preview_clean(self, config):
        if self.current_df is None:
            return None
        cleaned, log = preview_cleaning(self.current_df, config)
        self.cleaned_df = cleaned
        self.clean_log = log
        metrics = analyze_dataframe(cleaned)
        table = build_table_data(cleaned)
        return {"metrics": metrics, "table": table, "log": log}

    def quick_clean(self):
        if self.current_df is None:
            return None
        config = build_quick_config(self.current_df)
        cleaned, log = preview_cleaning(self.current_df, config)
        self.cleaned_df = cleaned
        self.clean_log = log
        metrics = analyze_dataframe(cleaned)
        table = build_table_data(cleaned)
        return {"metrics": metrics, "table": table, "log": log}

    def undo_clean(self):
        self.cleaned_df = None
        self.clean_log = []
        if self.current_df is None:
            return None
        metrics = analyze_dataframe(self.current_df)
        table = build_table_data(self.current_df)
        return {"metrics": metrics, "table": table}

    def save_cleaned_file(self, target_format):
        if self.cleaned_df is None or self.current_path is None:
            return None

        result = self.window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory='',
            save_filename=self.current_path.stem + "_cleaned." + target_format
        )
        if not result:
            return None

        dest = Path(result if isinstance(result, str) else result[0])
        if target_format == "csv":
            self.cleaned_df.to_csv(dest, index=False, encoding="utf-8-sig")
        elif target_format == "xlsx":
            self.cleaned_df.to_excel(dest, index=False)
        elif target_format == "json":
            self.cleaned_df.to_json(dest, orient="records", force_ascii=False, indent=2)

        return {"saved_path": str(dest)}

    def save_clean_log(self):
        if not self.clean_log or self.current_path is None:
            return None

        result = self.window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory='',
            save_filename=self.current_path.stem + "_clean_log.txt"
        )
        if not result:
            return None

        dest = Path(result if isinstance(result, str) else result[0])
        dest.write_text("\n".join(self.clean_log), encoding="utf-8")
        return {"saved_path": str(dest)}


def load_html_content() -> str:
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent
    return (base_path / 'web' / 'index.html').read_text(encoding='utf-8')


if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        title="Data Quality Checker",
        html=load_html_content(),
        js_api=api,
        resizable=True
    )
    api.window = window

    def on_loaded():
        window.maximize()

    window.events.loaded += on_loaded

    webview.start(debug=False)