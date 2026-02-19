import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Callable, Optional
from shmirot_gdud.core.models import TimeWindow, Group, ScheduleRange
from shmirot_gdud.gui.utils import bidi_text

class TimeWindowDialog(tk.Toplevel):
    def __init__(self, parent, title: str, windows: List[TimeWindow], on_save: Callable[[List[TimeWindow]], None]):
        super().__init__(parent)
        self.title(bidi_text(title))
        self.geometry("600x450")
        self.windows = [w for w in windows] # Copy
        self.on_save = on_save

        self._create_ui()

    def _create_ui(self):
        # Right-to-Left alignment for Hebrew
        
        # List of windows
        columns = ("End", "Start", "Day") 
        
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        self.tree.heading("Day", text=bidi_text("יום"))
        self.tree.heading("Start", text=bidi_text("שעת התחלה"))
        self.tree.heading("End", text=bidi_text("שעת סיום"))
        
        self.tree.column("Day", anchor="center")
        self.tree.column("Start", anchor="center")
        self.tree.column("End", anchor="center")
        
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._refresh_list()

        # Add/Remove controls
        control_frame = ttk.LabelFrame(self, text=bidi_text("הוספת חלון זמן"), padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # Grid layout for controls (RTL simulation)
        
        ttk.Label(control_frame, text=bidi_text("יום:")).grid(row=0, column=5, padx=5, sticky="e")
        self.day_var = tk.StringVar()
        
        # Combobox for Day selection instead of Entry
        self.day_combo = ttk.Combobox(control_frame, textvariable=self.day_var, width=15, justify="right", state="readonly")
        # Added "All Week" option
        days_list = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "כל השבוע"]
        self.day_combo['values'] = [bidi_text(d) for d in days_list]
        self.day_combo.grid(row=0, column=4, padx=5)

        ttk.Label(control_frame, text=bidi_text("התחלה (0-23):")).grid(row=0, column=3, padx=5, sticky="e")
        self.start_var = tk.StringVar()
        ttk.Entry(control_frame, textvariable=self.start_var, width=5, justify="right").grid(row=0, column=2, padx=5)

        ttk.Label(control_frame, text=bidi_text("סיום (0-24):")).grid(row=0, column=1, padx=5, sticky="e")
        self.end_var = tk.StringVar()
        ttk.Entry(control_frame, textvariable=self.end_var, width=5, justify="right").grid(row=0, column=0, padx=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text=bidi_text("הוסף"), command=self._add_window).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("הסר נבחרים"), command=self._remove_window).pack(side=tk.RIGHT, padx=5)

        # Bottom buttons
        ttk.Button(btn_frame, text=bidi_text("שמור וסגור"), command=self._save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        for w in self.windows:
            day_str = days[w.day] if 0 <= w.day < 7 else str(w.day)
            # Insert values matching column order: End, Start, Day
            self.tree.insert("", tk.END, values=(f"{w.end_hour:02d}:00", f"{w.start_hour:02d}:00", bidi_text(day_str)))

    def _add_window(self):
        try:
            day_str = self.day_var.get()
            
            raw_days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
            days_display = [bidi_text(d) for d in raw_days]
            all_week_display = bidi_text("כל השבוע")
            
            start_val = self.start_var.get()
            end_val = self.end_var.get()
            
            if not start_val or not end_val:
                raise ValueError(bidi_text("יש למלא שעות התחלה וסיום"))

            start = int(start_val)
            end = int(end_val)

            if not (0 <= start < 24): raise ValueError(bidi_text("שעת התחלה חייבת להיות בין 0 ל-23"))
            if not (0 <= end <= 24): raise ValueError(bidi_text("שעת סיום חייבת להיות בין 0 ל-24"))
            if start >= end: raise ValueError(bidi_text("שעת התחלה חייבת להיות קטנה משעת סיום"))

            # Check if "All Week" is selected
            if day_str == all_week_display:
                # Add for all days 0-6
                for d in range(7):
                    self.windows.append(TimeWindow(d, start, end))
            elif day_str in days_display:
                # Add for specific day
                day = days_display.index(day_str)
                self.windows.append(TimeWindow(day, start, end))
            else:
                 raise ValueError(bidi_text("יש לבחור יום מהרשימה"))

            self._refresh_list()
            
            self.day_var.set("")
            self.start_var.set("")
            self.end_var.set("")

        except ValueError as e:
            messagebox.showerror(bidi_text("שגיאה"), str(e))

    def _remove_window(self):
        selection = self.tree.selection()
        if selection:
            # Get index of selected item
            all_items = self.tree.get_children()
            selected_item = selection[0]
            index = all_items.index(selected_item)
            
            del self.windows[index]
            self._refresh_list()

    def _save(self):
        self.on_save(self.windows)
        self.destroy()


class GroupCreationDialog(tk.Toplevel):
    def __init__(self, parent, on_create: Callable[[Group], None]):
        super().__init__(parent)
        self.title(bidi_text("יצירת קבוצה חדשה"))
        self.geometry("400x300")
        self.on_create = on_create
        
        self._create_ui()

    def _create_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Name
        ttk.Label(main_frame, text=bidi_text("שם הקבוצה:")).pack(anchor=tk.E, pady=(0, 5))
        self.name_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.name_var, justify="right").pack(fill=tk.X, pady=(0, 15))
        
        # Constraint Type Selection
        ttk.Label(main_frame, text=bidi_text("בחר סוג אילוץ (חובה לבחור אחד):")).pack(anchor=tk.E, pady=(0, 5))
        
        self.constraint_type = tk.StringVar(value="staffing")
        
        rb_frame = ttk.Frame(main_frame)
        rb_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Radiobutton(rb_frame, text=bidi_text("סד\"כ (לחלוקה יחסית)"), variable=self.constraint_type, value="staffing", command=self._toggle_inputs).pack(anchor=tk.E)
        ttk.Radiobutton(rb_frame, text=bidi_text("מכסה שבועית קשיחה"), variable=self.constraint_type, value="quota", command=self._toggle_inputs).pack(anchor=tk.E)
        
        # Input fields
        self.input_frame = ttk.Frame(main_frame)
        self.input_frame.pack(fill=tk.X, pady=10)
        
        self.value_label = ttk.Label(self.input_frame, text=bidi_text("גודל סד\"כ:"))
        self.value_label.pack(anchor=tk.E)
        
        self.value_var = tk.StringVar()
        self.value_entry = ttk.Entry(self.input_frame, textvariable=self.value_var, justify="right")
        self.value_entry.pack(fill=tk.X)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text=bidi_text("צור קבוצה"), command=self._create).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self._toggle_inputs()

    def _toggle_inputs(self):
        if self.constraint_type.get() == "staffing":
            self.value_label.config(text=bidi_text("גודל סד\"כ:"))
        else:
            self.value_label.config(text=bidi_text("כמות משמרות שבועית:"))

    def _create(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror(bidi_text("שגיאה"), bidi_text("יש להזין שם קבוצה"))
            return
            
        try:
            val = int(self.value_var.get())
            if val < 0: raise ValueError
        except ValueError:
            messagebox.showerror(bidi_text("שגיאה"), bidi_text("יש להזין מספר שלם חיובי"))
            return

        group = Group(id="", name=name) # ID will be assigned by controller
        
        if self.constraint_type.get() == "staffing":
            group.staffing_size = val
            group.weekly_guard_quota = None
        else:
            group.staffing_size = None
            group.weekly_guard_quota = val
            
        self.on_create(group)
        self.destroy()

class GenerationSettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_generate: Callable[[Optional[ScheduleRange]], None]):
        super().__init__(parent)
        self.title(bidi_text("הגדרות יצירת סידור"))
        self.geometry("400x350")
        self.on_generate = on_generate
        
        self._create_ui()

    def _create_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Mode Selection
        self.mode_var = tk.StringVar(value="full")
        ttk.Radiobutton(main_frame, text=bidi_text("שבוע מלא (ראשון-שבת)"), variable=self.mode_var, value="full", command=self._toggle_range).pack(anchor=tk.E, pady=5)
        ttk.Radiobutton(main_frame, text=bidi_text("טווח חלקי"), variable=self.mode_var, value="partial", command=self._toggle_range).pack(anchor=tk.E, pady=5)
        
        # Range Selection Frame
        self.range_frame = ttk.LabelFrame(main_frame, text=bidi_text("בחירת טווח"), padding=10)
        self.range_frame.pack(fill=tk.X, pady=10)
        
        days = [bidi_text(d) for d in ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]]
        hours = [f"{h:02d}:00" for h in range(24)]
        
        # Start
        ttk.Label(self.range_frame, text=bidi_text("התחלה:")).grid(row=0, column=2, sticky=tk.E, pady=5)
        self.start_day_combo = ttk.Combobox(self.range_frame, values=days, width=10, justify="right", state="readonly")
        self.start_day_combo.grid(row=0, column=1, padx=5)
        self.start_day_combo.current(0)
        
        self.start_hour_combo = ttk.Combobox(self.range_frame, values=hours, width=8, justify="right", state="readonly")
        self.start_hour_combo.grid(row=0, column=0, padx=5)
        self.start_hour_combo.current(0)
        
        # End
        ttk.Label(self.range_frame, text=bidi_text("סיום:")).grid(row=1, column=2, sticky=tk.E, pady=5)
        self.end_day_combo = ttk.Combobox(self.range_frame, values=days, width=10, justify="right", state="readonly")
        self.end_day_combo.grid(row=1, column=1, padx=5)
        self.end_day_combo.current(6)
        
        self.end_hour_combo = ttk.Combobox(self.range_frame, values=hours, width=8, justify="right", state="readonly")
        self.end_hour_combo.grid(row=1, column=0, padx=5)
        self.end_hour_combo.current(23)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text=bidi_text("צור סידור"), command=self._generate).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self._toggle_range()

    def _toggle_range(self):
        if self.mode_var.get() == "partial":
            for child in self.range_frame.winfo_children():
                child.configure(state="normal")
        else:
            for child in self.range_frame.winfo_children():
                child.configure(state="disabled")

    def _generate(self):
        if self.mode_var.get() == "full":
            self.on_generate(None)
        else:
            days_display = [bidi_text(d) for d in ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]]
            
            start_day = days_display.index(self.start_day_combo.get())
            start_hour = int(self.start_hour_combo.get().split(":")[0])
            
            end_day = days_display.index(self.end_day_combo.get())
            end_hour = int(self.end_hour_combo.get().split(":")[0])
            
            # Validate
            start_linear = start_day * 24 + start_hour
            end_linear = end_day * 24 + end_hour
            
            if end_linear <= start_linear:
                messagebox.showerror(bidi_text("שגיאה"), bidi_text("זמן הסיום חייב להיות מאוחר מזמן ההתחלה"))
                return
                
            self.on_generate(ScheduleRange(start_day, start_hour, end_day, end_hour))

        self.destroy()
