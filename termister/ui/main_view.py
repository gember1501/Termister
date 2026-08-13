from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from .assignments_tab import AssignmentsTab
from .grades_tab import GradesTab
from .schedule_tab import ScheduleTab


class MainView(Vertical):
    def __init__(self, client, school_name: str):
        super().__init__()
        self.client = client
        self.school_name = school_name

    def compose(self):
        yield Static(f"[b]{self.school_name}[/b] — [dim]Magister[/dim]", id="school-bar")
        with TabbedContent(initial="tab-schedule"):
            with TabPane("Rooster", id="tab-schedule"):
                yield ScheduleTab(self.client)
            with TabPane("Cijfers", id="tab-grades"):
                yield GradesTab(self.client)
            with TabPane("Huiswerk & Toetsen", id="tab-assignments"):
                yield AssignmentsTab(self.client)
