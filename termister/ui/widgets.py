from __future__ import annotations

from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from ..errors import NotAuthenticatedError


class NeedReauth(Message):
    pass


class DataTab(Vertical):
    def __init__(self, client):
        super().__init__()
        self.client = client

    def compose(self):
        yield Static("", id="tab-status")
        yield VerticalScroll(id="tab-content")

    def on_mount(self):
        self.run_worker(self.reload(), name="reload", group="data", exclusive=True)

    async def reload(self):
        self._set_status("Bezig met laden…")
        try:
            await self.fetch_and_render()
            self._set_status("")
        except NotAuthenticatedError as exc:
            self._set_status("")
            await self._show_error(str(exc))
            self.post_message(NeedReauth())
        except Exception as exc:
            self._set_status("")
            await self._show_error(str(exc))

    async def fetch_and_render(self):
        raise NotImplementedError

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#tab-status", Static).update(message)
        except Exception:
            pass

    async def _show_error(self, message: str) -> None:
        content = await self._clear_content()
        await content.mount(Static(f"[red]{message}[/red]"))

    async def _clear_content(self) -> VerticalScroll:
        content = self.query_one("#tab-content", VerticalScroll)
        await content.remove_children()
        return content
