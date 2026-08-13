from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Assignment, Grade, Lesson

SCHOOL_NAME = "Demo College"

PERIODS = {
    1: ("08:30", "09:15"),
    2: ("09:15", "10:00"),
    3: ("10:15", "11:00"),
    4: ("11:00", "11:45"),
    5: ("12:15", "13:00"),
    6: ("13:00", "13:45"),
    7: ("14:00", "14:45"),
    8: ("14:45", "15:30"),
}


def _dt(day: date, time_str: str) -> datetime:
    hour, minute = (int(p) for p in time_str.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def _lesson(day: date, period_start: int, period_end: int, subject: str, teacher: str, room: str,
            info_type: int = 0, status: int = 1) -> Lesson:
    start_str, _ = PERIODS[period_start]
    _, end_str = PERIODS[period_end]
    return Lesson(
        id=f"{day.isoformat()}-{subject}-{period_start}",
        start=_dt(day, start_str),
        end=_dt(day, end_str),
        period_start=period_start,
        period_end=period_end,
        description=subject,
        location=room,
        subjects=[subject],
        teachers=[teacher],
        rooms=[room],
        type_id=13,
        info_type=info_type,
        status=status,
        is_cancelled=status in (4, 5),
        is_changed=status in (3, 9, 10),
    )


def _full_day_lesson(day: date, subject: str, teacher: str = "Mw. De Vries") -> Lesson:
    return Lesson(
        id=f"{day.isoformat()}-fullday",
        start=_dt(day, "08:00"),
        end=_dt(day, "16:00"),
        period_start=None,
        period_end=None,
        full_day=True,
        description=subject,
        subjects=[subject],
        teachers=[teacher],
        rooms=[],
        info_type=0,
        status=1,
    )


def demo_lessons(from_date: date, to_date: date) -> list[Lesson]:
    lessons = []
    monday = from_date - timedelta(days=from_date.weekday())
    days = [
        ("Ma", [
            (1, 2, "Nederlands", "Dhr. Jansen", "12"),
            (3, 3, "Wiskunde", "Mw. De Vries", "34", 2),
            (4, 5, "Engels", "Dhr. Bakker", "8"),
            (6, 7, "Natuurkunde", "Mw. Smit", "15"),
        ]),
        ("Di", [
            (1, 1, "Geschiedenis", "Dhr. Van Dijk", "22"),
            (2, 3, "Wiskunde", "Mw. De Vries", "34"),
            (4, 4, "Biologie", "Mw. Jansen", "9"),
            (5, 6, "Lichamelijke Opvoeding", "Dhr. Kok", "Sporthal"),
            (7, 8, "Duits", "Mw. Peters", "5", 4),
        ]),
        ("Wo", [
            (1, 2, "Economie", "Dhr. Visser", "11"),
            (3, 4, "Nederlands", "Dhr. Jansen", "12"),
            (5, 5, "Scheikunde", "Mw. Smit", "18", 0, 4),
            (6, 8, "Informatica", "Dhr. Bos", "Lokaal 27"),
        ]),
        ("Do", [
            (1, 2, "Engels", "Dhr. Bakker", "8"),
            (3, 4, "Natuurkunde", "Mw. Smit", "15"),
            (5, 5, "Wiskunde", "Mw. De Vries", "34"),
            (6, 7, "Maatschappijleer", "Mw. Peters", "5"),
        ]),
        ("Vr", [
            (1, 1, "Frans", "Mw. Lambers", "3"),
            (2, 3, "Geschiedenis", "Dhr. Van Dijk", "22", 2),
            (4, 5, "Mentoruur", "Mw. De Vries", "34"),
        ]),
    ]
    for offset, (_, plan) in enumerate(days):
        day = monday + timedelta(days=offset)
        if not (from_date <= day <= to_date):
            continue
        for entry in plan:
            period_start, period_end = entry[0], entry[1]
            subject, teacher, room = entry[2], entry[3], entry[4]
            info_type = entry[5] if len(entry) > 5 else 0
            status = entry[6] if len(entry) > 6 else 1
            lessons.append(_lesson(day, period_start, period_end, subject, teacher, room, info_type, status))
        if day.weekday() == 3:
            lessons.append(_full_day_lesson(day, "Excursie Natuurmuseum"))
    return lessons


_GRADE_SET = [
    ("Nederlands", "NE", "Leesvaardigheid", "7.4", 3),
    ("Nederlands", "NE", "Boekverslag", "6.8", 2),
    ("Engels", "EN", "So woorden", "5.5", 1),
    ("Engels", "EN", "Leestoets", "7.1", 3),
    ("Wiskunde", "WI", "Proefwerk hst 4", "6.2", 3),
    ("Wiskunde", "WI", "Repetitie hst 5", "4.8", 3),
    ("Natuurkunde", "NA", "Toets krachten", "7.8", 3),
    ("Natuurkunde", "NA", "Practicumverslag", "8.2", 2),
    ("Geschiedenis", "GS", "Toets Romeinen", "6.9", 2),
    ("Biologie", "BI", "So cellen", "7.0", 1),
    ("Economie", "EC", "Repetitie geld", "5.9", 2),
    ("Scheikunde", "SK", "Toets stoffen", "7.6", 2),
    ("Duits", "DU", "So grammatica", "6.3", 1),
    ("Frans", "FA", "Luistertoets", "6.1", 2),
    ("Informatica", "INF", "Opdracht HTML", "8.7", 1),
    ("Maatschappijleer", "MA", "Presentatie", "7.9", 1),
]


def demo_grades(top: int = 100, skip: int = 0) -> list[Grade]:
    grades = []
    today = date.today()
    for index, (subject, code, description, value, weight) in enumerate(_GRADE_SET):
        numeric = float(value)
        grades.append(
            Grade(
                id=str(index),
                subject=subject,
                subject_code=code,
                description=description,
                value=value,
                numeric_value=numeric,
                weight=float(weight),
                passed=numeric >= 5.5,
                counts=True,
                entered=_dt(today - timedelta(days=index * 3), "15:30"),
            )
        )
    return sorted(grades, key=lambda g: g.entered, reverse=True)


def demo_assignments() -> list[Assignment]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [
        Assignment(
            id="a1", title="Leesvaardigheid oefenen",
            subject="Nederlands", deadline=_dt(today - timedelta(days=1), "23:59"),
            teachers=["Dhr. Jansen"], handed_in_on=_dt(today - timedelta(days=2), "20:15"),
            can_hand_in=False, finished=True, grade="7.4",
        ),
        Assignment(
            id="a2", title="Proefwerk hoofdstuk 5",
            subject="Wiskunde", deadline=_dt(monday + timedelta(days=1), "10:00"),
            teachers=["Mw. De Vries"], can_hand_in=True,
        ),
        Assignment(
            id="a3", title="Verslag proef krachten",
            subject="Natuurkunde", deadline=_dt(monday + timedelta(days=2), "17:00"),
            teachers=["Mw. Smit"], can_hand_in=True,
        ),
        Assignment(
            id="a4", title="Leestoets voorbereiden",
            subject="Engels", deadline=_dt(monday + timedelta(days=3), "09:00"),
            teachers=["Dhr. Bakker"], can_hand_in=True,
        ),
        Assignment(
            id="a5", title="SO grammatica Duits",
            subject="Duits", deadline=_dt(monday + timedelta(days=3), "10:15"),
            teachers=["Mw. Peters"], can_hand_in=True,
        ),
        Assignment(
            id="a6", title="Essay Romeinen",
            subject="Geschiedenis", deadline=_dt(monday + timedelta(days=4), "12:00"),
            teachers=["Dhr. Van Dijk"], can_hand_in=True,
        ),
        Assignment(
            id="a7", title="Werkstuk economie",
            subject="Economie", deadline=_dt(monday + timedelta(days=8), "17:00"),
            teachers=["Dhr. Visser"], can_hand_in=True,
        ),
        Assignment(
            id="a8", title="Opdracht HTML/CSS",
            subject="Informatica", deadline=_dt(monday + timedelta(days=6), "16:00"),
            teachers=["Dhr. Bos"], handed_in_on=_dt(monday + timedelta(days=5), "19:30"),
            can_hand_in=False, finished=False, grade="8.7",
        ),
    ]


class DemoClient:
    school_name = SCHOOL_NAME

    def schedule(self, from_date: date, to_date: date) -> list[Lesson]:
        return demo_lessons(from_date, to_date)

    def grades(self, top: int = 100, skip: int = 0) -> list[Grade]:
        return demo_grades(top, skip)

    def assignments(self) -> list[Assignment]:
        return demo_assignments()
