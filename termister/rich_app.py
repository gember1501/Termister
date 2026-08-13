from __future__ import annotations

import io
import os
import select
import sys
import termios
import threading
import tty
from collections import defaultdict
from datetime import date, datetime, timedelta

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .auth import perform_login
from .client import MagisterClient
from .config import (
    load_credentials,
    load_session,
    load_settings,
    save_credentials,
    save_session,
    save_settings,
    clear_session,
)
from .demo_data import DemoClient
from .errors import NotAuthenticatedError, TermisterError
from .models import INFO_TYPES, Assignment, Grade, Lesson, room_numbers

WEEKDAYS = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
DAY_NAMES = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
MONTHS = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

SELECT_CELL_BG = "on rgb(52,92,164)"
SELECT_ROW_BG = "on rgb(23,38,65)"

_DIGITS = {
    "0": (" ███ ", "█   █", "█   █", "█   █", "█   █", "█   █", " ███ "),
    "1": ("  █  ", " ██  ", "  █  ", "  █  ", "  █  ", "  █  ", " ████"),
    "2": (" ███ ", "█   █", "    █", "   █ ", "  █  ", " █   ", "█████"),
    "3": (" ███ ", "█   █", "    █", "  ██ ", "    █", "█   █", " ███ "),
    "4": ("   █ ", "  ██ ", " █ █ ", "█  █ ", "█████", "   █ ", "   █ "),
    "5": ("█████", "█    ", "████ ", "    █", "    █", "█   █", " ███ "),
    "6": (" ███ ", "█    ", "█    ", "████ ", "█   █", "█   █", " ███ "),
    "7": ("█████", "    █", "   █ ", "  █  ", "  █  ", " █   ", " █   "),
    "8": (" ███ ", "█   █", "█   █", " ███ ", "█   █", "█   █", " ███ "),
    "9": (" ███ ", "█   █", "█   █", " ████", "    █", "    █", " ███ "),
    ":": ("     ", "  █  ", "  █  ", "     ", "  █  ", "  █  ", "     "),
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
}


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        first = os.read(fd, 1)
        if first != b"\x1b":
            return first.decode("utf-8", "replace")
        rest = b""
        while len(rest) < 8:
            ready, _, _ = select.select([fd], [], [], 0.03)
            if not ready:
                break
            data = os.read(fd, 1)
            if not data:
                break
            rest += data
        return "\x1b" + rest.decode("utf-8", "replace")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class RichTermister:
    def __init__(
        self,
        demo: bool = False,
        school: str | None = None,
        username: str | None = None,
        password: str | None = None,
        use_cache: bool = True,
        use_saved_credentials: bool = True,
        today: date | None = None,
    ):
        self.demo = demo
        self.cli_credentials = {"school": school, "username": username, "password": password}
        self.use_cache = use_cache
        self.use_saved_credentials = use_saved_credentials
        self._today = today or date.today()
        self.client = None
        self.school_name: str | None = None
        self.section = "schedule"
        self.day_offset = 0
        self.period_offset = 0
        self.selected_period: int | None = None
        self.selected_day: int = 0
        self.detail_lessons: list[Lesson] | None = None
        self._term_lines: int | None = None
        self._term_columns: int | None = None
        self.settings = load_settings()
        self._cache: dict[str, list] = {}
        self.status_message = ""

    # -- lifecycle ---------------------------------------------------------

    def run(self) -> None:
        console = Console()
        try:
            self._initialise(console)
        except TermisterError as exc:
            console.print(f"[red]Fout:[/red] {exc}")
            return
        except Exception as exc:
            console.print(f"[red]Onverwachte fout:[/red] {exc}")
            return

        sys.stdout.write("\x1b[?1049h\x1b[?25l")
        sys.stdout.flush()
        stop = threading.Event()

        def _redraw() -> None:
            try:
                try:
                    columns, lines = os.get_terminal_size(sys.stdout.fileno())
                except OSError:
                    columns, lines = 0, 0
                if columns < 20 or lines < 5:
                    columns, lines = 80, 24
                self._term_lines = lines
                self._term_columns = columns
                buffer = io.StringIO()
                render_console = Console(
                    file=buffer, force_terminal=True, width=columns, height=lines
                )
                render_console.print(self.render())
                sys.stdout.write("\x1b[H" + buffer.getvalue() + "\x1b[J")
                sys.stdout.flush()
            except Exception:
                pass

        def _ticker() -> None:
            while not stop.wait(1.0):
                _redraw()

        try:
            _redraw()
            threading.Thread(target=_ticker, daemon=True).start()
            while True:
                key = _read_key()
                if not self.on_key(key):
                    break
                _redraw()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    def _initialise(self, console: Console) -> None:
        if self.demo:
            self.client = DemoClient()
            self.school_name = DemoClient.school_name
            return

        session = load_session() if self.use_cache else {}
        if session.get("api_url") and session.get("app_token") and session.get("person_id"):
            # Try to refresh the saved session if possible so an expired token is
            # renewed before making any API calls. If refresh fails, continue
            # with the saved token (it might still be valid) and let callers handle
            # authentication errors.
            try:
                from .auth import refresh_session

                new_app = refresh_session() if session.get("refresh_token") else None
            except Exception:
                new_app = None
            app_token = new_app or session["app_token"]
            self.client = MagisterClient(session["api_url"], app_token, session["person_id"])
            # Validate the token so the app doesn't start with an expired
            # session that immediately errors on the first API call.
            try:
                self.client._get("/account")
            except Exception:
                # Any error validating the saved token should clear the session so
                # the user is prompted to log in again.
                try:
                    clear_session()
                finally:
                    pass
            else:
                self.school_name = session.get("school_name") or "Magister"
                return

        creds = {k: v for k, v in (self.cli_credentials or {}).items() if v}
        if not creds and self.use_saved_credentials:
            creds = load_credentials()
        school = creds.get("school") or Prompt.ask("Schoolnaam (of subdomein, bv sghaarlem)")
        username = creds.get("username") or Prompt.ask("Gebruikersnaam")
        password = creds.get("password") or Prompt.ask("Wachtwoord", password=True)

        with console.status("Inloggen bij Magister…", spinner="dots"):
            result = perform_login(school, username, password)

        self.client = MagisterClient(result.api_url, result.app_token, result.person_id)
        self.school_name = result.school_name
        save_session(
            {
                "school_name": result.school_name,
                "api_url": result.api_url,
                "app_token": result.app_token,
                "person_id": result.person_id,
                "refresh_token": result.refresh_token,
            }
        )
        save_credentials(school, username)

    def on_key(self, key: str) -> bool:
        if self.detail_lessons is not None:
            if key in ("q", "Q", "\x1b", "\r", " "):
                self.detail_lessons = None
            return True
        if key in ("q", "Q", "\x1b"):
            return False
        if key == "0":
            self.section = "dashboard"
        elif key == "1":
            self.section = "schedule"
        elif key == "2":
            self.section = "grades"
        elif key == "3":
            self.section = "assignments"
        elif key in ("r", "R"):
            self.refresh()
        elif key in ("[",):
            self.day_offset -= 1
            self._clear_schedule_cache()
        elif key in ("]",):
            self.day_offset += 1
            self._clear_schedule_cache()
        elif key in ("t", "T"):
            self.day_offset = 0
            self._clear_schedule_cache()
        elif key in ("\x1b[D",):
            if self.section == "schedule":
                self.selected_day = max(0, self.selected_day - 1)
        elif key in ("\x1b[C",):
            if self.section == "schedule":
                self.selected_day = min(2, self.selected_day + 1)
        elif key in ("j", "\x1b[B"):
            if self.section == "schedule":
                self._select_next_period(1)
        elif key in ("k", "\x1b[A"):
            if self.section == "schedule":
                self._select_next_period(-1)
        elif key in ("\r", "\n"):
            if self.section == "schedule":
                self._open_detail()
        elif key in ("l", "L"):
            self.settings["verkort_lokaalnummers"] = not self.settings.get(
                "verkort_lokaalnummers", True
            )
            save_settings(self.settings)
            self.status_message = (
                "Verkort lokaalnummers: aan" if self.settings["verkort_lokaalnummers"] else "Verkort lokaalnummers: uit"
            )
        return True

    def _current_periods(self) -> list[int]:
        return list(range(1, self._max_periods() + 1))

    def _max_periods(self) -> int:
        try:
            return max(1, min(12, int(self.settings.get("max_periods", 7))))
        except (TypeError, ValueError):
            return 7

    def _select_next_period(self, step: int) -> None:
        periods = self._current_periods()
        if self.selected_period is None or self.selected_period not in periods:
            self.selected_period = periods[0]
        index = periods.index(self.selected_period) + step
        index = min(max(0, index), len(periods) - 1)
        self.selected_period = periods[index]

    def _selected_lessons(self) -> list[Lesson]:
        first = self._first_day()
        lessons = self._fetch(
            f"schedule:{first.isoformat()}", self.client.schedule, first, first + timedelta(days=2)
        )
        period = self.selected_period or 1
        return [
            lesson
            for lesson in lessons
            if lesson.start is not None
            and not lesson.full_day
            and (lesson.start.date() - first).days == self.selected_day
            and self._period_of(lesson) == period
        ]

    def _open_detail(self) -> None:
        lessons = self._selected_lessons()
        if lessons:
            self.detail_lessons = lessons

    def refresh(self) -> None:
        self._cache.clear()
        self.status_message = ""

    # -- data --------------------------------------------------------------

    def _fetch(self, key: str, fn, *args) -> list:
        if key not in self._cache:
            self._cache[key] = fn(*args)
        return self._cache[key]

    def _clear_schedule_cache(self) -> None:
        self.period_offset = 0
        self.selected_period = None
        self.selected_day = 0
        self.detail_lessons = None
        for key in [k for k in self._cache if k.startswith("schedule:")]:
            del self._cache[key]

    def _first_day(self) -> date:
        return self._today + timedelta(days=self.day_offset)

    # -- dashboard ---------------------------------------------------------

    def _dashboard_view(self) -> Group:
        now = datetime.now()
        grades = self._fetch("grades", self.client.grades, 200)
        start = self._school_year_start()
        year_grades = [
            grade for grade in grades
            if grade.entered is not None and grade.entered.date() >= start
        ]

        parts = [
            Text(""),
            Text(""),
            Align.center(self._big_clock(now)),
            Align.center(
                Text(
                    f"{DAY_NAMES[now.weekday()]} {now.day} {MONTHS[now.month - 1]} {now.year}",
                    style="bold",
                )
            ),
            Text(""),
            Text(f"Cijfers schooljaar {start.year}–{start.year + 1}", style="bold"),
        ]
        if year_grades:
            parts.append(self._grade_graph(year_grades))
            parts.append(self._grades_summary(year_grades))
            parts.append(Text("Gemiddelde per vak", style="bold"))
            parts.append(self._subject_bars(year_grades))
        else:
            parts.append(Text("Nog geen cijfers dit schooljaar.", style="dim"))
        return Group(*parts)

    def _big_clock(self, now: datetime) -> Text:
        glyphs = [_DIGITS.get(char, _DIGITS[" "]) for char in now.strftime("%H:%M:%S")]
        lines = ["".join(glyph[row] + "  " for glyph in glyphs) for row in range(len(glyphs[0]))]
        width = max(len(line) for line in lines)
        block = Text()
        for line in lines:
            block.append(line.ljust(width), style="bold cyan")
            block.append("\n")
        return block

    def _school_year_start(self, reference: date | None = None) -> date:
        ref = reference or date.today()
        start = date(ref.year, 9, 1)
        if ref < start:
            start = date(ref.year - 1, 9, 1)
        return start

    def _grade_graph(self, grades: list[Grade]) -> Group:
        ordered = sorted(grades, key=lambda g: g.entered or datetime.min)
        show = ordered[-30:]
        lines: list[Text] = []
        for level in range(10, 0, -1):
            row = Text()
            for grade in show:
                value = grade.numeric_value or 0
                color = "green" if grade.passed else "red"
                if value >= level:
                    row.append("█ ", style=color)
                elif value + 0.5 >= level:
                    row.append("▄ ", style=color)
                else:
                    row.append("  ")
            lines.append(row)
        caption = Text(
            f"Laatste {len(show)} van {len(ordered)} cijfers · balkhoogte = cijfer (0–10) · "
            "groen = voldoende · rood = onvoldoende",
            style="dim",
        )
        return Group(*lines, caption)

    def _subject_bars(self, grades: list[Grade]) -> Group:
        lines: list[Text] = []
        for subject, info in self._per_subject(grades).items():
            value = info["avg"]
            color = "green" if value >= 5.5 else "red"
            bar = "█" * int(round(value / 10 * 20))
            text = Text()
            text.append(f"{subject:<18}", style="bold")
            text.append(f"{value:.1f}  ", style=f"bold {color}")
            text.append(bar, style=color)
            text.append(f"  (n={info['count']})", style="dim")
            lines.append(text)
        return Group(*lines)

    # -- render ------------------------------------------------------------

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=4),
        )
        layout["header"].update(self._header())
        layout["body"].update(self._body())
        layout["footer"].update(self._footer())
        return layout

    def _header(self) -> Panel:
        today = date.today()
        title = Text()
        title.append("Termister", style="bold cyan")
        title.append("   ")
        title.append(self.school_name or "Magister", style="bold")
        subtitle = f"{DAY_NAMES[today.weekday()]} {today.day} {MONTHS[today.month - 1]} {today.year}"
        return Panel(title, subtitle=subtitle, box=box.ROUNDED, border_style="cyan")

    def _footer(self) -> Panel:
        keys = (
            "0 Home   1 Rooster   2 Cijfers   3 Huiswerk & toetsen   "
            "↑/↓ selecteer   ←/→ dag   [ / ] week   t Vandaag   Enter details   r Vernieuwen   l Lokaalnummers   q Afsluiten"
        )
        source = "demo" if isinstance(self.client, DemoClient) else "Magister"
        status = Text(f"Bron: {source}")
        if self.settings.get("verkort_lokaalnummers", True):
            status.append("   ·   ", style="dim")
            status.append("verkort lokaalnummers: aan", style="dim")
        if self.status_message:
            status.append("   ·   ", style="dim")
            status.append(self.status_message, style="yellow")
        return Panel(Group(Text(keys, style="dim"), status), box=box.ROUNDED, border_style="blue")

    def _body(self) -> Panel:
        try:
            if self.section == "dashboard":
                return Panel(self._dashboard_view(), title="Home", box=box.ROUNDED, border_style="green")
            if self.section == "schedule":
                if self.detail_lessons is not None:
                    return Panel(
                        self._detail_view(self.detail_lessons),
                        title="Details",
                        box=box.ROUNDED,
                        border_style="green",
                    )
                return Panel(self._schedule_view(), title="Rooster", box=box.ROUNDED, border_style="green")
            if self.section == "grades":
                return Panel(self._grades_view(), title="Cijfers", box=box.ROUNDED, border_style="green")
            return Panel(self._assignments_view(), title="Huiswerk & Toetsen", box=box.ROUNDED, border_style="green")
        except NotAuthenticatedError as exc:
            return Panel(Text(str(exc), style="red bold"), title="Sessie verlopen", box=box.ROUNDED, border_style="red")
        except TermisterError as exc:
            self.status_message = str(exc)
            return Panel(Text(f"{exc}", style="red"), title="Fout", box=box.ROUNDED, border_style="red")

    # -- schedule ----------------------------------------------------------

    def _schedule_view(self) -> Group:
        first = self._first_day()
        end = first + timedelta(days=2)
        lessons = self._fetch(
            f"schedule:{first.isoformat()}", self.client.schedule, first, end
        )

        by_day: dict[int, list[Lesson]] = defaultdict(list)
        for lesson in lessons:
            if lesson.start is None:
                continue
            day_index = (lesson.start.date() - first).days
            if 0 <= day_index < 3:
                by_day[day_index].append(lesson)

        legend = Text(
            "rood = toets   ·   doorgestreept = geannuleerd   ·   geel = gewijzigd",
            style="dim",
        )
        date_label = (
            f"{DAY_NAMES[first.weekday()]} {first.day} {MONTHS[first.month - 1]} {first.year}  –  "
            f"{DAY_NAMES[end.weekday()].lower()} {end.day} {MONTHS[end.month - 1]}"
        )

        periods = list(range(1, self._max_periods() + 1))

        if self.selected_period is None or self.selected_period not in periods:
            self.selected_period = periods[0]
        selected_index = periods.index(self.selected_period)
        selection = (self.selected_day, self.selected_period)

        if self._term_lines is None:
            table = self._schedule_table(periods, by_day, selection)
            return Group(Text(date_label, style="bold"), legend, table)

        columns = max(1, (self._term_columns or 80) - 2)
        page_available = max(1, self._term_lines - 9)
        total = len(periods)

        def page(end_idx: int, page_start: int, show_indicator: bool = True) -> Group:
            label = date_label
            if show_indicator:
                label += f"   ·   periodes {page_start + 1}–{end_idx} van {total}"
            return Group(
                Text(label, style="bold"),
                legend,
                self._schedule_table(
                    periods[page_start:end_idx],
                    by_day,
                    selection,
                    full_day_row=end_idx == total,
                ),
            )

        def page_height(end_idx: int, page_start: int, show_indicator: bool = True) -> int:
            buffer = io.StringIO()
            Console(file=buffer, width=columns, height=10000).print(page(end_idx, page_start, show_indicator))
            return len(buffer.getvalue().splitlines())

        def build(page_start: int) -> tuple[int, bool]:
            end_idx = page_start
            for candidate in range(page_start + 1, total + 1):
                if page_height(candidate, page_start) <= page_available:
                    end_idx = candidate
                else:
                    break
            partial = False
            if end_idx == page_start:
                end_idx = page_start + 1
                partial = True
            elif end_idx < total:
                if end_idx + 1 == total:
                    if page_height(end_idx + 1, page_start) <= page_available:
                        end_idx += 1
                else:
                    overflow = page_height(end_idx + 1, page_start) - page_available
                    added = page_height(end_idx + 1, page_start) - page_height(end_idx, page_start)
                    if overflow < added:
                        end_idx += 1
                        partial = True
            return end_idx, partial

        if page_height(total, 0, show_indicator=False) <= page_available:
            self.period_offset = 0
            return page(total, 0, show_indicator=False)

        start = self.period_offset = min(max(0, self.period_offset), total - 1)
        end_idx, partial = build(start)
        if selected_index < start:
            start = self.period_offset = selected_index
            end_idx, partial = build(start)
        elif selected_index > end_idx - 1 or (selected_index == end_idx - 1 and partial):
            fully_visible = end_idx - (1 if partial else 0) - start
            new_start = max(0, selected_index - max(1, fully_visible) + 1)
            new_end, new_partial = build(new_start)
            if selected_index > new_end - 1 or (selected_index == new_end - 1 and new_partial):
                new_start = selected_index
                new_end, new_partial = build(new_start)
            start = self.period_offset = new_start
            end_idx, partial = new_end, new_partial
        return page(end_idx, start)

    def _detail_view(self, lessons: list[Lesson]) -> Group:
        parts: list = []
        for index, lesson in enumerate(lessons):
            style = "red bold" if lesson.is_test else "bold"
            head = Text(" · ".join(lesson.subjects) or "Les", style=style)
            if lesson.is_cancelled:
                head.append("   (geannuleerd)", style="red bold")
            elif lesson.is_changed:
                head.append("   (gewijzigd)", style="yellow bold")

            lines: list = [head]
            times: list[str] = []
            if lesson.start:
                times.append(f"{DAY_NAMES[lesson.start.weekday()].lower()} "
                             f"{lesson.start.day} {MONTHS[lesson.start.month - 1]} "
                             f"{lesson.start.year}, {lesson.start.strftime('%H:%M')}")
            if lesson.end:
                times.append(f"tot {lesson.end.strftime('%H:%M')}")
            if lesson.period_start or lesson.period_end:
                start = lesson.period_start or "?"
                end = lesson.period_end or start
                times.append(f"periode {start}–{end}")
            if times:
                lines.append(Text("   ".join(times), style="bold"))

            def row(label: str, value: str) -> None:
                if value:
                    line = Text(f"{label}: ", style="bold")
                    line.append(value)
                    lines.append(line)

            row("Docenten", ", ".join(lesson.teachers))
            rooms = ", ".join(lesson.rooms)
            if rooms:
                if self.settings.get("verkort_lokaalnummers", True):
                    rooms = room_numbers(lesson.rooms)
                row("Lokalen", rooms)
            row("Groepen", ", ".join(lesson.groups))
            if lesson.info_type is not None:
                row("Type", (INFO_TYPES.get(lesson.info_type) or "").capitalize())
            row("Omschrijving", lesson.description)
            row("Inhoud", lesson.content)
            row("Aantekening", lesson.annotation)
            row("Locatie", lesson.location)

            if index < len(lessons) - 1:
                lines.append(Text("─" * 40, style="dim"))
            parts.append(Group(*lines))
        return Group(*parts)

    def _schedule_table(
        self,
        periods: list[int],
        by_day: dict[int, list[Lesson]],
        selection: tuple[int, int] | None = None,
        full_day_row: bool = True,
    ) -> Table:
        first = self._first_day()
        table = Table(expand=True, pad_edge=False, box=box.ROUNDED, show_lines=True)
        table.add_column("Uur")
        for offset in range(3):
            day = first + timedelta(days=offset)
            table.add_column(f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}")

        full_day_by_day: dict[int, list[Lesson]] = {
            offset: [lesson for lesson in by_day[offset] if lesson.full_day]
            for offset in range(3)
        }

        row_style = SELECT_ROW_BG
        for period in periods:
            row_selected = selection is not None and selection[1] == period
            cells = [self._time_cell(period, by_day)]
            for offset in range(3):
                day_lessons = [
                    lesson
                    for lesson in by_day[offset]
                    if self._period_of(lesson) == period and not lesson.full_day
                ]
                cell_selected = row_selected and selection[0] == offset
                cell = self._lesson_cell(day_lessons, selected=cell_selected) if day_lessons else Text("")
                cells.append(cell)
            table.add_row(*cells, style=row_style if row_selected else None)

        if full_day_row and any(full_day_by_day.values()):
            cells = [self._full_day_cell(
                [lesson for offset in range(3) for lesson in full_day_by_day[offset]]
            )]
            for offset in range(3):
                lessons = full_day_by_day[offset]
                cells.append(self._lesson_cell(lessons) if lessons else Text(""))
            table.add_row(*cells)
        return table

    def _full_day_cell(self, lessons: list[Lesson]) -> Text:
        text = Text("de gehele dag", style="bold")
        if lessons:
            lesson = lessons[0]
            if lesson.start:
                text.append("\n")
                text.append(lesson.start.strftime("%H:%M"), style="bold")
                if lesson.end:
                    text.append("\n")
                    text.append(lesson.end.strftime("%H:%M"), style="dim")
        return text

    def _period_of(self, lesson: Lesson) -> int:
        if lesson.period_start:
            return lesson.period_start
        if lesson.start:
            return max(1, lesson.start.hour - 7)
        return 1

    def _time_cell(self, period: int, by_day: dict[int, list[Lesson]]) -> Text:
        text = Text(f"uur {period}", style="bold")
        lessons = [lesson for day_lessons in by_day.values() for lesson in day_lessons
                   if not lesson.full_day and self._period_of(lesson) == period]
        if lessons:
            lesson = lessons[0]
            if lesson.start:
                text.append("\n")
                text.append(lesson.start.strftime("%H:%M"), style="bold")
                if lesson.end:
                    text.append("\n")
                    text.append(lesson.end.strftime("%H:%M"), style="dim")
        return text

    def _lesson_cell(self, lessons: list[Lesson], selected: bool = False) -> Text:
        blocks: list[Text] = []
        for lesson in lessons:
            style = "red bold" if lesson.is_test else "bold"
            text = Text(lesson.subject, style=style)
            details = []
            if lesson.rooms:
                if self.settings.get("verkort_lokaalnummers", True):
                    details.append(room_numbers(lesson.rooms))
                else:
                    details.append(", ".join(lesson.rooms))
            if lesson.teachers:
                details.append(", ".join(lesson.teachers))
            if lesson.is_test:
                details.append((INFO_TYPES.get(lesson.info_type, "toets") or "toets").lower())
            if lesson.is_changed:
                details.append("gewijzigd")
            if lesson.is_cancelled:
                details.append("geannuleerd")
            text.append("\n")
            text.append(" · ".join(details), style="dim")
            if lesson.is_cancelled:
                text.stylize("strike")
            blocks.append(text)
        combined = Text()
        for index, block in enumerate(blocks):
            if index:
                combined.append("\n\n")
            combined.append_text(block)
        if selected:
            combined.stylize(SELECT_CELL_BG)
        return combined

    # -- grades ------------------------------------------------------------

    def _grades_view(self) -> Group:
        grades = self._fetch("grades", self.client.grades, 200)

        parts: list = [self._grades_summary(grades)]
        if not grades:
            parts.append(Text("Nog geen cijfers bekend.", style="dim"))
            return Group(*parts)

        table = Table(
            title="Laatste cijfers",
            title_justify="left",
            expand=True,
            box=box.ROUNDED,
        )
        table.add_column("Datum", width=12)
        table.add_column("Vak", width=16)
        table.add_column("Toets")
        table.add_column("Cijfer", justify="center", width=7)
        table.add_column("Weegfactor", justify="right", width=10)
        table.add_column("Telt mee", justify="center", width=9)
        for grade in sorted(
            grades,
            key=lambda g: (g.entered is None, g.entered or datetime.min),
            reverse=True,
        ):
            color = "green" if grade.passed else "red"
            table.add_row(
                grade.entered.strftime("%d-%m-%Y") if grade.entered else "—",
                grade.subject,
                grade.description or "—",
                Text(grade.label, style=f"bold {color}"),
                f"{grade.weight:g}" if grade.weight else "—",
                "ja" if grade.counts else "nee",
            )
        parts.append(table)

        per_subject = self._per_subject(grades)
        if per_subject:
            table2 = Table(
                title="Gemiddelden per vak",
                title_justify="left",
                expand=True,
                box=box.ROUNDED,
            )
            table2.add_column("Vak", width=18)
            table2.add_column("Aantal", justify="right", width=7)
            table2.add_column("Gemiddelde", justify="right", width=11)
            table2.add_column("Laagste", justify="right", width=8)
            table2.add_column("Hoogste", justify="right", width=8)
            for subject, info in per_subject.items():
                avg_style = "bold " + ("green" if info["avg"] >= 5.5 else "red")
                table2.add_row(
                    subject,
                    str(info["count"]),
                    Text(f"{info['avg']:.1f}", style=avg_style),
                    f"{info['low']:g}",
                    f"{info['high']:g}",
                )
            parts.append(table2)

        return Group(*parts)

    def _grades_summary(self, grades: list[Grade]) -> Text:
        values = [g.numeric_value for g in grades if g.numeric_value is not None and g.counts]
        if not values:
            return Text("Nog geen meetellende cijfers.", style="dim")
        average = sum(values) / len(values)
        passed = sum(1 for g in grades if g.passed)
        color = "green" if average >= 5.5 else "red"
        text = Text()
        text.append("Gemiddelde: ", style="bold")
        text.append(f"{average:.1f}", style=f"bold {color}")
        text.append(f" over {len(values)} meetellende cijfers ({passed}/{len(grades)} voldoende)")
        return text

    def _per_subject(self, grades: list[Grade]) -> dict:
        per: dict[str, list[float]] = {}
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

    # -- assignments -------------------------------------------------------

    def _assignments_view(self) -> Group:
        assignments = self._fetch("assignments", self.client.assignments)

        if not assignments:
            return Group(Text("Geen opdrachten gevonden.", style="dim"))

        table = Table(expand=True, box=box.ROUNDED)
        table.add_column("Deadline", width=16)
        table.add_column("Vak", width=16)
        table.add_column("Opdracht")
        table.add_column("Docenten", width=20)
        table.add_column("Status", width=16)
        table.add_column("Cijfer", justify="center", width=7)

        today = date.today()

        def sort_key(assignment: Assignment):
            if assignment.deadline is None:
                return (2, datetime.max)
            if assignment.deadline.date() < today:
                return (0, assignment.deadline)
            return (1, assignment.deadline)

        for assignment in sorted(assignments, key=sort_key):
            deadline: object = self._deadline(assignment.deadline)
            if (
                assignment.deadline
                and assignment.deadline.date() < today
                and not assignment.finished
            ):
                deadline = Text(self._deadline(assignment.deadline), style="red bold")
            grade = (
                Text(assignment.grade, style="bold green")
                if assignment.grade
                else Text("—", style="dim")
            )
            table.add_row(
                deadline,
                assignment.subject,
                assignment.title or assignment.description or "—",
                ", ".join(assignment.teachers),
                assignment.status_text,
                grade,
            )
        return Group(table)

    def _deadline(self, value: datetime | None) -> str:
        if value is None:
            return "—"
        text = f"{value.day} {MONTHS[value.month - 1]} {value.year}"
        if value.hour or value.minute:
            text += f" {value.strftime('%H:%M')}"
        return text


def main(
    demo: bool = False,
    school: str | None = None,
    username: str | None = None,
    password: str | None = None,
    use_cache: bool = True,
    use_saved_credentials: bool = True,
) -> None:
    RichTermister(
        demo=demo,
        school=school,
        username=username,
        password=password,
        use_cache=use_cache,
        use_saved_credentials=use_saved_credentials,
    ).run()
