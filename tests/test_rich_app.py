from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from termister.demo_data import DemoClient
from termister.models import parse_dt, room_numbers
from termister.rich_app import RichTermister

TODAY = date(2026, 8, 11)


def build() -> RichTermister:
    app = RichTermister(demo=True, today=TODAY)
    app._initialise(_NullConsole())
    return app


def render_text(renderable, width: int = 120) -> str:
    console = Console(record=True, width=width, force_terminal=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text()


class _NullConsole:
    def status(self, message: str, **kwargs):
        return _NullStatus()

    def print(self, *args, **kwargs):
        pass


class _NullStatus:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAIL: {label}")
    print(f"ok: {label}")


def plain(renderable) -> str:
    if hasattr(renderable, "renderable"):
        return plain(renderable.renderable)
    if hasattr(renderable, "plain"):
        return renderable.plain
    if hasattr(renderable, "renderables"):
        return "\n".join(plain(item) for item in renderable.renderables)
    return str(renderable)


app = build()

header = app._header()
check(isinstance(header, Panel), "header is a Panel")
check("Demo College" in header.renderable.plain, "header shows school name")

footer = app._footer()
check(isinstance(footer, Panel), "footer is a Panel")
check("Bron: demo" in plain(footer), "footer shows demo source")

layout = app.render()
check(isinstance(layout, Layout), "render returns a Layout")
names = [child.name for child in layout.children]
check("header" in names and "body" in names and "footer" in names,
      "layout has header/body/footer")

schedule = app._schedule_view()
check(hasattr(schedule, "renderables"), "schedule view is a Group")
date_label = schedule.renderables[0].plain
check("Maandag" in date_label or "Dinsdag" in date_label, "schedule shows date label")
check("doorgestreept" in plain(schedule.renderables[1]), "schedule shows legend")
table = schedule.renderables[2]
check(isinstance(table, Table), "schedule contains a Table")
check(len(table.columns) == 4, "schedule table has 4 columns (uur + 3 dagen)")
check(len(table.rows) >= 4, "schedule table has lesson rows")
check("Nederlands" in render_text(table), "schedule table contains a subject")
table_text = render_text(table)
hour_line = next(line for line in table_text.splitlines() if "uur 1" in line)
check("Geschiedenis" in hour_line and "Economie" in hour_line and "Engels" in hour_line,
      "period 1 lessons from all 3 days line up on the same row")

full_day = [l for l in DemoClient().schedule(TODAY, TODAY + timedelta(days=2)) if l.full_day]
check(bool(full_day), "demo data contains a full-day lesson")
fd = full_day[0]
fd_table = app._schedule_table([1], {0: [fd], 1: [], 2: []})
fd_text = render_text(fd_table)
check("de gehele dag" in fd_text, "full-day row is named 'de gehele dag'")
check(fd_text.index("de gehele dag") > fd_text.index("uur 1"),
      "full-day row sits below the period rows")
check(fd_text.count(fd.subjects[0]) == 1, "full-day lesson appears only in the last row")
check(fd.start.strftime("%H:%M") in fd_text, "full-day row shows the start time")

full_table = app._schedule_view().renderables[2]
full_text = render_text(full_table)
check("uur 7" in full_text and "uur 8" not in full_text,
      "all configured periods are shown even when empty")
app.settings["max_periods"] = 5
five_text = render_text(app._schedule_view().renderables[2])
check("uur 5" in five_text and "uur 6" not in five_text,
      "max_periods setting is honored")
app.settings["max_periods"] = 7

weekend_app = RichTermister(demo=True, today=date(2026, 8, 15))
weekend_app._initialise(_NullConsole())
weekend_app._term_lines = 40
weekend_app._term_columns = 120
weekend_text = render_text(weekend_app._schedule_view().renderables[2])
check(("Za" in weekend_text or "Zo" in weekend_text) and "uur 7" in weekend_text,
      "weekend days render without crashing")

app._term_lines = 30
app._term_columns = 100
paged = app._schedule_view()
paged_text = plain(paged)
check("periodes 1–4 van 7" in paged_text, "small terminal paginates schedule with indicator")
paged_table = paged.renderables[2]
check(len(paged_table.rows) == 4, "paginated schedule shows only fitting periods")
for _ in range(4):
    app.on_key("j")
paged2 = app._schedule_view()
check("periodes 2–5 van 7" in plain(paged2) and app.selected_period == 5,
      "j moves the selection and scrolls it fully into view")
for _ in range(4):
    app.on_key("k")
check("periodes 1–4 van 7" in plain(app._schedule_view()) and app.selected_period == 1,
      "k moves the selection back and scrolls the page up")
app.selected_period = 7
app.on_key("j")
last_paged = app._schedule_view()
last_text = render_text(last_paged.renderables[2])
check("de gehele dag" in last_text and "Excursie Natuurmuseum" in last_text,
      "last page shows the full-day row")
app.on_key("]")
check(app.day_offset == 1 and app.period_offset == 0 and app.selected_period is None,
      "day navigation resets selection and offset")
app._term_lines = None
app._term_columns = None
app.day_offset = 0

app._term_lines = 30
app._term_columns = 60
app.period_offset = 0
buf = io.StringIO()
Console(file=buf, width=60, height=30).print(app.render())
rendered = buf.getvalue()
check("1–4 van 7" in rendered and "Biologie" in rendered,
      "partially cut off last block stays visible instead of vanishing")
app._term_lines = None
app._term_columns = None

app.selected_period = 1
app.selected_day = 0
app.on_key("\x1b[C")
check(app.selected_day == 1, "right arrow selects the next day")
app.on_key("\x1b[D")
check(app.selected_day == 0, "left arrow selects the previous day")
app.on_key("\r")
check(app.detail_lessons is not None and app.detail_lessons[0].subjects == ["Geschiedenis"],
      "enter opens the detail view of the selected block")
app.on_key("\x1b")
check(app.detail_lessons is None, "esc closes the detail view")

app.selected_day = 0
app.selected_period = 1
app.on_key("k")
check(app.selected_period == 1, "k above the first period stays on period 1")

app.selected_period = 3
app.on_key("\r")
check(app.detail_lessons is None, "enter on an empty cell does not open a detail view")
app.selected_period = 1

lesson = DemoClient().schedule(TODAY, TODAY)[0]
sel_cell = app._lesson_cell([lesson], selected=True)
check(any("rgb(52,92,164)" in str(span.style) for span in sel_cell.spans),
      "selected day cell gets the solid cursor fill")
plain_cell = app._lesson_cell([lesson], selected=False)
check(not any("rgb(52,92,164)" in str(span.style) for span in plain_cell.spans),
      "unselected cell is not highlighted")

app.selected_period = 1
app.selected_day = 0
app._term_lines = None
app._term_columns = None
table = app._schedule_table([1, 2], {0: [], 1: [], 2: []}, selection=(0, 1))
row_styles = [row.style for row in table.rows]
check(row_styles[0] == "on rgb(23,38,65)" and row_styles[1] is None,
      "selected row gets the translucent fill, other rows stay plain")
app.selected_period = None
app.selected_day = 0

check(room_numbers(["Lokaal 43, verdieping 1"]) == "43",
      "room number wins over verdieping after a comma")
check(room_numbers(["verdieping 1, lokaal 43"]) == "43",
      "lokaal number wins when verdieping comes first")
check(room_numbers(["Lokaal 43 verdieping 1"]) == "43",
      "first number wins without comma")
check(room_numbers(["Lokaal 1.43"]) == "43",
      "room after dot in floor codes wins")
check(room_numbers(["Sporthal"]) == "Sporthal",
      "non-numeric rooms are kept")

check(parse_dt("2026-08-04T08:30:00+02:00").hour == 8,
      "Magister +02:00 times keep local wall time (not 2h early)")
check(parse_dt("2026-08-04T08:30:00Z").hour == datetime.now().astimezone().utcoffset().total_seconds() // 3600 + 8,
      "UTC times convert to the local timezone")
check(parse_dt("2026-08-04T08:30:00").hour == 8,
      "naive times stay as-is")

week = DemoClient().schedule(TODAY - timedelta(days=7), TODAY + timedelta(days=7))
lokaal27 = next(l for l in week if l.rooms == ["Lokaal 27"])
app.settings["verkort_lokaalnummers"] = True
check("27" in app._lesson_cell([lokaal27]).plain and "Lokaal 27" not in app._lesson_cell([lokaal27]).plain,
      "shortening on shows only the room number")
app.on_key("l")
check(app.settings["verkort_lokaalnummers"] is False,
      "l toggles verkort lokaalnummers off")
check("Lokaal 27" in app._lesson_cell([lokaal27]).plain,
      "shortening off shows the full room")
app.on_key("l")
check(app.settings["verkort_lokaalnummers"] is True,
      "l toggles verkort lokaalnummers back on")

app.section = "dashboard"
dashboard = app._dashboard_view()
dashboard_text = plain(dashboard)
check("Cijfers schooljaar" in dashboard_text, "dashboard shows school year header")
check("█" in dashboard_text, "dashboard clock shows block digits")
check("balkhoogte = cijfer" in dashboard_text, "dashboard shows grade graph caption")
check("Gemiddelde per vak" in dashboard_text, "dashboard shows per-subject bars")
check("Wiskunde" in dashboard_text, "dashboard subject bars contain a subject")

clock = render_text(app._big_clock(datetime(2026, 8, 11, 9, 15, 47)))
clock_lines = [line for line in clock.splitlines() if line.strip()]
check(len(set(len(line) for line in clock_lines)) == 1,
      "clock rows all have equal width")
first_block = clock_lines[0].index("█")
middle_start = clock_lines[1].index("█")
check(abs(first_block - (middle_start + 1)) <= 1,
      "clock top bar aligns with digit body")

app.on_key("0")
check(app.section == "dashboard", "key 0 switches to dashboard")
app.on_key("1")
check(app.section == "schedule", "key 1 switches to schedule")
app.section = "dashboard"

app.section = "grades"
grades = app._grades_view()
check(hasattr(grades, "renderables"), "grades view is a Group")
check("Gemiddelde" in grades.renderables[0].plain, "grades shows summary")
check(any(isinstance(r, Table) for r in grades.renderables), "grades contains a Table")

app.section = "assignments"
assignments = app._assignments_view()
check(hasattr(assignments, "renderables"), "assignments view is a Group")
a_table = assignments.renderables[0]
check(isinstance(a_table, Table), "assignments contains a Table")
check(len(a_table.rows) >= 6, "assignments table has rows")

app.section = "schedule"
app.on_key("]")
check(app.day_offset == 1, "right arrow advances a day")
app.on_key("[")
check(app.day_offset == 0, "left arrow moves back a day")
app.on_key("]")
app.on_key("]")
app.on_key("t")
check(app.day_offset == 0, "t jumps back to today")
app.on_key("2")
check(app.section == "grades", "key 2 switches to grades")
app.on_key("3")
check(app.section == "assignments", "key 3 switches to assignments")
app.on_key("1")
check(app.section == "schedule", "key 1 switches back to schedule")
app.on_key("r")
check(app._cache == {}, "r clears the data cache")
check(app.on_key("q") is False, "q quits")

print("ALL RICH CHECKS PASSED")
