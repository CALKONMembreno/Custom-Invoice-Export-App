"""
Authentication for Command Alkon API (OAuth-style login + refresh).
Uses credentials from config (encrypted storage).
"""
import requests
import json
from typing import Optional

from .config import load_credentials

BASE_URL = "https://api.us.commandalkon.io/v4"
_headers: dict = {}
_refresh_token: str = ""
_access_token: str = ""


def _safe_json(response: requests.Response) -> dict:
    if not response.content:
        return {}
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text}


def _ensure_headers():
    global _headers
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured. Please set up credentials in Config.")
    if "x-api-key" not in _headers or _headers.get("x-api-key") != creds.get("apiKey"):
        _headers = {
            "accept": "application/json",
            "x-api-key": creds["apiKey"],
            "Content-Type": "application/json",
        }


def login_get_refresh_token() -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    _ensure_headers()
    payload = {
        "clientId": creds["clientId"],
        "clientSecret": creds["clientSecret"],
        "apiScopeRef": creds["apiScopeRef"],
    }
    auth_url = f"{BASE_URL}/services/authnz/{entity_ref}/api/login"
    auth = requests.post(auth_url, json=payload, headers=_headers, timeout=30)
    if auth.status_code != 200:
        raise RuntimeError(
            f"Authentication failed ({auth.status_code}). Check your credentials."
        )
    data = _safe_json(auth)
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh_token in login response.")
    return refresh_token


def refresh_access_token(refresh_token: str) -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    _ensure_headers()
    refresh_headers = {**_headers, "authorization": f"Bearer {refresh_token}"}
    refresh_url = f"{BASE_URL}/services/authnz/{entity_ref}/api/tokens/refresh-access-token"
    r = requests.get(refresh_url, headers=refresh_headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({r.status_code}). Try re-entering credentials.")
    data = _safe_json(r)
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("No access_token in refresh response.")
    return access_token


def ensure_access_token() -> None:
    global _refresh_token, _access_token, _headers
    _ensure_headers()
    if not _refresh_token:
        _refresh_token = login_get_refresh_token()
    _access_token = refresh_access_token(_refresh_token)
    _headers["authorization"] = f"Bearer {_access_token}"


def request_with_token_refresh(
    method: str, url: str, *, json_payload=None, params=None, timeout=30
) -> requests.Response:
    """Make request; on 401 refresh token and retry once."""
    ensure_access_token()
    response = requests.request(
        method, url, headers=_headers, json=json_payload, params=params, timeout=timeout
    )
    if response.status_code != 401:
        return response
    # Retry with fresh login/refresh
    global _refresh_token, _access_token
    try:
        _refresh_token = login_get_refresh_token()
        _access_token = refresh_access_token(_refresh_token)
        _headers["authorization"] = f"Bearer {_access_token}"
    except Exception:
        pass
    return requests.request(
        method, url, headers=_headers, json=json_payload, params=params, timeout=timeout
    )


def get_headers() -> dict:
    """Return current headers (with Bearer) for API calls. Call ensure_access_token() first."""
    ensure_access_token()
    return dict(_headers)
