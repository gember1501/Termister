from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

APPOINTMENT_TYPES = {
    0: "Geen",
    1: "Persoonlijk",
    2: "Algemeen",
    3: "School breed",
    4: "Stage",
    5: "Intake",
    6: "Roostervrij",
    7: "Kwt",
    8: "Standby",
    9: "Blokkade",
    10: "Overig",
    11: "Blokkade lokaal",
    12: "Blokkade klas",
    13: "Les",
    14: "Studiehuis",
    15: "Roostervrije studie",
    16: "Planning",
    101: "Maatregelen",
    102: "Presentaties",
    103: "Examen rooster",
}

INFO_TYPES = {
    0: "Geen",
    1: "Huiswerk",
    2: "Proefwerk",
    3: "Tentamen",
    4: "Schriftelijke overhoring",
    5: "Mondelinge overhoring",
    6: "Informatie",
    7: "Aantekening",
}

STATUS_TYPES = {
    0: "Onbekend",
    1: "Automatisch geroosterd",
    2: "Handmatig geroosterd",
    3: "Gewijzigd",
    4: "Vervallen (handmatig)",
    5: "Vervallen (automatisch)",
    6: "In gebruik",
    7: "Afgesloten",
    8: "Ingezet",
    9: "Verplaatst",
    10: "Gewijzigd en verplaatst",
}

TEST_INFO_TYPES = (2, 3, 4, 5)


def parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def person_name(p) -> str:
    if isinstance(p, str):
        return p
    if not isinstance(p, dict):
        return str(p)
    for key in ("Naam", "NaamDocent", "VolledigeNaam", "DisplayNaam", "Omschrijving"):
        value = p.get(key)
        if value:
            return str(value)
    first = p.get("Roepnaam") or p.get("Voornaam") or p.get("Voorletters") or ""
    last = p.get("Achternaam") or ""
    if first or last:
        return (str(first) + " " + str(last)).strip()
    return p.get("Docentcode") or p.get("Code") or str(p.get("Id") or "?")


def list_names(items) -> list[str]:
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            out.append(str(item))
            continue
        name = item.get("Naam") or item.get("Omschrijving")
        if name:
            out.append(str(name))
    return out


def room_numbers(rooms: list[str]) -> str:
    """Rooms as plain room numbers: strip 'Lokaal', building and floor codes."""
    cleaned: list[str] = []
    for room in rooms:
        value = str(room).strip()
        match = re.search(r"(?i)lokaal", value)
        if match:
            value = value[match.end():].split(",")[0].strip()
        else:
            value = value.split(",")[0].strip()
        if not value:
            continue
        numbers = re.findall(r"\d+", value)
        if not numbers:
            cleaned.append(value)
        elif "." in value or "/" in value:
            cleaned.append(numbers[-1])
        else:
            cleaned.append(numbers[0])
    return ", ".join(cleaned)


@dataclass
class Lesson:
    id: str = ""
    start: datetime | None = None
    end: datetime | None = None
    period_start: int | None = None
    period_end: int | None = None
    full_day: bool = False
    description: str = ""
    location: str = ""
    content: str = ""
    annotation: str = ""
    done: bool = False
    subjects: list[str] = field(default_factory=list)
    teachers: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    type_id: int | None = None
    info_type: int | None = None
    status: int | None = None
    is_cancelled: bool = False
    is_changed: bool = False

    @classmethod
    def from_raw(cls, raw: dict) -> "Lesson":
        status = raw.get("Status")
        return cls(
            id=str(raw.get("Id") or ""),
            start=parse_dt(raw.get("Start")),
            end=parse_dt(raw.get("Einde")),
            period_start=raw.get("LesuurVan"),
            period_end=raw.get("LesuurTotMet"),
            full_day=bool(raw.get("DuurtHeleDag")),
            description=(raw.get("Omschrijving") or "").strip(),
            location=(raw.get("Lokatie") or "").strip(),
            content=raw.get("Inhoud") or "",
            annotation=raw.get("Aantekening") or "",
            done=bool(raw.get("Afgerond")),
            subjects=list_names(raw.get("Vakken")),
            teachers=[person_name(p) for p in (raw.get("Docenten") or [])],
            rooms=list_names(raw.get("Lokalen")),
            groups=list_names(raw.get("Groepen")),
            type_id=raw.get("Type"),
            info_type=raw.get("InfoType"),
            status=status,
            is_cancelled=status in (4, 5),
            is_changed=status in (3, 9, 10),
        )

    @property
    def is_test(self) -> bool:
        return self.info_type in TEST_INFO_TYPES

    @property
    def subject(self) -> str:
        return self.description or (", ".join(self.subjects) if self.subjects else "—")


@dataclass
class Grade:
    id: str = ""
    subject: str = ""
    subject_code: str = ""
    description: str = ""
    value: str = ""
    numeric_value: float | None = None
    weight: float = 0.0
    passed: bool = True
    counts: bool = True
    entered: datetime | None = None
    achieved: datetime | None = None
    must_retake: bool = False
    exemption: bool = False

    @classmethod
    def from_raw(cls, raw: dict) -> "Grade":
        vak = raw.get("vak") or raw.get("Vak") or {}
        if isinstance(vak, dict):
            subject = vak.get("omschrijving") or vak.get("Naam") or ""
            code = vak.get("code") or vak.get("Afkorting") or ""
        else:
            subject, code = "", ""
        value = raw.get("waarde") or raw.get("CijferStr") or raw.get("Cijfer") or ""
        numeric = _to_float(value)
        if numeric is None:
            numeric = _to_float(raw.get("Cijfer"))
        return cls(
            id=str(raw.get("CijferId") or raw.get("id") or ""),
            subject=str(subject or ""),
            subject_code=str(code or ""),
            description=str(raw.get("omschrijving") or raw.get("Omschrijving") or "").strip(),
            value=str(value),
            numeric_value=numeric,
            weight=_to_float(raw.get("weegfactor") or raw.get("Weging") or 0) or 0.0,
            passed=bool(raw.get("isVoldoende") if "isVoldoende" in raw else raw.get("IsVoldoende", True)),
            counts=bool(raw.get("teltMee") if "teltMee" in raw else raw.get("TeltMee", True)),
            entered=parse_dt(raw.get("ingevoerdOp") or raw.get("DatumIngevoerd")),
            achieved=parse_dt(raw.get("behaaldOp") or raw.get("DatumBehaald")),
            must_retake=bool(raw.get("moetInhalen") if "moetInhalen" in raw else raw.get("Inhalen", False)),
            exemption=bool(raw.get("heeftVrijstelling") if "heeftVrijstelling" in raw else raw.get("Vrijstelling", False)),
        )

    @property
    def label(self) -> str:
        return self.value if self.value else "—"


@dataclass
class Assignment:
    id: str = ""
    title: str = ""
    description: str = ""
    subject: str = ""
    deadline: datetime | None = None
    handed_in_on: datetime | None = None
    teachers: list[str] = field(default_factory=list)
    grade: str = ""
    marked_on: datetime | None = None
    can_hand_in: bool = False
    finished: bool = False
    hand_in_again: bool = False

    @classmethod
    def from_raw(cls, raw: dict) -> "Assignment":
        vak = raw.get("Vak") or {}
        if isinstance(vak, dict):
            subject = vak.get("Naam") or vak.get("Omschrijving") or ""
        else:
            subject = str(vak)
        return cls(
            id=str(raw.get("Id") or ""),
            title=str(raw.get("Titel") or "").strip(),
            description=str(raw.get("Omschrijving") or "").strip(),
            subject=str(subject),
            deadline=parse_dt(raw.get("InleverenVoor") or raw.get("EindTijd")),
            handed_in_on=parse_dt(raw.get("IngeleverdOp")),
            teachers=[person_name(p) for p in (raw.get("Docenten") or [])],
            grade=str(raw.get("Beoordeling") or ""),
            marked_on=parse_dt(raw.get("BeoordeeldOp")),
            can_hand_in=bool(raw.get("MagInleveren")),
            finished=bool(raw.get("Afgesloten")),
            hand_in_again=bool(raw.get("OpnieuwInleveren")),
        )

    @property
    def status_text(self) -> str:
        if self.finished:
            return "afgesloten"
        if self.hand_in_again:
            return "opnieuw inleveren"
        if self.handed_in_on:
            return "ingeleverd"
        if self.can_hand_in:
            return "in te leveren"
        return "—"


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None
