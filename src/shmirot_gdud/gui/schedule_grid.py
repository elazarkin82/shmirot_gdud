import tkinter as tk
from typing import Optional, Tuple, Callable, List, Dict
from datetime import datetime, timedelta
from shmirot_gdud.core.models import Schedule, Group, ScheduleSlot
from shmirot_gdud.gui.utils import bidi_text

DISABLED_ID = "DISABLED"

class ScheduleGrid(tk.Canvas):
    def __init__(self, parent, groups: List[Group], on_change: Callable[[], bool], **kwargs):
        super().__init__(parent, **kwargs)
        self.groups = groups
        self.on_change = on_change 
        self.schedule: Optional[Schedule] = None
        
        # Base dimensions
        self.base_cell_width = 140
        self.base_cell_height = 40
        self.base_header_height = 30
        self.base_sidebar_width = 60
        
        # Current dimensions (will be scaled)
        self.scale = 1.0
        self.cell_width = self.base_cell_width
        self.cell_height = self.base_cell_height
        self.header_height = self.base_header_height
        self.sidebar_width = self.base_sidebar_width
        
        self.days_names = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        
        # Highlight state
        self.highlighted_group_id: Optional[str] = None

        # Drag state
        self.drag_start_slot: Optional[Tuple[str, int, int]] = None 
        self.drag_ghost_rect = None
        self.drag_ghost_text = None
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Button-3>", self._on_right_click)

    def set_schedule(self, schedule: Schedule):
        self.schedule = schedule
        self.redraw()

    def refresh_groups(self, groups: List[Group]):
        self.groups = groups
        self.redraw()

    def set_highlighted_group(self, group_id: Optional[str]):
        """Sets the group to highlight. Pass None to clear highlight."""
        self.highlighted_group_id = group_id
        self.redraw()

    def zoom(self, factor: float):
        """Zooms in or out by adding factor to current scale"""
        new_scale = self.scale + factor
        if new_scale < 0.2: new_scale = 0.2 # Minimum limit
        if new_scale > 3.0: new_scale = 3.0 # Maximum limit
        
        self.scale = new_scale
        self._update_dimensions()
        self.redraw()

    def fit_to_width(self):
        """Adjusts scale so all columns fit within the current canvas width"""
        if not self.schedule: return
        
        canvas_width = self.winfo_width()
        if canvas_width <= 1: return # Not visible yet
        
        start_date = datetime.strptime(self.schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.schedule.end_date, "%Y-%m-%d")
        num_days = (end_date - start_date).days + 1
        
        if num_days == 0: return

        total_base_content = (num_days * self.base_cell_width) + self.base_sidebar_width
        new_scale = canvas_width / total_base_content
        
        if new_scale < 0.2: new_scale = 0.2
        
        self.scale = new_scale
        self._update_dimensions()
        self.redraw()

    def _update_dimensions(self):
        self.cell_width = int(self.base_cell_width * self.scale)
        self.cell_height = int(self.base_cell_height * self.scale)
        self.header_height = int(self.base_header_height * self.scale)
        self.sidebar_width = int(self.base_sidebar_width * self.scale)

    def redraw(self):
        self.delete("all")
        
        if not self.schedule:
            self.create_text(self.winfo_width()//2, self.winfo_height()//2, text=bidi_text("לא נוצר סידור עבודה"))
            return

        # Calculate date range
        start_date = datetime.strptime(self.schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.schedule.end_date, "%Y-%m-%d")
        num_days = (end_date - start_date).days + 1
        
        grid_width = num_days * self.cell_width
        total_width = grid_width + self.sidebar_width
        total_height = self.header_height + 24 * self.cell_height

        # Draw Sidebar (Hours) - On the Right for RTL
        sidebar_x = grid_width
        
        # Sidebar background
        self.create_rectangle(sidebar_x, 0, total_width, total_height, fill="#f0f0f0", outline="")
        
        font_size = max(6, int(8 * self.scale))
        
        for h in range(24):
            y = self.header_height + h * self.cell_height
            self.create_text(sidebar_x + self.sidebar_width//2, y + self.cell_height//2, text=f"{h:02d}:00", font=("Arial", font_size))

        # Draw Headers
        current = start_date
        for d in range(num_days):
            # RTL: First day is rightmost
            x = (num_days - 1 - d) * self.cell_width
            
            # Header background
            self.create_rectangle(x, 0, x + self.cell_width, self.header_height, fill="#e0e0e0", outline="")
            
            # Calculate day name
            py_wd = current.weekday()
            our_wd = (py_wd + 1) % 7
            day_name = self.days_names[our_wd]
            date_str = current.strftime("%d/%m")
            
            self.create_text(x + self.cell_width//2, self.header_height//2, text=bidi_text(f"{day_name} {date_str}"), font=("Arial", font_size, "bold"))
            
            current += timedelta(days=1)

        # Draw Grid Content
        slot_map = {}
        for slot in self.schedule.slots:
            slot_map[(slot.date, slot.hour, slot.position)] = slot

        current = start_date
        for d in range(num_days):
            date_str = current.strftime("%Y-%m-%d")
            
            for h in range(24):
                x = (num_days - 1 - d) * self.cell_width
                y = self.header_height + h * self.cell_height
                
                half_width = self.cell_width // 2
                
                # Position 1 (Right half)
                s1 = slot_map.get((date_str, h, 1))
                g1_id = s1.group_id if s1 else None
                g1_name, g1_color = self._get_group_info(g1_id)
                self._draw_slot(x + half_width, y, half_width, self.cell_height, bidi_text(g1_name), g1_color, (date_str, h, 1), font_size, g1_id)
                
                # Position 2 (Left half)
                s2 = slot_map.get((date_str, h, 2))
                g2_id = s2.group_id if s2 else None
                g2_name, g2_color = self._get_group_info(g2_id)
                self._draw_slot(x, y, half_width, self.cell_height, bidi_text(g2_name), g2_color, (date_str, h, 2), font_size, g2_id)

            current += timedelta(days=1)

        # Draw Grid Lines
        # Horizontal lines
        for h in range(25):
            y = self.header_height + h * self.cell_height
            self.create_line(0, y, total_width, y, fill="black", width=1)

        # Vertical lines
        for d in range(num_days + 1):
            x = d * self.cell_width
            self.create_line(x, 0, x, total_height, fill="black", width=1)
            
        # Update scroll region
        self.config(scrollregion=(0, 0, total_width, total_height))

    def _draw_slot(self, x, y, w, h, text, color, slot_key, font_size, group_id):
        # Determine visual style based on highlight
        fill_color = color
        outline_color = "lightgray"
        text_color = "black"
        width = 1
        
        if self.highlighted_group_id:
            if group_id == self.highlighted_group_id:
                # This is the highlighted group
                outline_color = "black"
                width = 2
            else:
                # This is NOT the highlighted group - dim it
                if group_id == DISABLED_ID:
                    fill_color = "#eeeeee" # Lighter gray than normal disabled
                    text_color = "#aaaaaa"
                elif group_id:
                    fill_color = "#f9f9f9" # Very light gray (almost white)
                    text_color = "#cccccc" # Dimmed text
                else:
                    # Empty slot
                    pass

        # Background
        rect_id = self.create_rectangle(x, y, x+w, y+h, fill=fill_color, outline=outline_color, width=width, tags=f"slot_{slot_key}")
        
        # Text
        if h > 10 and w > 20:
            text_id = self.create_text(x+w//2, y+h//2, text=text, fill=text_color, font=("Arial", font_size), tags=f"text_{slot_key}")

    def _get_group_info(self, group_id):
        if not group_id: return "", "white"
        
        if group_id == DISABLED_ID:
            return "---", "#555555" 
            
        for g in self.groups:
            if g.id == group_id:
                return g.name, g.color
        return "?", "white"

    def _get_slot_at(self, x, y) -> Optional[Tuple[str, int, int]]:
        if not self.schedule: return None
        
        start_date = datetime.strptime(self.schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.schedule.end_date, "%Y-%m-%d")
        num_days = (end_date - start_date).days + 1
        
        grid_width = num_days * self.cell_width
        
        if x >= grid_width or y < self.header_height:
            return None
            
        col = int(x // self.cell_width)
        d_idx = num_days - 1 - col # Reverse mapping for RTL
        
        if not (0 <= d_idx < num_days): return None
        
        target_date = start_date + timedelta(days=d_idx)
        date_str = target_date.strftime("%Y-%m-%d")
        
        h = int((y - self.header_height) // self.cell_height)
        if not (0 <= h < 24): return None
            
        rel_x = x % self.cell_width
        pos = 1 if rel_x >= self.cell_width // 2 else 2
        
        return (date_str, h, pos)

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
                
                font_size = max(6, int(8 * self.scale))
                self.drag_ghost_rect = self.create_rectangle(x1, y1, x2, y2, fill=color, outline="black", stipple="gray50", tags="ghost")
                self.drag_ghost_text = self.create_text((x1+x2)//2, (y1+y2)//2, text=bidi_text(name), font=("Arial", font_size), tags="ghost")

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

    def _on_right_click(self, event):
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        slot = self._get_slot_at(x, y)
        
        if not slot or not self.schedule:
            return
            
        menu = tk.Menu(self, tearoff=0)
        
        # Add "Clear" option
        menu.add_command(label=bidi_text("נקה משבצת"), command=lambda: self._replace_group_in_slot(slot, None))
        
        # Add "Disable" option
        menu.add_command(label=bidi_text("נטרל משבצת"), command=lambda: self._replace_group_in_slot(slot, DISABLED_ID))
        
        menu.add_separator()
        
        for group in self.groups:
            menu.add_command(label=bidi_text(group.name), command=lambda gid=group.id: self._replace_group_in_slot(slot, gid))
            
        menu.tk_popup(event.x_root, event.y_root)

    def _replace_group_in_slot(self, slot_key: Tuple[str, int, int], new_group_id: Optional[str]):
        if not self.schedule: return
        
        date_str, hour, pos = slot_key
        current_slot = self.schedule.get_slot(date_str, hour, pos)
        old_group_id = current_slot.group_id if current_slot else None
        
        if old_group_id == new_group_id:
            return

        # Update model
        self.schedule.set_slot(date_str, hour, pos, new_group_id, lock=True if new_group_id else False)
        
        # Validate
        is_valid = self.on_change()
        
        if not is_valid:
            # Rollback
            self.schedule.set_slot(date_str, hour, pos, old_group_id)
            
        self.redraw()

    def _swap_slots(self, slot1, slot2):
        if not self.schedule: return
        
        s1 = self.schedule.get_slot(*slot1)
        s2 = self.schedule.get_slot(*slot2)
        
        id1 = s1.group_id if s1 else None
        id2 = s2.group_id if s2 else None
        
        # Update model temporarily
        self.schedule.set_slot(slot1[0], slot1[1], slot1[2], id2, lock=True)
        self.schedule.set_slot(slot2[0], slot2[1], slot2[2], id1, lock=True)
        
        # Validate change via callback
        is_valid = self.on_change()
        
        if not is_valid:
            # Rollback
            self.schedule.set_slot(slot1[0], slot1[1], slot1[2], id1)
            self.schedule.set_slot(slot2[0], slot2[1], slot2[2], id2)
        
        self.redraw()
