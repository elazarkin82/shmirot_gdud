import tkinter as tk
from typing import Optional, Tuple, Callable, List, Dict
from shmirot_gdud.core.models import WeeklySchedule, Group

class ScheduleGrid(tk.Canvas):
    def __init__(self, parent, groups: List[Group], on_change: Callable[[], None], **kwargs):
        super().__init__(parent, **kwargs)
        self.groups = groups
        self.on_change = on_change
        self.schedule: Optional[WeeklySchedule] = None
        
        self.cell_width = 100
        self.cell_height = 40
        self.header_height = 30
        self.sidebar_width = 60
        
        self.days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        
        # Drag state
        self.drag_start_slot: Optional[Tuple[int, int, int]] = None # day, hour, pos
        self.drag_item_id = None
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_schedule(self, schedule: WeeklySchedule):
        self.schedule = schedule
        self.redraw()

    def refresh_groups(self, groups: List[Group]):
        self.groups = groups
        self.redraw()

    def redraw(self):
        self.delete("all")
        
        if not self.schedule:
            self.create_text(self.winfo_width()//2, self.winfo_height()//2, text="לא נוצר סידור עבודה")
            return

        # Draw Headers (RTL: Sunday on right)
        # Actually, standard calendar view usually puts Sunday on left even in Israel, 
        # but let's stick to LTR grid for simplicity unless specifically requested RTL grid logic which is complex to draw.
        # Wait, user asked for Hebrew. Let's keep LTR grid structure but with Hebrew labels for now to avoid confusion,
        # as "Sunday" is usually column 0.

        for d, day in enumerate(self.days):
            x = self.sidebar_width + d * self.cell_width
            self.create_text(x + self.cell_width//2, self.header_height//2, text=day)
            
        # Draw Sidebar (Hours)
        for h in range(24):
            y = self.header_height + h * self.cell_height
            self.create_text(self.sidebar_width//2, y + self.cell_height//2, text=f"{h:02d}:00")

        # Draw Grid
        slot_map = {}
        for slot in self.schedule.slots:
            slot_map[(slot.day, slot.hour, slot.position)] = slot.group_id

        for d in range(7):
            for h in range(24):
                x = self.sidebar_width + d * self.cell_width
                y = self.header_height + h * self.cell_height
                
                # Draw cell border
                self.create_rectangle(x, y, x + self.cell_width, y + self.cell_height, outline="gray")
                
                # Position 1 (Top half)
                g1_id = slot_map.get((d, h, 1))
                g1_name = self._get_group_name(g1_id)
                self._draw_slot(x, y, self.cell_width, self.cell_height//2, g1_name, (d, h, 1))
                
                # Position 2 (Bottom half)
                g2_id = slot_map.get((d, h, 2))
                g2_name = self._get_group_name(g2_id)
                self._draw_slot(x, y + self.cell_height//2, self.cell_width, self.cell_height//2, g2_name, (d, h, 2))

        # Update scroll region
        total_width = self.sidebar_width + 7 * self.cell_width
        total_height = self.header_height + 24 * self.cell_height
        self.config(scrollregion=(0, 0, total_width, total_height))

    def _draw_slot(self, x, y, w, h, text, slot_key):
        # Background
        rect_id = self.create_rectangle(x, y, x+w, y+h, fill="white", outline="lightgray", tags=f"slot_{slot_key}")
        # Text
        text_id = self.create_text(x+w//2, y+h//2, text=text, font=("Arial", 8), tags=f"text_{slot_key}")

    def _get_group_name(self, group_id):
        if not group_id: return ""
        for g in self.groups:
            if g.id == group_id:
                return g.name
        return "?"

    def _get_slot_at(self, x, y) -> Optional[Tuple[int, int, int]]:
        if x < self.sidebar_width or y < self.header_height:
            return None
            
        d = int((x - self.sidebar_width) // self.cell_width)
        h = int((y - self.header_height) // self.cell_height)
        
        if not (0 <= d < 7 and 0 <= h < 24):
            return None
            
        # Check if top or bottom half
        rel_y = (y - self.header_height) % self.cell_height
        pos = 1 if rel_y < self.cell_height // 2 else 2
        
        return (d, h, pos)

    def _on_click(self, event):
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        slot = self._get_slot_at(x, y)
        
        if slot:
            self.drag_start_slot = slot
            # Visual feedback could be added here (highlight)

    def _on_drag(self, event):
        pass # Could implement a floating label here

    def _on_release(self, event):
        if not self.drag_start_slot:
            return
            
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        target_slot = self._get_slot_at(x, y)
        
        if target_slot and target_slot != self.drag_start_slot:
            self._swap_slots(self.drag_start_slot, target_slot)
            
        self.drag_start_slot = None

    def _swap_slots(self, slot1, slot2):
        if not self.schedule: return
        
        s1 = self.schedule.get_slot(*slot1)
        s2 = self.schedule.get_slot(*slot2)
        
        # If slots don't exist in the list (e.g. empty schedule), create them or handle gracefully
        # Our scheduler creates all slots, but let's be safe
        
        id1 = s1.group_id if s1 else None
        id2 = s2.group_id if s2 else None
        
        # Update model
        self.schedule.set_slot(slot1[0], slot1[1], slot1[2], id2)
        self.schedule.set_slot(slot2[0], slot2[1], slot2[2], id1)
        
        self.redraw()
        self.on_change()
