# Shmirot Gdud

A Python application for managing and scheduling weekly guard duties for groups.

## Features

*   **Group Management**: Create, edit, and delete groups.
*   **Constraints**: Define staffing size, weekly quotas, unavailability rules, and primary activity windows.
*   **Automatic Scheduling**: Generate a weekly schedule respecting hard constraints and aiming for fair distribution.
*   **Manual Adjustments**: Drag and drop to swap shifts in the schedule grid.
*   **Validation**: Real-time validation of schedule against constraints.
*   **Export**: Export schedule and group data to Excel.
*   **Persistence**: Save and load group configurations to/from JSON files.

## Installation

1.  Ensure you have Python 3.8+ installed.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    (Note: `tkinter` is usually included with Python, but on some Linux distributions you might need to install `python3-tk`).

## Usage

Run the application:

```bash
python main.py
```

### Workflow

1.  **Add Groups**: Use the "Add Group" button to create groups.
2.  **Configure Groups**: Select a group and fill in details:
    *   **Name**: Group name.
    *   **Staffing Size**: Relative size for proportional distribution (if no hard quota).
    *   **Weekly Quota**: Fixed number of shifts per week (overrides proportional distribution).
    *   **Unavailability Rules**: Times when the group absolutely cannot guard.
    *   **Activity Windows**: Times when the group has primary activities (soft constraint - scheduler tries to avoid these).
3.  **Generate Schedule**: Click "Generate Schedule".
4.  **Review & Edit**: Check the grid. Drag and drop cells to swap shifts if needed.
5.  **Export**: Use `File -> Export to Excel` to save the schedule.
6.  **Save Work**: Use `File -> Save Groups` to save your configuration for later.

## Developer Notes

### Project Structure

*   `main.py`: Entry point.
*   `src/shmirot_gdud/`: Source code package.
    *   `core/`: Core logic and data models.
        *   `models.py`: Data classes (`Group`, `WeeklySchedule`, `TimeWindow`).
        *   `scheduler.py`: Scheduling algorithm.
    *   `gui/`: User interface (Tkinter).
        *   `app.py`: Main application window and controller.
        *   `dialogs.py`: Dialogs for editing constraints.
        *   `schedule_grid.py`: Custom widget for the schedule grid.

### Data Model

*   **Group**: Represents a unit that can perform guard duty.
*   **WeeklySchedule**: Represents the 7-day, 24-hour schedule with 2 positions per hour.
*   **TimeWindow**: Represents a specific time range on a specific day (0=Sunday).

### Scheduling Algorithm

The current scheduler uses a randomized greedy approach:
1.  Calculates target quotas for each group based on fixed quotas or proportional staffing size.
2.  Iterates through all slots in random order.
3.  Assigns the best available group to each slot, prioritizing groups that are furthest from their target quota.
4.  Respects hard unavailability constraints.

Future improvements could include a more sophisticated constraint solver (e.g., backtracking or constraint programming) to better handle soft constraints like activity windows and consecutive shifts.
