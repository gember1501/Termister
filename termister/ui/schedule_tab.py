from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, timedelta

from rich.text import Text
from textual import on
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from ..config import load_settings
from ..models import INFO_TYPES, Lesson, room_numbers
from .widgets import DataTab

WEEKDAYS = ["Ma", "Di", "Wo", "Do", "Vr"]


class ScheduleTab(DataTab):
    def __init__(self, client):
        super().__init__(client)
        self.week_offset = 0
        self.shorten_rooms = load_settings().get("verkort_lokaalnummers", True)

    def compose(self):
        with Horizontal(id="week-nav"):
            yield Button("◀ Vorige week", id="week-prev")
            yield Static("", id="week-label")
            yield Button("Volgende week ▶", id="week-next")
            yield Button("Vandaag", id="week-today")
        yield from super().compose()

    def _monday(self) -> date:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(weeks=self.week_offset)

    def _week_range(self) -> tuple[date, date]:
        monday = self._monday()
        return monday, monday + timedelta(days=6)

    async def fetch_and_render(self):
        monday, sunday = self._week_range()
        lessons = await asyncio.to_thread(self.client.schedule, monday, sunday)
        await self._draw(monday, lessons)

    @on(Button.Pressed, "#week-prev")
    def _prev_week(self):
        self.week_offset -= 1
        self.run_worker(self.reload(), name="reload", group="data", exclusive=True)

    @on(Button.Pressed, "#week-next")
    def _next_week(self):
        self.week_offset += 1
        self.run_worker(self.reload(), name="reload", group="data", exclusive=True)

    @on(Button.Pressed, "#week-today")
    def _today_week(self):
        self.week_offset = 0
        self.run_worker(self.reload(), name="reload", group="data", exclusive=True)

    async def _draw(self, monday: date, lessons: list[Lesson]) -> None:
        self.query_one("#week-label", Static).update(self._week_label(monday))
        content = await self._clear_content()

        by_day: dict[int, list[Lesson]] = defaultdict(list)
        for lesson in lessons:
            if lesson.start is None:
                continue
            day_index = (lesson.start.date() - monday).days
            if 0 <= day_index < 5:
                by_day[day_index].append(lesson)

        slots: dict[tuple, list[tuple[int, Lesson]]] = defaultdict(list)
        for day_index, day_lessons in by_day.items():
            for lesson in day_lessons:
                slots[(lesson.start, lesson.end)].append((day_index, lesson))

        table = DataTable(id="week-table")
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.add_column("Tijd", key="time", width=11)
        for offset in range(5):
            day = monday + timedelta(days=offset)
            label = f"{WEEKDAYS[offset]} {day.day} {day.strftime('%b')}"
            table.add_column(label, key=f"day-{offset}")

        for slot in sorted(slots.keys()):
            first_lesson = slots[slot][0][1]
            cells = [self._time_cell(*slot, first_lesson)]
            for offset in range(5):
                day_lessons = [lesson for (day_index, lesson) in slots[slot] if day_index == offset]
                cells.append(self._lesson_cell(day_lessons) if day_lessons else "")
            table.add_row(*cells)

        await content.mount(table)
        await content.mount(Static(
            "[red]rood[/red] = toets · [strike]doorgestreept[/strike] = geannuleerd · "
            "[yellow]gewijzigd[/yellow]",
            id="legend",
        ))

    def _week_label(self, monday: date) -> str:
        friday = monday + timedelta(days=4)
        iso = monday.isocalendar()
        return f"Week {iso.week} · {monday.day} {monday.strftime('%b')} – {friday.day} {friday.strftime('%b')} {iso.year}"

    def _time_cell(self, start, end, lesson) -> Text:
        text = Text()
        if lesson.period_start and lesson.period_end:
            text.append(f"uur {lesson.period_start}", style="bold")
            if lesson.period_end != lesson.period_start:
                text.append(f"–{lesson.period_end}", style="bold")
            text.append("\n")
        text.append(f"{start.strftime('%H:%M')}\n", style="bold")
        text.append(end.strftime("%H:%M"), style="dim")
        return text

    def _lesson_cell(self, lessons: list[Lesson]) -> Text:
        blocks: list[Text] = []
        for lesson in lessons:
            style = "red bold" if lesson.is_test else "bold"
            text = Text(lesson.subject, style=style)
            details = []
            if lesson.rooms:
                details.append(
                    room_numbers(lesson.rooms) if self.shorten_rooms else ", ".join(lesson.rooms)
                )
            if lesson.teachers:
                details.append(", ".join(lesson.teachers))
            if lesson.is_test:
                details.append(INFO_TYPES.get(lesson.info_type, "toets").lower())
            if lesson.is_changed:
                details.append("gewijzigd")
            if lesson.is_cancelled:
                details.append("geannuleerd")
            text.append("\n", style=style)
            text.append(" · ".join(details), style="dim")
            if lesson.is_cancelled:
                text.stylize("strike")
            blocks.append(text)
        combined = Text()
        for index, block in enumerate(blocks):
            if index:
                combined.append("\n\n")
            combined.append_text(block)
        return combined
