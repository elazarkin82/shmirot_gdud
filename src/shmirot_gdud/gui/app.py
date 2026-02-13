import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from typing import List, Dict, Optional
import pandas as pd

from shmirot_gdud.core.models import Group, TimeWindow, WeeklySchedule
from shmirot_gdud.core.scheduler import Scheduler
from shmirot_gdud.gui.dialogs import TimeWindowDialog, GroupCreationDialog
from shmirot_gdud.gui.schedule_grid import ScheduleGrid

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("מערכת שיבוץ שמירות גדודית")
        self.root.geometry("1200x800")

        self.groups: List[Group] = []
        self.schedule: Optional[WeeklySchedule] = None

        self._create_menu()
        self._show_main_menu() # Start with main menu

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="טען קבוצות", command=self._load_groups)
        file_menu.add_command(label="שמור קבוצות", command=self._save_groups)
        file_menu.add_separator()
        file_menu.add_command(label="ייצוא לאקסל", command=self._export_excel)
        file_menu.add_separator()
        file_menu.add_command(label="יציאה", command=self.root.quit)
        menubar.add_cascade(label="קובץ", menu=file_menu)
        
        nav_menu = tk.Menu(menubar, tearoff=0)
        nav_menu.add_command(label="תפריט ראשי", command=self._show_main_menu)
        nav_menu.add_command(label="ניהול קבוצות", command=self._show_group_management)
        nav_menu.add_command(label="לוח שיבוץ", command=self._show_schedule)
        menubar.add_cascade(label="ניווט", menu=nav_menu)
        
        self.root.config(menu=menubar)

    def _clear_window(self):
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Menu): continue
            widget.destroy()

    def _show_main_menu(self):
        self._clear_window()
        
        frame = ttk.Frame(self.root, padding=50)
        frame.pack(expand=True)
        
        ttk.Label(frame, text="מערכת שיבוץ שמירות", font=("Arial", 24, "bold")).pack(pady=30)
        
        btn_width = 25
        ttk.Button(frame, text="יצירת קבוצה חדשה", width=btn_width, command=self._open_create_group_dialog).pack(pady=10)
        ttk.Button(frame, text="ניהול קבוצות", width=btn_width, command=self._show_group_management).pack(pady=10)
        ttk.Button(frame, text="יצירת/צפייה בלוח שיבוץ", width=btn_width, command=self._show_schedule).pack(pady=10)
        ttk.Button(frame, text="שמירת נתונים", width=btn_width, command=self._save_groups).pack(pady=10)
        ttk.Button(frame, text="טעינת נתונים", width=btn_width, command=self._load_groups).pack(pady=10)

    def _open_create_group_dialog(self):
        def on_create(group: Group):
            group.id = str(len(self.groups) + 1) # Simple ID generation
            self.groups.append(group)
            messagebox.showinfo("הצלחה", f"הקבוצה {group.name} נוצרה בהצלחה")
            
        GroupCreationDialog(self.root, on_create)

    def _show_group_management(self):
        self._clear_window()
        
        # Main container
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # Right panel: Group List (Hebrew UI implies RTL, but Tkinter is LTR by default. 
        # We'll put the list on the right for RTL feel or keep standard layout but translate text)
        # Let's stick to standard layout but maybe swap sides if we want true RTL feel.
        # For simplicity, let's keep list on left but align text right.
        
        # Left panel: Group List
        left_frame = ttk.Frame(main_paned, width=300)
        main_paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="רשימת קבוצות", font=("Arial", 14, "bold")).pack(pady=5)
        
        self.group_listbox = tk.Listbox(left_frame, height=20, justify="right")
        self.group_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.group_listbox.bind('<<ListboxSelect>>', self._on_group_select)
        
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="הוסף קבוצה", command=self._open_create_group_dialog_refresh).pack(side=tk.RIGHT, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="מחק קבוצה", command=self._delete_group).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Right panel: Details
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=3)
        
        self.details_frame = ttk.LabelFrame(right_frame, text="פרטי קבוצה")
        self.details_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Basic Info
        info_frame = ttk.Frame(self.details_frame)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Grid layout for RTL
        ttk.Label(info_frame, text="שם הקבוצה:").grid(row=0, column=2, sticky=tk.E, padx=5)
        self.name_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.name_var, justify="right").grid(row=0, column=1, sticky=tk.EW)
        
        ttk.Label(info_frame, text="גודל סד\"כ:").grid(row=1, column=2, sticky=tk.E, padx=5)
        self.staffing_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.staffing_var, justify="right").grid(row=1, column=1, sticky=tk.EW)
        
        ttk.Label(info_frame, text="מכסה שבועית (קשיח):").grid(row=2, column=2, sticky=tk.E, padx=5)
        self.quota_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.quota_var, justify="right").grid(row=2, column=1, sticky=tk.EW)
        
        info_frame.columnconfigure(1, weight=1)

        # Constraints List
        ttk.Label(self.details_frame, text="חוקי אי-זמינות:").pack(anchor=tk.E, padx=5, pady=(10, 0))
        self.constraints_list = tk.Listbox(self.details_frame, height=5, justify="right")
        self.constraints_list.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(self.details_frame, text="ניהול אי-זמינות", command=self._manage_unavailability).pack(fill=tk.X, padx=5, pady=2)

        # Activity Windows List
        ttk.Label(self.details_frame, text="חלונות פעילות עיקרית:").pack(anchor=tk.E, padx=5, pady=(10, 0))
        self.activity_list = tk.Listbox(self.details_frame, height=5, justify="right")
        self.activity_list.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(self.details_frame, text="ניהול חלונות פעילות", command=self._manage_activity).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(self.details_frame, text="שמור שינויים", command=self._save_group_details).pack(fill=tk.X, padx=5, pady=20)

        self._refresh_group_list()

    def _open_create_group_dialog_refresh(self):
        def on_create(group: Group):
            group.id = str(len(self.groups) + 1)
            self.groups.append(group)
            self._refresh_group_list()
            
        GroupCreationDialog(self.root, on_create)

    def _show_schedule(self):
        self._clear_window()
        
        # Top controls
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        
        ttk.Button(top_frame, text="חזור לתפריט ראשי", command=self._show_main_menu).pack(side=tk.RIGHT)
        ttk.Button(top_frame, text="צור סידור עבודה", command=self._generate_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="ייצוא לאקסל", command=self._export_excel).pack(side=tk.LEFT, padx=5)

        # Schedule Grid
        grid_frame = ttk.Frame(self.root)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.schedule_grid = ScheduleGrid(grid_frame, self.groups, self._on_schedule_change, bg="white")
        
        h_scroll = ttk.Scrollbar(grid_frame, orient=tk.HORIZONTAL, command=self.schedule_grid.xview)
        v_scroll = ttk.Scrollbar(grid_frame, orient=tk.VERTICAL, command=self.schedule_grid.yview)
        
        self.schedule_grid.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.schedule_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        if self.schedule:
            self.schedule_grid.set_schedule(self.schedule)

    def _delete_group(self):
        selection = self.group_listbox.curselection()
        if selection:
            if messagebox.askyesno("אישור מחיקה", "האם אתה בטוח שברצונך למחוק את הקבוצה?"):
                idx = selection[0]
                del self.groups[idx]
                self._refresh_group_list()
                self._clear_details()

    def _refresh_group_list(self):
        if not hasattr(self, 'group_listbox'): return
        self.group_listbox.delete(0, tk.END)
        for g in self.groups:
            self.group_listbox.insert(tk.END, g.name)

    def _on_group_select(self, event):
        selection = self.group_listbox.curselection()
        if selection:
            idx = selection[0]
            group = self.groups[idx]
            self.name_var.set(group.name)
            self.staffing_var.set(str(group.staffing_size) if group.staffing_size is not None else "")
            self.quota_var.set(str(group.weekly_guard_quota) if group.weekly_guard_quota is not None else "")
            
            self._refresh_constraints_list(group)
            self._refresh_activity_list(group)

    def _refresh_constraints_list(self, group: Group):
        self.constraints_list.delete(0, tk.END)
        days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        for c in group.hard_unavailability_rules:
            day_str = days[c.day] if 0 <= c.day < 7 else str(c.day)
            self.constraints_list.insert(tk.END, f"{day_str} {c.start_hour:02d}:00 - {c.end_hour:02d}:00")

    def _refresh_activity_list(self, group: Group):
        self.activity_list.delete(0, tk.END)
        days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        for w in group.primary_activity_windows:
            day_str = days[w.day] if 0 <= w.day < 7 else str(w.day)
            self.activity_list.insert(tk.END, f"{day_str} {w.start_hour:02d}:00 - {w.end_hour:02d}:00")

    def _save_group_details(self):
        selection = self.group_listbox.curselection()
        if selection:
            idx = selection[0]
            group = self.groups[idx]
            group.name = self.name_var.get()
            
            try:
                s_size = self.staffing_var.get()
                group.staffing_size = int(s_size) if s_size else None
            except ValueError:
                messagebox.showerror("שגיאה", "גודל סד\"כ חייב להיות מספר שלם")
                return

            try:
                quota = self.quota_var.get()
                group.weekly_guard_quota = int(quota) if quota else None
            except ValueError:
                messagebox.showerror("שגיאה", "מכסה שבועית חייבת להיות מספר שלם")
                return

            if not group.validate():
                messagebox.showwarning("אזהרה", "לקבוצה חייב להיות מוגדר סד\"כ או מכסה שבועית")
            
            self._refresh_group_list()
            self.group_listbox.selection_set(idx)
            messagebox.showinfo("הצלחה", "השינויים נשמרו")

    def _manage_unavailability(self):
        selection = self.group_listbox.curselection()
        if selection:
            idx = selection[0]
            group = self.groups[idx]
            
            def on_save(constraints):
                group.hard_unavailability_rules = constraints
                self._refresh_constraints_list(group)
            
            TimeWindowDialog(self.root, f"אי-זמינות עבור {group.name}", group.hard_unavailability_rules, on_save)

    def _manage_activity(self):
        selection = self.group_listbox.curselection()
        if selection:
            idx = selection[0]
            group = self.groups[idx]
            
            def on_save(windows):
                group.primary_activity_windows = windows
                self._refresh_activity_list(group)
            
            TimeWindowDialog(self.root, f"חלונות פעילות עבור {group.name}", group.primary_activity_windows, on_save)

    def _clear_details(self):
        self.name_var.set("")
        self.staffing_var.set("")
        self.quota_var.set("")
        self.constraints_list.delete(0, tk.END)
        self.activity_list.delete(0, tk.END)

    def _generate_schedule(self):
        if not self.groups:
            messagebox.showwarning("אזהרה", "אין קבוצות מוגדרות")
            return

        scheduler = Scheduler(self.groups)
        self.schedule = scheduler.generate_schedule()
        
        self._validate_and_show_errors()
        if hasattr(self, 'schedule_grid'):
            self.schedule_grid.set_schedule(self.schedule)
        else:
            self._show_schedule()

    def _on_schedule_change(self):
        self._validate_and_show_errors()

    def _validate_and_show_errors(self):
        if not self.schedule: return
        scheduler = Scheduler(self.groups)
        scheduler.schedule = self.schedule
        errors = scheduler.validate_schedule()
        
        if errors:
             msg = "\n".join(errors[:10])
             if len(errors) > 10:
                 msg += "\n..."
             messagebox.showwarning("בעיות בסידור", msg)

    def _save_groups(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filename:
            data = [g.to_dict() for g in self.groups]
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("הצלחה", "הקבוצות נשמרו בהצלחה")

    def _load_groups(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                self.groups = []
                for d in data:
                    self.groups.append(Group.from_dict(d))
                
                messagebox.showinfo("הצלחה", "הקבוצות נטענו בהצלחה")
                
                # If we are in group management screen, refresh
                if hasattr(self, 'group_listbox'):
                    self._refresh_group_list()
                    self._clear_details()
                    
            except Exception as e:
                messagebox.showerror("שגיאה", f"נכשל בטעינת הקבוצות: {e}")

    def _export_excel(self):
        if not self.schedule:
            messagebox.showwarning("אזהרה", "יש לייצר סידור עבודה תחילה")
            return
            
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if filename:
            schedule_data = []
            days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
            
            slot_map = {}
            for slot in self.schedule.slots:
                slot_map[(slot.day, slot.hour, slot.position)] = slot.group_id

            for hour in range(24):
                row = {"שעה": f"{hour:02d}:00 - {hour+1:02d}:00"}
                for day_idx, day_name in enumerate(days):
                    g1_id = slot_map.get((day_idx, hour, 1))
                    g2_id = slot_map.get((day_idx, hour, 2))
                    
                    g1_name = next((g.name for g in self.groups if g.id == g1_id), "")
                    g2_name = next((g.name for g in self.groups if g.id == g2_id), "")
                    
                    row[f"{day_name} עמדה 1"] = g1_name
                    row[f"{day_name} עמדה 2"] = g2_name
                schedule_data.append(row)

            df_schedule = pd.DataFrame(schedule_data)
            
            groups_data = []
            for g in self.groups:
                groups_data.append({
                    "שם": g.name,
                    "סד\"כ": g.staffing_size,
                    "מכסה שבועית": g.weekly_guard_quota,
                    "אי-זמינות": "; ".join([f"יום {r.day} {r.start_hour}-{r.end_hour}" for r in g.hard_unavailability_rules]),
                    "חלונות פעילות": "; ".join([f"יום {r.day} {r.start_hour}-{r.end_hour}" for r in g.primary_activity_windows])
                })
            df_groups = pd.DataFrame(groups_data)

            with pd.ExcelWriter(filename) as writer:
                df_schedule.to_excel(writer, sheet_name='לוח שיבוץ', index=False)
                df_groups.to_excel(writer, sheet_name='קבוצות', index=False)
            
            messagebox.showinfo("הצלחה", "הייצוא הושלם בהצלחה")

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()
