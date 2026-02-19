import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Callable, Optional, Tuple, Set
from datetime import datetime, date, timedelta
import calendar
from shmirot_gdud.core.models import TimeWindow, Group, ScheduleRange, DateConstraint
from shmirot_gdud.gui.utils import bidi_text

# Set calendar to start on Sunday
calendar.setfirstweekday(calendar.SUNDAY)

class CalendarWidget(ttk.Frame):
    def __init__(self, parent, on_selection_change=None):
        super().__init__(parent)
        self.on_selection_change = on_selection_change
        self.selected_dates: Set[str] = set() # "YYYY-MM-DD"
        self.current_date = date.today()
        self.display_year = self.current_date.year
        self.display_month = self.current_date.month
        
        self._create_ui()
        self._refresh_calendar()

    def _create_ui(self):
        # Header
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=5)
        
        ttk.Button(header, text="<", width=3, command=self._prev_month).pack(side=tk.LEFT)
        self.month_label = ttk.Label(header, text="", font=("Arial", 10, "bold"), width=15, anchor="center")
        self.month_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(header, text=">", width=3, command=self._next_month).pack(side=tk.LEFT)
        
        # Days grid
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # RTL: Sunday (Rightmost) -> Saturday (Leftmost)
        # Grid columns: 6=Sun, 5=Mon, ..., 0=Sat
        days = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]
        for i, d in enumerate(days):
            # i=0 is Sun, i=6 is Sat
            # We want Sun at col 6, Sat at col 0
            col = 6 - i
            ttk.Label(self.grid_frame, text=d, width=4, anchor="center").grid(row=0, column=col, padx=1, pady=1)

    def _refresh_calendar(self):
        self.month_label.config(text=f"{self.display_month}/{self.display_year}")
        
        # Clear existing buttons
        for widget in self.grid_frame.winfo_children():
            if int(widget.grid_info()["row"]) > 0:
                widget.destroy()
                
        # Get month days
        # Since we set firstweekday to SUNDAY, monthcalendar returns weeks starting on Sunday
        # week[0] is Sunday, week[6] is Saturday
        cal = calendar.monthcalendar(self.display_year, self.display_month)
        
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                # c=0 is Sunday, c=6 is Saturday
                # We want RTL display: Sun at col 6, Sat at col 0
                grid_col = 6 - c
                
                if day != 0:
                    date_str = f"{self.display_year}-{self.display_month:02d}-{day:02d}"
                    
                    bg_color = "white"
                    if date_str in self.selected_dates:
                        bg_color = "#aaddff"
                    
                    btn = tk.Button(self.grid_frame, text=str(day), width=3, 
                                    bg=bg_color,
                                    command=lambda d=date_str: self._toggle_date(d))
                    btn.grid(row=r+1, column=grid_col, padx=1, pady=1)

    def _toggle_date(self, date_str):
        if date_str in self.selected_dates:
            self.selected_dates.remove(date_str)
        else:
            self.selected_dates.add(date_str)
        
        self._refresh_calendar()
        if self.on_selection_change:
            self.on_selection_change()

    def _prev_month(self):
        self.display_month -= 1
        if self.display_month < 1:
            self.display_month = 12
            self.display_year -= 1
        self._refresh_calendar()

    def _next_month(self):
        self.display_month += 1
        if self.display_month > 12:
            self.display_month = 1
            self.display_year += 1
        self._refresh_calendar()
        
    def get_selection(self) -> List[str]:
        return sorted(list(self.selected_dates))
    
    def clear_selection(self):
        self.selected_dates.clear()
        self._refresh_calendar()

class DateConstraintDialog(tk.Toplevel):
    def __init__(self, parent, title: str, constraints: List[DateConstraint], on_save: Callable[[List[DateConstraint]], None]):
        super().__init__(parent)
        self.title(bidi_text(title))
        self.geometry("900x600")
        self.constraints = [c for c in constraints] # Copy
        self.on_save = on_save

        self._create_ui()

    def _create_ui(self):
        # Main Layout: Left (List), Right (Editor)
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left: List of existing constraints
        left_frame = ttk.LabelFrame(main_paned, text=bidi_text("אילוצים קיימים"))
        main_paned.add(left_frame, weight=1)
        
        self.tree = ttk.Treeview(left_frame, columns=("Type", "Hours", "Date"), show="headings")
        self.tree.heading("Type", text=bidi_text("סוג"))
        self.tree.heading("Hours", text=bidi_text("שעות"))
        self.tree.heading("Date", text=bidi_text("תאריך"))
        
        self.tree.column("Type", width=60, anchor="center")
        self.tree.column("Hours", width=80, anchor="center")
        self.tree.column("Date", width=100, anchor="center")
        
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Button(left_frame, text=bidi_text("מחק נבחר"), command=self._delete_constraint).pack(fill=tk.X, padx=5, pady=5)
        
        # Right: Editor
        right_frame = ttk.LabelFrame(main_paned, text=bidi_text("הוספת/עריכת אילוץ"))
        main_paned.add(right_frame, weight=2)
        
        # Calendar
        ttk.Label(right_frame, text=bidi_text("בחר תאריכים:")).pack(anchor=tk.E, padx=5)
        self.calendar = CalendarWidget(right_frame)
        self.calendar.pack(padx=5, pady=5)
        
        # Settings
        settings_frame = ttk.Frame(right_frame)
        settings_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Type
        self.type_var = tk.BooleanVar(value=False) # False = Not Available, True = Available
        ttk.Radiobutton(settings_frame, text=bidi_text("לא זמין (חסימה)"), variable=self.type_var, value=False).pack(anchor=tk.E)
        ttk.Radiobutton(settings_frame, text=bidi_text("זמין (רק בשעות אלו)"), variable=self.type_var, value=True).pack(anchor=tk.E)
        
        # Hours
        hours_frame = ttk.Frame(right_frame)
        hours_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(hours_frame, text=bidi_text("עד שעה:")).pack(side=tk.RIGHT, padx=5)
        self.end_var = tk.StringVar(value="24")
        ttk.Entry(hours_frame, textvariable=self.end_var, width=5).pack(side=tk.RIGHT)
        
        ttk.Label(hours_frame, text=bidi_text("משעה:")).pack(side=tk.RIGHT, padx=5)
        self.start_var = tk.StringVar(value="0")
        ttk.Entry(hours_frame, textvariable=self.start_var, width=5).pack(side=tk.RIGHT)
        
        # Add Button
        ttk.Button(right_frame, text=bidi_text("הוסף אילוץ"), command=self._add_constraint).pack(fill=tk.X, padx=20, pady=20)
        
        # Bottom Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text=bidi_text("שמור וסגור"), command=self._save).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)

        self._refresh_list()

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Sort by date
        sorted_constraints = sorted(self.constraints, key=lambda c: c.dates[0] if c.dates else "")
        
        for c in sorted_constraints:
            type_str = "זמין" if c.is_available else "לא זמין"
            hours_str = f"{c.start_hour:02d}:00 - {c.end_hour:02d}:00"
            
            # Since we split constraints, each should have exactly one date
            if c.dates:
                date_str = c.dates[0]
                # Format to DD/MM/YYYY
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    date_display = dt.strftime("%d/%m/%Y")
                except:
                    date_display = date_str
            else:
                date_display = "???"
                
            self.tree.insert("", tk.END, values=(bidi_text(type_str), hours_str, date_display))

    def _add_constraint(self):
        dates = self.calendar.get_selection()
        if not dates:
            messagebox.showwarning(bidi_text("שגיאה"), bidi_text("יש לבחור לפחות תאריך אחד"))
            return
            
        try:
            start = int(self.start_var.get())
            end = int(self.end_var.get())
            
            if not (0 <= start < 24): raise ValueError
            if not (0 <= end <= 24): raise ValueError
            if start >= end: raise ValueError
            
        except ValueError:
            messagebox.showerror(bidi_text("שגיאה"), bidi_text("שעות לא תקינות"))
            return

        is_avail = self.type_var.get()
        
        # Check conflicts and add individually
        for date_str in dates:
            # Check conflict for this specific date
            for c in self.constraints:
                if date_str in c.dates:
                    # Check hour overlap
                    if max(c.start_hour, start) < min(c.end_hour, end):
                        # Overlap exists
                        if c.is_available != is_avail:
                            messagebox.showerror(bidi_text("התנגשות"), bidi_text(f"קיימת התנגשות בתאריך {date_str}"))
                            return
            
            # Create separate constraint for each date
            new_constraint = DateConstraint([date_str], start, end, is_avail)
            self.constraints.append(new_constraint)
            
        self._refresh_list()
        self.calendar.clear_selection()

    def _delete_constraint(self):
        selection = self.tree.selection()
        if selection:
            # We need to find the correct index in the original list
            # The tree is sorted, so index might not match
            item = selection[0]
            values = self.tree.item(item, "values")
            
            # Reconstruct to find match
            # values = (Type, Hours, Date)
            # We need to be careful with bidi text reversal when matching
            
            # Simpler way: keep a map or just iterate and match properties
            # Since we refresh list from sorted_constraints, let's use the same sort logic to find index
            sorted_constraints = sorted(self.constraints, key=lambda c: c.dates[0] if c.dates else "")
            index_in_sorted = self.tree.index(item)
            
            if 0 <= index_in_sorted < len(sorted_constraints):
                target = sorted_constraints[index_in_sorted]
                self.constraints.remove(target)
                self._refresh_list()

    def _save(self):
        self.on_save(self.constraints)
        self.destroy()

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

class DateRangeDialog(tk.Toplevel):
    def __init__(self, parent, on_confirm: Callable[[str, str], None]):
        super().__init__(parent)
        self.title(bidi_text("בחירת טווח תאריכים"))
        self.geometry("400x300")
        self.on_confirm = on_confirm
        
        self._create_ui()

    def _create_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        today = date.today()
        
        # Start Date
        ttk.Label(main_frame, text=bidi_text("תאריך התחלה:")).pack(anchor=tk.E, pady=(0, 5))
        self.start_frame = self._create_date_picker(main_frame, today)
        self.start_frame.pack(fill=tk.X, pady=(0, 15))
        
        # End Date
        ttk.Label(main_frame, text=bidi_text("תאריך סיום:")).pack(anchor=tk.E, pady=(0, 5))
        self.end_frame = self._create_date_picker(main_frame, today)
        self.end_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text=bidi_text("צור טבלה ריקה"), command=self._confirm).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _create_date_picker(self, parent, default_date):
        frame = ttk.Frame(parent)
        
        # Year
        year_var = tk.StringVar(value=str(default_date.year))
        years = [str(y) for y in range(default_date.year - 1, default_date.year + 5)]
        ttk.Combobox(frame, textvariable=year_var, values=years, width=6, state="readonly").pack(side=tk.LEFT, padx=2)
        
        # Month
        month_var = tk.StringVar(value=f"{default_date.month:02d}")
        months = [f"{m:02d}" for m in range(1, 13)]
        ttk.Combobox(frame, textvariable=month_var, values=months, width=4, state="readonly").pack(side=tk.LEFT, padx=2)
        
        # Day
        day_var = tk.StringVar(value=f"{default_date.day:02d}")
        days = [f"{d:02d}" for d in range(1, 32)]
        ttk.Combobox(frame, textvariable=day_var, values=days, width=4, state="readonly").pack(side=tk.LEFT, padx=2)
        
        frame.vars = (year_var, month_var, day_var)
        return frame

    def _get_date(self, frame):
        y, m, d = frame.vars
        return f"{y.get()}-{m.get()}-{d.get()}"

    def _confirm(self):
        start_str = self._get_date(self.start_frame)
        end_str = self._get_date(self.end_frame)
        
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d")
            end = datetime.strptime(end_str, "%Y-%m-%d")
            
            if end < start:
                messagebox.showerror(bidi_text("שגיאה"), bidi_text("תאריך סיום חייב להיות אחרי תאריך התחלה"))
                return
                
            self.on_confirm(start_str, end_str)
            self.destroy()
            
        except ValueError:
            messagebox.showerror(bidi_text("שגיאה"), bidi_text("תאריך לא תקין"))

class ImprovementSettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_confirm: Callable[[int, int], None]):
        super().__init__(parent)
        self.title(bidi_text("הגדרות שיפור סידור"))
        self.geometry("400x250")
        self.on_confirm = on_confirm
        
        self._create_ui()

    def _create_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text=bidi_text("הגדרת שעות קשות (לילה)"), font=("Arial", 12, "bold")).pack(pady=10)
        
        hours_frame = ttk.Frame(main_frame)
        hours_frame.pack(pady=10)
        
        ttk.Label(hours_frame, text=bidi_text("עד שעה:")).pack(side=tk.RIGHT, padx=5)
        self.end_var = tk.StringVar(value="6")
        ttk.Entry(hours_frame, textvariable=self.end_var, width=5).pack(side=tk.RIGHT)
        
        ttk.Label(hours_frame, text=bidi_text("משעה:")).pack(side=tk.RIGHT, padx=5)
        self.start_var = tk.StringVar(value="2")
        ttk.Entry(hours_frame, textvariable=self.start_var, width=5).pack(side=tk.RIGHT)
        
        ttk.Label(main_frame, text=bidi_text("האלגוריתם ינסה לאזן את השעות הללו בין הקבוצות")).pack(pady=5)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text=bidi_text("התחל שיפור"), command=self._confirm).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=bidi_text("ביטול"), command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _confirm(self):
        try:
            start = int(self.start_var.get())
            end = int(self.end_var.get())
            
            if not (0 <= start < 24): raise ValueError
            if not (0 <= end <= 24): raise ValueError
            
            self.on_confirm(start, end)
            self.destroy()
            
        except ValueError:
            messagebox.showerror(bidi_text("שגיאה"), bidi_text("שעות לא תקינות"))
