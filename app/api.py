"""
Invoice API client: paginated invoices with dateOption and pageToken.
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


def get_invoices_paginated(
    date_option: str = "Yesterday",
    filtered_fields: bool = True,
) -> Iterator[dict]:
    """
    Yield pages of invoice data. Each yielded value is the raw response dict
    with 'items', 'itemCount', and optionally 'pageToken'.
    """
    creds = load_credentials()
    if not creds:
        raise RuntimeError("No credentials configured.")
    entity_ref = creds["entityRef"]
    url = f"{BASE_URL}/services/billing/{entity_ref}/invoices/paginated"

    page_token: Optional[str] = None
    seen_tokens: set = set()

    while True:
        params: dict = {
            "dateOption": date_option,
            "filteredFields": "true" if filtered_fields else "false",
        }
        if page_token:
            if page_token in seen_tokens:
                break
            seen_tokens.add(page_token)
            params["pageToken"] = page_token

        response = request_with_token_refresh("GET", url, params=params, timeout=60)
        data = _safe_json(response)

        if response.status_code != 200:
            raise RuntimeError(
                f"Invoice API error {response.status_code}: {data}"
            )

        yield data

        if isinstance(data, dict):
            page_token = data.get("pageToken") or data.get("nextPageToken")
        else:
            page_token = None
        if not page_token:
            break


def fetch_all_invoice_items(
    date_option: str = "Yesterday",
    filtered_fields: bool = True,
) -> list[dict[str, Any]]:
    """Fetch all invoice items across all pages."""
    all_items: list = []
    for page in get_invoices_paginated(date_option=date_option, filtered_fields=filtered_fields):
        items = page.get("items") if isinstance(page, dict) else []
        if isinstance(items, list):
            all_items.extend(items)
    return all_items
