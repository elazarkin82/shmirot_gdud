import tkinter as tk
from typing import Optional, Tuple, Callable, List, Dict
from shmirot_gdud.core.models import WeeklySchedule, Group
from shmirot_gdud.gui.utils import bidi_text

class ScheduleGrid(tk.Canvas):
    def __init__(self, parent, groups: List[Group], on_change: Callable[[], bool], **kwargs):
        super().__init__(parent, **kwargs)
        self.groups = groups
        self.on_change = on_change # Now expects a boolean return value
        self.schedule: Optional[WeeklySchedule] = None
        
        self.cell_width = 140
        self.cell_height = 40
        self.header_height = 30
        self.sidebar_width = 60
        
        self.days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        
        # Drag state
        self.drag_start_slot: Optional[Tuple[int, int, int]] = None # day, hour, pos
        self.drag_ghost_rect = None
        self.drag_ghost_text = None
        
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
            self.create_text(self.winfo_width()//2, self.winfo_height()//2, text=bidi_text("לא נוצר סידור עבודה"))
            return

        grid_width = 7 * self.cell_width
        total_width = grid_width + self.sidebar_width
        total_height = self.header_height + 24 * self.cell_height

        # Draw Sidebar (Hours) - On the Right for RTL
        sidebar_x = grid_width
        
        # Sidebar background
        self.create_rectangle(sidebar_x, 0, total_width, total_height, fill="#f0f0f0", outline="")
        
        for h in range(24):
            y = self.header_height + h * self.cell_height
            self.create_text(sidebar_x + self.sidebar_width//2, y + self.cell_height//2, text=f"{h:02d}:00")

        # Draw Headers
        for d, day in enumerate(self.days):
            # RTL: Sunday (0) is rightmost, Saturday (6) is leftmost
            x = (6 - d) * self.cell_width
            
            # Header background
            self.create_rectangle(x, 0, x + self.cell_width, self.header_height, fill="#e0e0e0", outline="")
            self.create_text(x + self.cell_width//2, self.header_height//2, text=bidi_text(day))

        # Draw Grid Content
        slot_map = {}
        for slot in self.schedule.slots:
            slot_map[(slot.day, slot.hour, slot.position)] = slot.group_id

        for d in range(7):
            for h in range(24):
                x = (6 - d) * self.cell_width
                y = self.header_height + h * self.cell_height
                
                half_width = self.cell_width // 2
                
                # Position 1 (Right half)
                g1_id = slot_map.get((d, h, 1))
                g1_name, g1_color = self._get_group_info(g1_id)
                self._draw_slot(x + half_width, y, half_width, self.cell_height, bidi_text(g1_name), g1_color, (d, h, 1))
                
                # Position 2 (Left half)
                g2_id = slot_map.get((d, h, 2))
                g2_name, g2_color = self._get_group_info(g2_id)
                self._draw_slot(x, y, half_width, self.cell_height, bidi_text(g2_name), g2_color, (d, h, 2))

        # Draw Grid Lines (Overlay for thickness)
        
        # Horizontal lines (Hours) - Across Grid and Sidebar
        for h in range(25): # 0 to 24 inclusive
            y = self.header_height + h * self.cell_height
            self.create_line(0, y, total_width, y, fill="black", width=2)

        # Vertical lines (Days) - Including Sidebar separator
        for d in range(8): # 0 to 7 inclusive
            x = d * self.cell_width
            self.create_line(x, 0, x, total_height, fill="black", width=2)
            
        # Top border line
        self.create_line(0, 0, total_width, 0, fill="black", width=2)

        # Update scroll region
        self.config(scrollregion=(0, 0, total_width, total_height))

    def _draw_slot(self, x, y, w, h, text, color, slot_key):
        # Background
        # Use thinner outline for internal slot separation
        rect_id = self.create_rectangle(x, y, x+w, y+h, fill=color, outline="lightgray", tags=f"slot_{slot_key}")
        # Text
        text_id = self.create_text(x+w//2, y+h//2, text=text, font=("Arial", 8), tags=f"text_{slot_key}")

    def _get_group_info(self, group_id):
        if not group_id: return "", "white"
        for g in self.groups:
            if g.id == group_id:
                return g.name, g.color
        return "?", "white"

    def _get_slot_at(self, x, y) -> Optional[Tuple[int, int, int]]:
        grid_width = 7 * self.cell_width
        
        # Check if click is within grid area (not sidebar, not header)
        if x >= grid_width or y < self.header_height:
            return None
            
        col = int(x // self.cell_width)
        d = 6 - col # Reverse mapping for RTL
        
        h = int((y - self.header_height) // self.cell_height)
        
        if not (0 <= d < 7 and 0 <= h < 24):
            return None
            
        # Check if right or left half
        rel_x = x % self.cell_width
        # If Pos 1 is Right half (x > half_width)
        pos = 1 if rel_x >= self.cell_width // 2 else 2
        
        return (d, h, pos)

    def _on_click(self, event):
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        slot = self._get_slot_at(x, y)
        
        if slot:
            self.drag_start_slot = slot
            
            # Create ghost visual
            if self.schedule:
                s = self.schedule.get_slot(*slot)
                group_id = s.group_id if s else None
                name, color = self._get_group_info(group_id)
                
                w = self.cell_width // 2
                h = self.cell_height
                
                # Center ghost on mouse
                x1 = x - w//2
                y1 = y - h//2
                x2 = x1 + w
                y2 = y1 + h
                
                self.drag_ghost_rect = self.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", stipple="gray50", tags="ghost")
                self.drag_ghost_text = self.create_text((x1+x2)//2, (y1+y2)//2, text=bidi_text(name), font=("Arial", 8), tags="ghost")

    def _on_drag(self, event):
        if self.drag_start_slot and self.drag_ghost_rect:
            x = self.canvasx(event.x)
            y = self.canvasy(event.y)
            
            w = self.cell_width // 2
            h = self.cell_height
            
            x1 = x - w//2
            y1 = y - h//2
            x2 = x1 + w
            y2 = y1 + h
            
            self.coords(self.drag_ghost_rect, x1, y1, x2, y2)
            self.coords(self.drag_ghost_text, (x1+x2)//2, (y1+y2)//2)

    def _on_release(self, event):
        # Remove ghost
        self.delete("ghost")
        self.drag_ghost_rect = None
        self.drag_ghost_text = None

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
        
        id1 = s1.group_id if s1 else None
        id2 = s2.group_id if s2 else None
        
        # Update model temporarily
        self.schedule.set_slot(slot1[0], slot1[1], slot1[2], id2)
        self.schedule.set_slot(slot2[0], slot2[1], slot2[2], id1)
        
        # Validate change via callback
        is_valid = self.on_change()
        
        if not is_valid:
            # Rollback
            self.schedule.set_slot(slot1[0], slot1[1], slot1[2], id1)
            self.schedule.set_slot(slot2[0], slot2[1], slot2[2], id2)
        
        self.redraw()
