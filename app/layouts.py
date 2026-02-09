"""
Layout model: list of columns = field path (dot notation) + optional custom title + blank columns.
Layouts are saved as JSON in config/layouts/.
"""
import json
from pathlib import Path
from typing import Any, Optional

from .config import LAYOUTS_DIR, ensure_dirs


def _dict_get(d: dict, key: str) -> tuple[bool, Any]:
    """Get value from dict by key, or by case-insensitive key match. Returns (found, value)."""
    if key in d:
        return True, d[key]
    key_lower = key.lower()
    for k, v in d.items():
        if k.lower() == key_lower:
            return True, v
    return False, None


def _layout_path(name: str) -> Path:
    ensure_dirs()
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "default"
    return LAYOUTS_DIR / f"{safe}.json"


def get_value_at_path(obj: dict, path: str) -> str | int | float | bool | None:
    """
    Get value from nested dict using dot path, e.g. paymentTerms.id.
    Arrays: use first element for the next key (e.g. contacts.email = first contact's email),
    or use a numeric segment for a specific index (e.g. contacts.0.email). Returns empty string for missing.
    """
    if not path or not obj:
        return ""
    parts = path.split(".")
    current: Any = obj
    for p in parts:
        if p.isdigit() and isinstance(current, list):
            idx = int(p)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return ""
        elif isinstance(current, dict):
            found, val = _dict_get(current, p)
            if found:
                current = val
            else:
                return ""
        elif isinstance(current, list) and current:
            # Path like contacts.email: use first element (contacts[0].email)
            current = current[0]
            if isinstance(current, dict):
                found, val = _dict_get(current, p)
                if found:
                    current = val
                else:
                    return ""
            else:
                return ""
        else:
            return ""
    if current is None:
        return ""
    if isinstance(current, (dict, list)):
        return json.dumps(current)  # flatten complex as JSON string
    return str(current)


def get_array_at_path(obj: dict, path: str) -> list:
    """Return the raw list at path (e.g. 'contacts'), or [] if not a list."""
    if not path or not obj:
        return []
    parts = path.split(".")
    current: Any = obj
    for p in parts:
        if p.isdigit() and isinstance(current, list):
            idx = int(p)
            current = current[idx] if 0 <= idx < len(current) else None
        elif isinstance(current, dict):
            found, val = _dict_get(current, p)
            if found:
                current = val
            else:
                return []
        elif isinstance(current, list) and current:
            current = current[0]
            if isinstance(current, dict):
                found, val = _dict_get(current, p)
                if found:
                    current = val
                else:
                    return []
            else:
                return []
        else:
            return []
        if current is None:
            return []
    return current if isinstance(current, list) else []


def get_flattened_array_at_path(obj: dict, path: str) -> list:
    """
    Return a flat list of all elements at the end of a path through nested arrays.
    E.g. path 'invoiceSections.billables.lineItems' → all line items from all sections and billables.
    Used for nested expand so you get one row per line item.
    """
    if not path or not obj:
        return []
    parts = path.split(".")
    if not parts:
        return []
    current: list = [obj]
    for p in parts:
        next_list: list = []
        for elem in current:
            if elem is None:
                continue
            if not isinstance(elem, dict):
                continue
            found, val = _dict_get(elem, p)
            if not found or val is None:
                continue
            if isinstance(val, list):
                next_list.extend(val)
            else:
                next_list.append(val)
        current = next_list
    return current


def row_from_item(item: dict, columns: list[dict]) -> list[str]:
    """Build one row (list of string values) from an invoice item using column defs."""
    row = []
    for col in columns:
        if col.get("blank"):
            row.append(col.get("customText", "") or "")
            continue
        path = col.get("fieldPath") or ""
        val = get_value_at_path(item, path)
        row.append("" if val is None else str(val))
    return row


def _value_for_expanded_row(
    item: dict, sub_item: dict | None, col: dict, expand_array_path: str
) -> str:
    """Resolve one cell when exporting with array expansion. Parent fields repeat; array fields from sub_item."""
    if col.get("blank"):
        return col.get("customText", "") or ""
    path = (col.get("fieldPath") or "").strip()
    if not path:
        return ""
    # Path under the expanded array → resolve from sub_item (suffix after expand path)
    if expand_array_path and (path == expand_array_path or path.startswith(expand_array_path + ".")):
        if sub_item is None:
            return ""
        suffix = path[len(expand_array_path):].lstrip(".")
        val = get_value_at_path(sub_item, suffix) if suffix else (
            json.dumps(sub_item) if isinstance(sub_item, (dict, list)) else str(sub_item)
        )
        return "" if val is None else str(val)
    # Parent/invoice-level path → resolve from item (repeated on every row)
    val = get_value_at_path(item, path)
    return "" if val is None else str(val)


def rows_from_items(
    items: list[dict],
    columns: list[dict],
    expand_array_path: str | None = None,
) -> list[list[str]]:
    """
    Build rows for export. If expand_array_path is set (e.g. 'contacts'), each invoice
    produces one row per array element with parent fields repeated (same headers each row).
    """
    if not expand_array_path:
        return [row_from_item(item, columns) for item in items]

    rows = []
    for item in items:
        # Nested path (e.g. invoiceSections.billables.lineItems) → flatten to get each line item
        if "." in expand_array_path:
            arr = get_flattened_array_at_path(item, expand_array_path)
        else:
            arr = get_array_at_path(item, expand_array_path)
        sub_items = arr if arr else [None]  # one row with parent data when array empty
        for sub in sub_items:
            row = [
                _value_for_expanded_row(item, sub, col, expand_array_path)
                for col in columns
            ]
            rows.append(row)
    return rows


# Column: { "fieldPath": "paymentTerms.id", "title": "Payment Terms ID", "blank": false }
# Blank column: { "title": "My Column", "blank": true }

def list_layouts() -> list[str]:
    """Return names of saved layouts (filename without .json)."""
    ensure_dirs()
    names = []
    for f in LAYOUTS_DIR.glob("*.json"):
        names.append(f.stem)
    return sorted(names)


def load_layout(name: str) -> list[dict]:
    """Load layout columns by name. Returns list of { fieldPath?, title, blank? } (backward compat)."""
    meta = load_layout_full(name)
    return meta.get("columns", [])


def load_layout_full(name: str) -> dict:
    """Load full layout: { columns, expandArrayPath? }. expandArrayPath = array path to expand (e.g. 'contacts')."""
    path = _layout_path(name)
    if not path.exists():
        return {"columns": [], "expandArrayPath": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"columns": data if isinstance(data, list) else [], "expandArrayPath": None}
        return {
            "columns": data.get("columns", data.get("items", [])),
            "expandArrayPath": data.get("expandArrayPath") or None,
        }
    except Exception:
        return {"columns": [], "expandArrayPath": None}


def save_layout(
    name: str,
    columns: list[dict],
    expand_array_path: str | None = None,
) -> None:
    """Save layout. columns: list of { fieldPath?, title, blank? }. Optional expand_array_path (e.g. 'contacts')."""
    path = _layout_path(name)
    payload = {"name": name, "columns": columns}
    if expand_array_path and expand_array_path.strip():
        payload["expandArrayPath"] = expand_array_path.strip()
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def delete_layout(name: str) -> bool:
    """Remove a saved layout. Returns True if deleted."""
    path = _layout_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def export_layouts_to_list(layout_names: list[str] | None = None) -> list[dict]:
    """
    Export layouts to a list of dicts for saving to JSON. If layout_names is None, export all.
    Each item: { "name", "columns", "expandArrayPath"? }.
    """
    names = layout_names if layout_names is not None else list_layouts()
    out = []
    for name in names:
        full = load_layout_full(name)
        out.append({
            "name": name,
            "columns": full.get("columns", []),
            "expandArrayPath": full.get("expandArrayPath"),
        })
    return out


def import_layouts_from_list(data: list[dict]) -> list[str]:
    """
    Import layouts from a list of dicts (e.g. from JSON). Each item: { "name", "columns", "expandArrayPath"? }.
    Saves each layout (overwrites if same name). Returns list of imported layout names.
    """
    imported = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("layoutName")
        columns = item.get("columns", item.get("items", []))
        if not name:
            continue
        expand = item.get("expandArrayPath")
        save_layout(name, columns, expand_array_path=expand)
        imported.append(name)
    return imported
