from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .errors import LoginError
from .config import load_session, save_session, clear_session

USER_AGENT = "Termister/0.1 (Magister terminal client)"

ACCOUNTS_BASE = "https://accounts.magister.net"
AUTHORIZE_URL = f"{ACCOUNTS_BASE}/connect/authorize"
TOKEN_ENDPOINT = f"{ACCOUNTS_BASE}/connect/token"

M6LOAPP_CLIENT = "M6LOAPP"
M6LOAPP_REDIRECT = "m6loapp://oauth2redirect/"
M6LOAPP_SCOPE = "openid profile offline_access"

AUTHCODE_MARKER = "].map((function(t)"
AUTHCODE_BUFFER = 200


@dataclass
class AuthResult:
    api_url: str
    app_token: str
    person_id: str
    school_name: str
    refresh_token: str | None = None


def perform_login(school_name: str, username: str, password: str, session: requests.Session | None = None) -> AuthResult:
    http = session or requests.Session()
    http.headers.setdefault("User-Agent", USER_AGENT)
    try:
        return _login(http, school_name, username, password)
    except LoginError:
        raise
    except requests.RequestException as exc:
        raise LoginError(f"Netwerkfout tijdens inloggen: {exc}") from exc
    except Exception as exc:
        raise LoginError(f"Onverwachte fout tijdens inloggen: {exc}") from exc


def _login(http: requests.Session, school_name: str, username: str, password: str) -> AuthResult:
    http.get(ACCOUNTS_BASE + "/", allow_redirects=False, timeout=30)

    verifier, challenge = _pkce_pair()
    response, session_id, return_url = _open_login_page(http, school_name, challenge)
    if not session_id or not return_url:
        raise LoginError("Kon de inlogsessie niet starten (sessionId ontbreekt).")

    authcode = _fetch_authcode(http, response.url, response.text)

    base_payload = {
        "authCode": authcode,
        "returnUrl": return_url,
        "sessionId": session_id,
    }

    _submit_challenge(http, "username", {**base_payload, "username": username})
    body = _submit_challenge(
        http,
        "password",
        {
            **base_payload,
            "password": password,
            "userWantsToPairSoftToken": False,
            "userSkippedFido": True,
        },
    )

    redirect_url = _finish_challenge_flow(http, base_payload, body)
    code = _obtain_code(http, redirect_url)
    access_token, refresh_token = _exchange_code(http, code, verifier)

    tenant = _tenant(school_name)
    api_url = f"https://{tenant}.magister.net/api"
    app_token = "Bearer " + access_token
    person_id = _account_person_id(http, api_url, app_token)

    return AuthResult(api_url, app_token, person_id, school_name, refresh_token)


def _finish_challenge_flow(http: requests.Session, base_payload: dict, body: dict) -> str:
    for _ in range(5):
        if body.get("redirectURL"):
            return str(body["redirectURL"])
        if body.get("error"):
            raise LoginError(str(body["error"]))
        action = body.get("action")
        if action == "pairfidopromo":
            body = _submit_challenge(
                http,
                "skip-pair-fido-promo",
                {
                    **base_payload,
                    "reason": "browser-not-supported",
                    "userVerifyingPlatformAuthenticator": None,
                },
            )
            continue
        if action in ("softtoken", "hard-token"):
            raise LoginError(
                "Dit account vereist twee-factor-authenticatie (tokencode), die Termister nog niet ondersteunt."
            )
        raise LoginError(f"Onverwachte inlogstap '{action}'. Probeer het later opnieuw.")
    raise LoginError("De login kon niet worden afgerond; probeer het opnieuw.")


def _open_login_page(http: requests.Session, school_name: str, code_challenge: str) -> tuple[requests.Response, str, str]:
    for attempt in range(3):
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)
        params = _authorize_params(school_name, code_challenge, state, nonce)
        response = http.get(AUTHORIZE_URL, params=params, allow_redirects=False, timeout=30)
        location = response.headers.get("Location")
        if not location:
            raise LoginError("Kon de loginpagina niet bereiken.")
        response = http.get(location, allow_redirects=False, timeout=30)
        location = response.headers.get("Location")
        if not location:
            if response.status_code >= 500 and attempt < 2:
                continue
            raise LoginError("Kon de loginpagina niet bereiken.")
        if location.startswith("/"):
            location = ACCOUNTS_BASE + location
        response = http.get(location, allow_redirects=False, timeout=30)
        if response.status_code >= 500 and attempt < 2:
            continue
        query = parse_qs(urlparse(response.url).query)
        session_id = (query.get("sessionId") or [None])[0]
        return_url = (query.get("returnUrl") or [None])[0]
        return response, session_id, return_url
    raise LoginError("De loginpagina reageerde niet goed; probeer het nog eens.")


def _tenant(school_name: str) -> str:
    tenant = school_name.strip().lower()
    if tenant.endswith(".magister.net"):
        tenant = tenant[: -len(".magister.net")]
    return tenant


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _authorize_params(school_name: str, code_challenge: str, state: str, nonce: str) -> dict:
    return {
        "client_id": M6LOAPP_CLIENT,
        "redirect_uri": M6LOAPP_REDIRECT,
        "response_type": "code id_token",
        "scope": M6LOAPP_SCOPE,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "acr_values": f"tenant:{_tenant(school_name)}.magister.net",
        "prompt": "select_account",
    }


def _obtain_code(http: requests.Session, url: str) -> str:
    code = _code_from_url(url)
    if not code:
        url = urljoin(ACCOUNTS_BASE + "/", url)
        response = http.get(url, allow_redirects=False, timeout=30)
        code = _code_from_url(response.headers.get("Location", ""))
    if not code:
        raise LoginError("De login kon niet worden afgerond (geen autorisatiecode ontvangen).")
    return code


def _code_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    params = parse_qs(parsed.fragment) or parse_qs(parsed.query)
    values = params.get("code")
    return values[0] if values else None


def _exchange_code(http: requests.Session, code: str, code_verifier: str) -> tuple[str, str | None]:
    response = http.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": M6LOAPP_REDIRECT,
            "client_id": M6LOAPP_CLIENT,
            "code_verifier": code_verifier,
        },
        headers={"accept": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise LoginError(f"Het toegangstoken kon niet worden uitgewisseld (HTTP {response.status_code}).")
    try:
        data = response.json()
    except ValueError:
        data = {}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token:
        raise LoginError("Het toegangstoken kon niet worden uitgewisseld.")
    return access_token, refresh_token


def _refresh_access_token(http: requests.Session, refresh_token: str) -> tuple[str, str | None]:
    response = http.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": M6LOAPP_CLIENT,
        },
        headers={"accept": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise LoginError(f"Het refresh-token kon niet worden ingewisseld (HTTP {response.status_code}).")
    try:
        data = response.json()
    except ValueError:
        data = {}
    access_token = data.get("access_token")
    new_refresh = data.get("refresh_token")
    if not access_token:
        raise LoginError("Het refresh-token kon niet worden ingewisseld.")
    return access_token, new_refresh


def refresh_session() -> str | None:
    """Try to refresh the saved session using the stored refresh token.

    Returns the new app_token (Bearer ...) on success, or None on failure.
    """
    session = load_session()
    refresh = session.get("refresh_token")
    if not refresh:
        return None
    http = requests.Session()
    http.headers.setdefault("User-Agent", USER_AGENT)
    try:
        access_token, new_refresh = _refresh_access_token(http, refresh)
    except Exception:
        try:
            clear_session()
        except Exception:
            pass
        return None
    app_token = "Bearer " + access_token
    session.update({"app_token": app_token})
    if new_refresh:
        session["refresh_token"] = new_refresh
    save_session(session)
    return app_token


def _account_person_id(http: requests.Session, api_url: str, app_token: str) -> str:
    response = http.get(
        f"{api_url}/account", headers={"authorization": app_token}, timeout=30
    )
    if response.status_code != 200:
        raise LoginError("De sessie kon niet worden gevalideerd bij Magister.")
    try:
        return str(response.json()["Persoon"]["Id"])
    except (KeyError, TypeError, ValueError):
        raise LoginError("De sessie kon niet worden gevalideerd bij Magister.") from None


def _headers(http: requests.Session) -> dict:
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": ACCOUNTS_BASE,
        "x-xsrf-token": http.cookies.get("XSRF-TOKEN") or "",
    }


def _submit_challenge(http: requests.Session, kind: str, payload: dict) -> dict:
    response = http.post(
        f"{ACCOUNTS_BASE}/challenges/{kind}", json=payload, headers=_headers(http), timeout=30
    )
    if response.status_code != 200:
        raise LoginError(_challenge_error_message(response, kind))
    try:
        return response.json()
    except ValueError:
        return {}


def _challenge_error_message(response: requests.Response, kind: str) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {}
    text = body.get("Message") or body.get("message") or body.get("error_description")
    if text:
        return str(text)
    if response.status_code == 401:
        if kind == "password":
            return "Onjuist wachtwoord, of er staat een login-cooldown op dit account."
        return f"Onjuiste {kind}-gegevens."
    if response.status_code == 429:
        return "Te veel inlogpogingen. Wacht even en probeer opnieuw."
    return f"Inlogstap '{kind}' mislukt (HTTP {response.status_code})."


def _fetch_authcode(http: requests.Session, page_url: str, page_html: str) -> str:
    soup = BeautifulSoup(page_html, "html.parser")
    script = soup.find("script", {"defer": "defer"})
    src = script.get("src") if script else None
    if not src:
        raise LoginError("Kon het login-script niet vinden.")
    src = str(src)
    candidates = [urljoin(page_url, src)]
    if not candidates[0].startswith("http"):
        candidates[0] = "https:" + candidates[0]
    if not src.startswith(("http://", "https://")):
        candidates.append(ACCOUNTS_BASE + "/" + src.lstrip("/"))
    response = None
    for candidate in dict.fromkeys(candidates):
        response = http.get(candidate, timeout=30)
        if response.status_code == 200:
            break
    else:
        raise LoginError("Kon het login-script niet downloaden.")
    authcode = _extract_authcode(response.text)
    if not authcode:
        raise LoginError("Kon de inlogsleutel niet extraheren.")
    return authcode


def _extract_authcode(js_content: str) -> str | None:
    index = js_content.find(AUTHCODE_MARKER)
    if index < 0:
        return None
    chunk = js_content[max(0, index + 1 - AUTHCODE_BUFFER): index + 1]
    last_bracket = chunk.rfind("[")
    if last_bracket < 0:
        return None
    previous_bracket = chunk.rfind("[", 0, last_bracket)
    if previous_bracket < 0:
        return None
    segment = chunk[previous_bracket:]
    lists: list[list] = []
    start: int | None = None
    for position, char in enumerate(segment):
        if char == "[":
            start = position
        elif char == "]" and start is not None:
            try:
                lists.append(json.loads(segment[start:position + 1]))
            except ValueError:
                pass
            start = None
        if len(lists) >= 2:
            break
    if len(lists) < 2:
        return None
    characters, indexes = lists[0], lists[1]
    try:
        return "".join(str(characters[int(index)]) for index in indexes)
    except (IndexError, TypeError, ValueError):
        return None
