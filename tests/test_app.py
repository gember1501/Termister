import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from termister.demo_data import DemoClient
from termister.models import Assignment, Grade, Lesson
from termister.ui.app import TermisterApp
from termister.ui.assignments_tab import AssignmentsTab
from termister.ui.grades_tab import GradesTab
from termister.ui.schedule_tab import ScheduleTab
from textual.widgets import DataTable, TabbedContent, TabPane


async def wait_for_workers(app, pilot, timeout=10.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await pilot.pause()
        workers = [w for w in app.workers if w.is_running or w.is_pending]
        if not workers:
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("workers did not finish")


async def main() -> int:
    demo = DemoClient()
    app = TermisterApp(demo=True)
    app.client = demo
    app.school_name = demo.school_name

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_workers(app, pilot)
        await pilot.pause()

        tabs = app.query_one(TabbedContent)
        panes = list(tabs.query(TabPane))
        assert len(panes) == 3, f"expected 3 tabs, got {len(panes)}"
        print("OK tabs:", [p.id for p in panes])

        schedule = app.query_one(ScheduleTab)
        table = schedule.query_one("#week-table", DataTable)
        assert table.row_count > 0, "schedule table empty"
        print("OK schedule rows:", table.row_count, "columns:", len(table.columns))

        grades = app.query_one(GradesTab)
        gtable = grades.query_one("#grades-table", DataTable)
        assert gtable.row_count > 0, "grades table empty"
        avg_table = grades.query_one("#subject-averages", DataTable)
        assert avg_table.row_count > 0, "subject averages empty"
        print("OK grades rows:", gtable.row_count, "subject avg rows:", avg_table.row_count)

        assignments = app.query_one(AssignmentsTab)
        atable = assignments.query_one("#assignments-table", DataTable)
        assert atable.row_count > 0, "assignments table empty"
        print("OK assignments rows:", atable.row_count)

        school_bar = app.query_one("#school-bar")
        assert demo.school_name in str(school_bar.render()), "school name not shown"
        print("OK school bar:", str(school_bar.render()).strip())

        tabs.active = "tab-grades"
        await pilot.pause()
        assert tabs.active == "tab-grades", "tab switch failed"
        print("OK tab switching works, active:", tabs.active)

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
