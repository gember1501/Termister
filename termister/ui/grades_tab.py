from __future__ import annotations

import asyncio
from datetime import datetime

from rich.text import Text
from textual.widgets import DataTable, Static

from ..models import Grade
from .widgets import DataTab


class GradesTab(DataTab):
    async def fetch_and_render(self):
        grades = await asyncio.to_thread(self.client.grades, 200)
        await self._draw(grades)

    async def _draw(self, grades: list[Grade]) -> None:
        content = await self._clear_content()
        if not grades:
            await content.mount(Static("[dim]Nog geen cijfers bekend.[/dim]"))
            return

        await content.mount(Static(self._summary(grades), classes="stats-line"))

        table = DataTable(id="grades-table")
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.add_column("Datum", key="date", width=10)
        table.add_column("Vak", key="subject", width=16)
        table.add_column("Toets", key="description")
        table.add_column("Cijfer", key="value", width=7)
        table.add_column("Weegfactor", key="weight", width=10)
        table.add_column("Telt mee", key="counts", width=9)
        for grade in sorted(
            grades,
            key=lambda grade: (grade.entered is None, grade.entered or datetime.min),
            reverse=True,
        ):
            value_text = Text(
                grade.label,
                style="bold " + ("green" if grade.passed else "red"),
            )
            table.add_row(
                self._date(grade.entered),
                grade.subject,
                grade.description or "—",
                value_text,
                f"{grade.weight:g}" if grade.weight else "—",
                "ja" if grade.counts else "nee",
            )
        await content.mount(table)

        per_subject = self._per_subject(grades)
        if per_subject:
            await content.mount(Static("[b]Gemiddelden per vak[/b]", classes="stats-line"))
            table2 = DataTable(id="subject-averages")
            table2.zebra_stripes = True
            table2.add_column("Vak", key="subject", width=18)
            table2.add_column("Aantal", key="count", width=8)
            table2.add_column("Gemiddelde", key="avg", width=12)
            table2.add_column("Laagste", key="low", width=8)
            table2.add_column("Hoogste", key="high", width=8)
            for subject, info in per_subject.items():
                average_text = Text(
                    f"{info['avg']:.1f}",
                    style="bold " + ("green" if info["avg"] >= 5.5 else "red"),
                )
                table2.add_row(
                    subject,
                    str(info["count"]),
                    average_text,
                    f"{info['low']:g}",
                    f"{info['high']:g}",
                )
            await content.mount(table2)

    def _summary(self, grades: list[Grade]) -> str:
        values = [g.numeric_value for g in grades if g.numeric_value is not None and g.counts]
        if not values:
            return "[dim]Nog geen meetellende cijfers.[/dim]"
        average = sum(values) / len(values)
        passed = sum(1 for grade in grades if grade.passed)
        color = "green" if average >= 5.5 else "red"
        return (
            f"[b]Gemiddelde:[/b] [{color}]{average:.1f}[/{color}] "
            f"over {len(values)} meetellende cijfers ({passed}/{len(grades)} voldoende)"
        )

    def _per_subject(self, grades: list[Grade]) -> dict:
        per: dict[str, dict] = {}
        for grade in grades:
            if grade.numeric_value is None or not grade.counts:
                continue
            subject = grade.subject or grade.subject_code or "Onbekend"
            per.setdefault(subject, []).append(grade.numeric_value)
        return {
            subject: {
                "count": len(values),
                "avg": sum(values) / len(values),
                "low": min(values),
                "high": max(values),
            }
            for subject, values in sorted(per.items())
        }

    def _date(self, value: datetime | None) -> str:
        return value.strftime("%d-%m-%Y") if value else "—"
