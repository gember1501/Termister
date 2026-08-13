from __future__ import annotations

import json
import os
from pathlib import Path

SESSION_FILENAME = "session.json"
CREDENTIALS_FILENAME = "credentials.json"
SETTINGS_FILENAME = "settings.json"
DEFAULT_SETTINGS = {"verkort_lokaalnummers": True, "max_periods": 7}


def config_dir() -> Path:
    override = os.environ.get("TERMISTER_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "termister"


def _path(filename: str) -> Path:
    path = config_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_session() -> dict:
    try:
        return json.loads(_path(SESSION_FILENAME).read_text())
    except (OSError, ValueError):
        return {}


def save_session(session: dict) -> None:
    path = _path(SESSION_FILENAME)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_session() -> None:
    try:
        _path(SESSION_FILENAME).unlink()
    except OSError:
        pass


def load_credentials() -> dict:
    try:
        return json.loads(_path(CREDENTIALS_FILENAME).read_text())
    except (OSError, ValueError):
        return {}


def save_credentials(school: str, username: str) -> None:
    path = _path(CREDENTIALS_FILENAME)
    path.write_text(json.dumps({"school": school, "username": username}, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)
    try:
        merged.update(json.loads(_path(SETTINGS_FILENAME).read_text()))
    except (OSError, ValueError):
        pass
    return merged


def save_settings(settings: dict) -> None:
    path = _path(SETTINGS_FILENAME)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
