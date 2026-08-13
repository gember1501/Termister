from __future__ import annotations

import asyncio
from datetime import date, datetime

from rich.text import Text
from textual.widgets import DataTable, Static

from ..models import Assignment
from .widgets import DataTab


class AssignmentsTab(DataTab):
    async def fetch_and_render(self):
        assignments = await asyncio.to_thread(self.client.assignments)
        await self._draw(assignments)

    async def _draw(self, assignments: list[Assignment]) -> None:
        content = await self._clear_content()
        if not assignments:
            await content.mount(Static("[dim]Geen opdrachten gevonden.[/dim]"))
            return

        table = DataTable(id="assignments-table")
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.add_column("Deadline", key="deadline", width=17)
        table.add_column("Vak", key="subject", width=16)
        table.add_column("Opdracht", key="title")
        table.add_column("Docenten", key="teachers", width=22)
        table.add_column("Status", key="status", width=18)
        table.add_column("Cijfer", key="grade", width=7)

        today = date.today()

        def sort_key(assignment: Assignment):
            if assignment.deadline is None:
                return (2, datetime.max)
            if assignment.deadline.date() < today:
                return (0, assignment.deadline)
            return (1, assignment.deadline)

        for assignment in sorted(assignments, key=sort_key):
            deadline_text = Text(self._deadline(assignment.deadline))
            if (
                assignment.deadline
                and assignment.deadline.date() < today
                and not assignment.finished
            ):
                deadline_text.stylize("red bold")
            grade_text = (
                Text(assignment.grade, style="bold green") if assignment.grade else Text("—")
            )
            table.add_row(
                deadline_text,
                assignment.subject,
                assignment.title or assignment.description or "—",
                ", ".join(assignment.teachers),
                assignment.status_text,
                grade_text,
            )
        await content.mount(table)

    def _deadline(self, value: datetime | None) -> str:
        if value is None:
            return "—"
        text = value.strftime("%d %b %Y")
        if value.hour or value.minute:
            text += f" {value.strftime('%H:%M')}"
        return text
