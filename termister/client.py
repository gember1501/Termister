from __future__ import annotations

from datetime import date

import requests

from .errors import FetchError, NotAuthenticatedError
from .models import Assignment, Grade, Lesson


class MagisterClient:
    def __init__(self, api_url: str, app_token: str, person_id: str, http_session: requests.Session | None = None):
        self.api_url = api_url.rstrip("/")
        self.app_token = app_token
        self.person_id = person_id
        self.session = http_session or requests.Session()

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.api_url}{path}"
        response = self.session.get(
            url, params=params, headers={"authorization": self.app_token}, timeout=30
        )
        if response.status_code == 401:
            # Try to refresh the saved session once
            try:
                from .auth import refresh_session

                new_app_token = refresh_session()
            except Exception:
                new_app_token = None
            if new_app_token:
                # retry the request with the refreshed token
                self.app_token = new_app_token
                response = self.session.get(
                    url, params=params, headers={"authorization": self.app_token}, timeout=30
                )
                if response.status_code == 401:
                    raise NotAuthenticatedError("Sessie verlopen; start de app opnieuw op om opnieuw in te loggen.")
            else:
                raise NotAuthenticatedError("Sessie verlopen; start de app opnieuw op om opnieuw in te loggen.")
        if response.status_code != 200:
            raise FetchError(f"Magister gaf HTTP {response.status_code} terug voor {url}.")
        try:
            return response.json()
        except ValueError:
            raise FetchError(f"Magister gaf geen JSON terug voor {url}.") from None

    def schedule(self, from_date: date, to_date: date) -> list[Lesson]:
        data = self._get(
            f"/personen/{self.person_id}/afspraken",
            {"van": from_date.isoformat(), "tot": to_date.isoformat()},
        )
        return [Lesson.from_raw(item) for item in data.get("Items") or []]

    def grades(self, top: int = 200, skip: int = 0) -> list[Grade]:
        data = self._get(
            f"/personen/{self.person_id}/cijfers/laatste", {"top": top, "skip": skip}
        )
        return [Grade.from_raw(item) for item in data.get("items") or []]

    def assignments(self, top: int = 100) -> list[Assignment]:
        data = self._get(
            f"/personen/{self.person_id}/opdrachten",
            {"top": top, "skip": 0, "status": "alle"},
        )
        assignments = []
        for item in data.get("Items") or []:
            assignment_id = item.get("Id")
            if assignment_id is None:
                continue
            try:
                raw = self._get(f"/personen/{self.person_id}/opdrachten/{assignment_id}")
            except (FetchError, NotAuthenticatedError):
                continue
            assignments.append(Assignment.from_raw(raw))
        return assignments
