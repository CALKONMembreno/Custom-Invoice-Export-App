"""app.api

Command Alkon API client helpers.

- Invoices: paginated endpoint (dateOption or start/end range)
- Billables: non-paginated endpoint, with an attempted paginated variant
- Tickets: paginated endpoint (supports dateField, dateOption or start/end range)
"""
import requests
from typing import Iterator, Any, Optional

from .auth import request_with_token_refresh
from .config import load_credentials

BASE_URL = "https://api.us.commandalkon.io/v4"

DATE_OPTIONS = [
    "Today",
    "Yesterday",
    "Tomorrow",
    "This_Week",
    "Last_3_Days",
    "Last_7_Days",
    "Last_30_Days",
    "This_Month",
    "Last_Month",
    "Last_3_Months",
    "Last_6_Months",
    "Last_12_Months",
    "Last_12_Hours",
    "Last_18_Hours",
    "Last_24_Hours",
    "This_Year",
    "Last_Year",
]


def _safe_json(response: requests.Response) -> dict | list:
    if not response.content:
        return {}
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text}


def _iter_paginated(
    url: str,
    *,
    base_params: Optional[dict[str, str]] = None,
    timeout: int = 60,
) -> Iterator[dict | list]:
    """Yield pages for endpoints that return a page token.

    The API commonly returns `pageToken` (or `nextPageToken`). We stop when missing
    or when a token repeats.
    """
    page_token: Optional[str] = None
    seen_tokens: set[str] = set()

    while True:
        params: dict[str, str] = dict(base_params or {})
        if page_token:
            if page_token in seen_tokens:
                break
            seen_tokens.add(page_token)
            params["pageToken"] = page_token

        response = request_with_token_refresh("GET", url, params=params, timeout=timeout)
        data = _safe_json(response)
        if response.status_code != 200:
            raise RuntimeError(f"API error {response.status_code}: {data}")

        yield data

        if isinstance(data, dict):
            page_token = data.get("pageToken") or data.get("nextPageToken")
        else:
            page_token = None
        if not page_token:
            break


def get_invoices_paginated(
    date_option: Optional[str] = "Yesterday",
    filtered_fields: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Iterator[dict]:
    """
    Yield pages of invoice data. Use either date_option (e.g. 'Yesterday') or
    start_date/end_date (ISO-8601), not both. When start_date and end_date are
    both set, they are used; otherwise date_option is used.
    """
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    url = f"{BASE_URL}/services/billing/{entity_ref}/invoices/paginated"

    base_params: dict[str, str] = {
        "filteredFields": "true" if filtered_fields else "false",
    }

    use_range = start_date and end_date
    if use_range:
        base_params["startDate"] = str(start_date)
        base_params["endDate"] = str(end_date)
    else:
        base_params["dateOption"] = str(date_option or "Yesterday")

    for page in _iter_paginated(url, base_params=base_params, timeout=60):
        if isinstance(page, dict) or isinstance(page, list):
            yield page


def fetch_all_invoice_items(
    date_option: Optional[str] = "Yesterday",
    filtered_fields: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch all invoice items. Use either date_option or start_date+end_date (ISO-8601), not both."""
    all_items: list = []
    for page in get_invoices_paginated(
        date_option=date_option,
        filtered_fields=filtered_fields,
        start_date=start_date,
        end_date=end_date,
    ):
        items = page.get("items") if isinstance(page, dict) else []
        if isinstance(items, list):
            all_items.extend(items)
    return all_items


def get_billables_paginated(
    date_option: Optional[str] = "Yesterday",
    filtered_fields: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Iterator[dict]:
    """Yield pages of billables if the tenant supports a paginated endpoint.

    Some environments expose `/billables/paginated`. If this endpoint is not available,
    callers should fall back to the non-paginated `fetch_all_billables`.
    """
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    url = f"{BASE_URL}/services/billing/{entity_ref}/billables/paginated"

    base_params: dict[str, str] = {
        "filteredFields": "true" if filtered_fields else "false",
    }
    use_range = start_date and end_date
    if use_range:
        base_params["startDate"] = str(start_date)
        base_params["endDate"] = str(end_date)
    else:
        if date_option:
            base_params["dateOption"] = str(date_option)

    # If this endpoint 404s or errors, bubble up so the caller can decide to fall back.
    for page in _iter_paginated(url, base_params=base_params, timeout=60):
        if isinstance(page, dict):
            yield page


def fetch_all_billables(
    date_option: Optional[str] = "Yesterday",
    filtered_fields: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch billables.

    The billables endpoint shape is not guaranteed to match invoices. This helper attempts
    to normalize common shapes (list response, or dict with items/billables/data list).

    Parameters mirror invoices for a consistent UI, but the API may accept a different
    set depending on tenant/version.
    """
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    url = f"{BASE_URL}/services/billing/{entity_ref}/billables"

    params: dict[str, str] = {
        "filteredFields": "true" if filtered_fields else "false",
    }
    use_range = start_date and end_date
    if use_range:
        params["startDate"] = str(start_date)
        params["endDate"] = str(end_date)
    else:
        if date_option:
            params["dateOption"] = str(date_option)

    response = request_with_token_refresh("GET", url, params=params, timeout=60)
    data = _safe_json(response)
    if response.status_code != 200:
        raise RuntimeError(f"Billables API error {response.status_code}: {data}")

    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]

    if isinstance(data, dict):
        for key in ("items", "billables", "data"):
            maybe = data.get(key)
            if isinstance(maybe, list):
                return [d for d in maybe if isinstance(d, dict)]
        # If it's a single object, wrap it.
        return [data]

    return []


def fetch_all_billable_items(
    date_option: Optional[str] = "Yesterday",
    filtered_fields: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch all billables, preferring a paginated endpoint if available."""
    all_items: list[dict[str, Any]] = []
    try:
        for page in get_billables_paginated(
            date_option=date_option,
            filtered_fields=filtered_fields,
            start_date=start_date,
            end_date=end_date,
        ):
            if not isinstance(page, dict):
                continue
            for key in ("items", "billables", "data"):
                maybe = page.get(key)
                if isinstance(maybe, list):
                    all_items.extend([d for d in maybe if isinstance(d, dict)])
                    break
        if all_items:
            return all_items
    except Exception:
        # Silent fallback to the non-paginated endpoint.
        pass

    return fetch_all_billables(
        date_option=date_option,
        filtered_fields=filtered_fields,
        start_date=start_date,
        end_date=end_date,
    )


def get_tickets_paginated(
    date_field: str = "modifyDate",
    date_option: Optional[str] = "Yesterday",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Iterator[dict]:
    """Yield pages of dispatch tickets.

    Endpoint example:
    `/v4/services/dispatch/<entityRef>/tickets/paginated?dateField=modifyDate`

    Supports either:
    - `startDate` + `endDate` (ISO-8601)
    - or `dateOption` (preset)
    """
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    url = f"{BASE_URL}/services/dispatch/{entity_ref}/tickets/paginated"

    base_params: dict[str, str] = {
        "dateField": str(date_field or "modifyDate"),
    }
    use_range = start_date and end_date
    if use_range:
        base_params["startDate"] = str(start_date)
        base_params["endDate"] = str(end_date)
    else:
        if date_option:
            base_params["dateOption"] = str(date_option)

    for page in _iter_paginated(url, base_params=base_params, timeout=60):
        if isinstance(page, dict):
            yield page


def fetch_all_ticket_items(
    date_field: str = "modifyDate",
    date_option: Optional[str] = "Yesterday",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch all ticket items from the paginated tickets endpoint."""
    all_items: list[dict[str, Any]] = []
    for page in get_tickets_paginated(
        date_field=date_field,
        date_option=date_option,
        start_date=start_date,
        end_date=end_date,
    ):
        if not isinstance(page, dict):
            continue
        for key in ("items", "tickets", "data"):
            maybe = page.get(key)
            if isinstance(maybe, list):
                all_items.extend([d for d in maybe if isinstance(d, dict)])
                break
    return all_items
