from __future__ import annotations

import asyncio

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Input

from ..auth import perform_login
from ..client import MagisterClient
from ..config import load_credentials, load_session, save_credentials, save_session, clear_session
from ..demo_data import DemoClient
from ..errors import TermisterError, NotAuthenticatedError
from .login_view import LoginView
from .main_view import MainView
from .theme import CSS
from .widgets import DataTab, NeedReauth


class TermisterApp(App[None]):
    TITLE = "Termister"
    SUB_TITLE = "Magister in je terminal"
    CSS = CSS
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Vernieuwen"),
        Binding("q", "quit", "Afsluiten"),
    ]

    def __init__(
        self,
        demo: bool = False,
        school: str | None = None,
        username: str | None = None,
        password: str | None = None,
        use_cache: bool = True,
        use_saved_credentials: bool = True,
    ):
        super().__init__()
        self.demo = demo
        self.cli_credentials = {"school": school, "username": username, "password": password}
        self.use_cache = use_cache
        self.use_saved_credentials = use_saved_credentials
        self.client = None
        self.school_name: str | None = None
        self._reauth_in_progress = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(id="root")
        yield Footer()

    def on_mount(self):
        self.run_worker(self._initialise(), name="init", group="startup")

    async def _initialise(self) -> None:
        if self.demo:
            self.client = DemoClient()
            self.school_name = DemoClient.school_name
            await self._show_main()
            return

        session = load_session() if self.use_cache else {}
        if session.get("api_url") and session.get("app_token") and session.get("person_id"):
            # If a refresh token exists, try to refresh the saved session so the app
            # doesn't immediately present an expired token. If refresh fails, fall
            # back to the saved app_token (it may still be valid).
            try:
                from ..auth import refresh_session

                new_app = refresh_session() if session.get("refresh_token") else None
            except Exception:
                new_app = None
            app_token = new_app or session["app_token"]
            self.client = MagisterClient(session["api_url"], app_token, session["person_id"])
            # Validate the token immediately so we don't show the main UI with a
            # broken/expired session. If validation fails, clear the saved
            # session and fall through to the login screen.
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
                await self._show_main()
                return

        creds = {k: v for k, v in (self.cli_credentials or {}).items() if v}
        if not creds and self.use_saved_credentials:
            creds = load_credentials()
        school = creds.get("school") or ""
        username = creds.get("username") or ""
        password = creds.get("password") or ""
        await self._show_login(school, username)
        if password:
            self.start_login(school, username, password)

    @on(Button.Pressed, "#login-submit")
    def _login_submit(self):
        login_view = self.query_one(LoginView)
        school, username, password = login_view.values()
        if not school or not username or not password:
            login_view.set_status("Vul schoolnaam, gebruikersnaam én wachtwoord in.", error=True)
            return
        self.start_login(school, username, password)

    @on(Button.Pressed, "#login-demo")
    def _login_demo(self):
        self.client = DemoClient()
        self.school_name = DemoClient.school_name
        self.run_worker(self._show_main(), name="demo", group="startup")

    @on(Input.Submitted, "#login-password")
    def _login_password_submitted(self):
        self._login_submit()

    def start_login(self, school: str, username: str, password: str) -> None:
        self._login_worker(school, username, password)

    @work(exclusive=True, group="login")
    async def _login_worker(self, school: str, username: str, password: str):
        login_view = self._get_login_view()
        if login_view:
            login_view.set_status("Inloggen…")
        try:
            result = await asyncio.to_thread(perform_login, school, username, password)
        except TermisterError as exc:
            if login_view:
                login_view.set_status(str(exc), error=True)
            return
        except Exception as exc:
            if login_view:
                login_view.set_status(f"Onverwachte fout: {exc}", error=True)
            return
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
        await self._show_main()

    @on(NeedReauth)
    def _handle_reauth(self):
        if self._reauth_in_progress:
            return
        self._reauth_in_progress = True
        creds = load_credentials() if self.use_saved_credentials else {}
        self.client = None
        self.run_worker(
            self._show_login(creds.get("school", ""), creds.get("username", "")),
            name="reauth",
            group="startup",
        )

    def action_refresh(self):
        for tab in self.query(DataTab):
            tab.run_worker(tab.reload(), name="reload", group="data", exclusive=True)

    def _get_login_view(self) -> LoginView | None:
        try:
            return self.query_one(LoginView)
        except Exception:
            return None

    async def _show_main(self) -> None:
        root = self.query_one("#root", Vertical)
        await root.remove_children()
        await root.mount(MainView(self.client, self.school_name))

    async def _show_login(self, school: str = "", username: str = "") -> None:
        root = self.query_one("#root", Vertical)
        await root.remove_children()
        await root.mount(LoginView(school, username))
