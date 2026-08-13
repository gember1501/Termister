from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Button, Input, Label, Static


class LoginView(Vertical):
    def __init__(self, school: str = "", username: str = "", password: str = ""):
        super().__init__()
        self._school = school
        self._username = username
        self._password = password

    def compose(self):
        with Vertical(id="login-box"):
            yield Static("Termister — Log in op Magister", id="login-title")
            yield Label("Schoolnaam (bijv. 'Erasmus College')")
            yield Input(self._school, id="login-school", placeholder="Schoolnaam")
            yield Label("Gebruikersnaam")
            yield Input(self._username, id="login-username", placeholder="Gebruikersnaam")
            yield Label("Wachtwoord")
            yield Input(
                self._password, id="login-password", placeholder="Wachtwoord", password=True
            )
            yield Button("Inloggen", id="login-submit", variant="primary")
            yield Button("Demo-data bekijken", id="login-demo")
            yield Static("", id="login-status")

    def set_status(self, message: str, error: bool = False) -> None:
        style = "red" if error else "yellow"
        self.query_one("#login-status", Static).update(f"[{style}]{message}[/{style}]")

    def values(self) -> tuple[str, str, str]:
        school = self.query_one("#login-school", Input).value.strip()
        username = self.query_one("#login-username", Input).value.strip()
        password = self.query_one("#login-password", Input).value
        return school, username, password
