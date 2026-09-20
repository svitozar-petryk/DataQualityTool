from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from core.analyzer import load_data, analyze_dataframe


class QualityCheckerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Data Quality Tool")
        self.geometry("640x500")
        self.configure(bg="#1e1e2e")
        self.resizable(False, False)

        self.file_path = None
        self._setup_ui()

    def _setup_ui(self):
        title_lbl = tk.Label(
            self, text="Проверка качества CSV",
            font=("Segoe UI", 16, "bold"), fg="#cdd6f4", bg="#1e1e2e"
        )
        title_lbl.pack(pady=15)

        # Верхняя панель
        file_frame = tk.Frame(self, bg="#313244", padx=15, pady=10)
        file_frame.pack(fill="x", px=20, pady=5)

        btn = tk.Button(
            file_frame, text="Открыть CSV", font=("Segoe UI", 10, "bold"),
            bg="#89b4fa", fg="#11111b", relief="flat", command=self.select_file, cursor="hand2"
        )
        btn.pack(side="left", padx=(0, 10))

        self.lbl_file = tk.Label(
            file_frame, text="Файл не выбран", font=("Segoe UI", 10),
            fg="#a6adc8", bg="#313244"
        )
        self.lbl_file.pack(side="left")

        # Панель статуса
        self.status_frame = tk.Frame(self, bg="#45475a", pady=8)
        self.status_frame.pack(fill="x", px=20, pady=10)

        self.lbl_status = tk.Label(
            self.status_frame, text="ОЖИДАНИЕ ФАЙЛА",
            font=("Segoe UI", 11, "bold"), fg="#bac2de", bg="#45475a"
        )
        self.lbl_status.pack()

        # Метрики
        grid_frame = tk.Frame(self, bg="#1e1e2e")
        grid_frame.pack(fill="both", expand=True, px=20, pady=5)

        self.card_widgets = {}
        labels = [
            ("total_rows", "Всего строк:"),
            ("total_cols", "Всего столбцов:"),
            ("total_missing", "Пропуски:"),
            ("duplicate_rows", "Дубликаты:"),
            ("invalid_dates", "Некорректные даты:"),
            ("logical_date_errors", "Ошибки логики дат:"),
            ("negative_values", "Отрицательные значения:"),
            ("potential_outliers", "Выбросы:")
        ]

        for idx, (key, title) in enumerate(labels):
            r, c = divmod(idx, 2)
            card = tk.Frame(grid_frame, bg="#313244", padx=10, pady=6)
            card.grid(row=r, column=c, sticky="nsew", padx=5, pady=4)

            tk.Label(card, text=title, font=("Segoe UI", 8), fg="#a6adc8", bg="#313244").pack(anchor="w")
            val_lbl = tk.Label(card, text="-", font=("Segoe UI", 11, "bold"), fg="#cdd6f4", bg="#313244")
            val_lbl.pack(anchor="w")
            self.card_widgets[key] = val_lbl

        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

    def select_file(self):
        selected = filedialog.askopenfilename(
            title="Выберите CSV файл",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if selected:
            self.file_path = Path(selected)
            self.lbl_file.config(text=self.file_path.name, fg="#cdd6f4")
            self.run_analysis()

    def run_analysis(self):
        df = load_data(self.file_path)
        if df is None:
            messagebox.showerror("Ошибка", "Не удалось прочитать файл")
            return

        metrics = analyze_dataframe(df)

        for key, widget in self.card_widgets.items():
            val = metrics[key]
            widget.config(text=str(val))
            if key not in ["total_rows", "total_cols"]:
                widget.config(fg="#f38ba8" if val > 0 else "#a6e3a1")

        if metrics["is_clean"]:
            self.status_frame.config(bg="#a6e3a1")
            self.lbl_status.config(text="ДАННЫЕ ЧИСТЫ", fg="#11111b", bg="#a6e3a1")
        else:
            self.status_frame.config(bg="#f38ba8")
            self.lbl_status.config(
                text=f"ТРЕБУЕТСЯ ОЧИСТКА ({metrics['total_issues']} ошибок)",
                fg="#11111b", bg="#f38ba8"
            )


if __name__ == "__main__":
    app = QualityCheckerApp()
    app.mainloop()
