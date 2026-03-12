"""
Layout model: list of columns = field path (dot notation) + optional custom title + blank columns.
Layouts are saved as JSON in config/layouts/.
"""
import json
from pathlib import Path
from typing import Any, Optional

from .config import LAYOUTS_DIR, ensure_dirs


def _safe_int(value: Any, default: int = 0, *, min_value: int = 0, max_value: int = 100) -> int:
    try:
        i = int(value)
    except (TypeError, ValueError):
        return default
    if i < min_value:
        return min_value
    if i > max_value:
        return max_value
    return i


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


def _condition_matches(val_s: str, rule: dict) -> bool:
    """Return True if the cell value matches the rule (operator + ifValue)."""
    op = (rule.get("operator") or "equals").strip().lower().replace(" ", "_")
    if_val = rule.get("ifValue")
    if_val_s = "" if if_val is None else str(if_val)
    val_stripped = (val_s or "").strip()
    if_val_stripped = if_val_s.strip()

    if op == "is_blank":
        return not bool(val_stripped)
    if op == "is_not_blank":
        return bool(val_stripped)

    # Try numeric comparison for greater/less
    def try_num(s: str):
        s = (s or "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    if op in ("greater", "greater_or_equal", "less", "less_or_equal"):
        n_val, n_if = try_num(val_s), try_num(if_val_s)
        if n_val is not None and n_if is not None:
            if op == "greater":
                return n_val > n_if
            if op == "greater_or_equal":
                return n_val >= n_if
            if op == "less":
                return n_val < n_if
            if op == "less_or_equal":
                return n_val <= n_if
        # Fallback to string comparison
        if op == "greater":
            return (val_stripped or "") > (if_val_stripped or "")
        if op == "greater_or_equal":
            return (val_stripped or "") >= (if_val_stripped or "")
        if op == "less":
            return (val_stripped or "") < (if_val_stripped or "")
        if op == "less_or_equal":
            return (val_stripped or "") <= (if_val_stripped or "")

    if op in ("not_equal", "not_equals"):
        return (val_stripped or "") != (if_val_stripped or "")
    if op == "contains":
        return (if_val_stripped or "") in (val_stripped or "")
    if op == "not_contains":
        return (if_val_stripped or "") not in (val_stripped or "")
    # equals (default)
    return (val_stripped or "") == (if_val_stripped or "")


def apply_conditions(value_str: str, conditions: list[dict]) -> str:
    """
    If value matches any condition (operator + ifValue), return replaceWith.
    conditions: [{"operator": "equals"|"not_equals"|..., "ifValue": "...", "replaceWith": "..."}, ...]. First match wins.
    """
    if not conditions or not isinstance(conditions, list):
        return value_str
    val_s = value_str if value_str is not None else ""
    for rule in conditions:
        if not isinstance(rule, dict):
            continue
        if _condition_matches(val_s, rule):
            return str(rule.get("replaceWith", "") or "")
    return value_str


def row_from_item(item: dict, columns: list[dict]) -> list[str]:
    """Build one row (list of string values) from an invoice item using column defs."""
    row = []
    for col in columns:
        if col.get("blank"):
            row.append(col.get("customText", "") or "")
            continue
        path = col.get("fieldPath") or ""
        val = get_value_at_path(item, path)
        s = "" if val is None else str(val)
        s = apply_conditions(s, col.get("conditions") or [])
        row.append(s)
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
        s = "" if val is None else str(val)
        s = apply_conditions(s, col.get("conditions") or [])
        return s
    # Parent/invoice-level path → resolve from item (repeated on every row)
    val = get_value_at_path(item, path)
    s = "" if val is None else str(val)
    s = apply_conditions(s, col.get("conditions") or [])
    return s


def rows_from_items(
    items: list[dict],
    columns: list[dict],
    expand_array_path: str | None = None,
    layout_options: dict | None = None,
) -> list[list[str]]:
    """
    Build rows for export. If expand_array_path is set (e.g. 'contacts'), each invoice
    produces one row per array element with parent fields repeated (same headers each row).
    """
    def blank_row() -> list[str]:
        return ["" for _ in columns]

    def resolve_rule_value(item: dict, sub_item: dict | None, rule_path: str) -> str:
        rule_path = (rule_path or "").strip()
        if not rule_path:
            return ""
        if expand_array_path:
            return _value_for_expanded_row(item, sub_item, {"fieldPath": rule_path, "blank": False}, expand_array_path)
        val = get_value_at_path(item, rule_path)
        return "" if val is None else str(val)

    blank_rules = []
    if isinstance(layout_options, dict):
        maybe = layout_options.get("blankRowsBefore")
        if isinstance(maybe, list):
            blank_rules = [r for r in maybe if isinstance(r, dict)]

    blank_before_empty_expanded = 0
    if isinstance(layout_options, dict):
        blank_before_empty_expanded = _safe_int(layout_options.get("blankRowsBeforeEmptyExpandedRow"), 0)

    def blank_rows_to_insert(item: dict, sub_item: dict | None) -> int:
        total = 0
        # Convenience: expanded array is empty -> sub_item None
        if expand_array_path and sub_item is None and blank_before_empty_expanded:
            total += blank_before_empty_expanded
        for rule in blank_rules:
            path = rule.get("path") or rule.get("fieldPath") or ""
            op = rule.get("operator") or "is_blank"
            if_val = rule.get("ifValue", "")
            count = _safe_int(rule.get("count"), 1)
            if count <= 0:
                continue
            val_s = resolve_rule_value(item, sub_item, str(path))
            if _condition_matches(val_s, {"operator": op, "ifValue": if_val}):
                total += count
        return _safe_int(total, 0)

    if not expand_array_path:
        rows: list[list[str]] = []
        for item in items:
            n_blank = blank_rows_to_insert(item, None)
            for _ in range(n_blank):
                rows.append(blank_row())
            rows.append(row_from_item(item, columns))
        return rows

    rows: list[list[str]] = []
    for item in items:
        # Nested path (e.g. invoiceSections.billables.lineItems) → flatten to get each line item
        if "." in expand_array_path:
            arr = get_flattened_array_at_path(item, expand_array_path)
        else:
            arr = get_array_at_path(item, expand_array_path)
        sub_items = arr if arr else [None]  # one row with parent data when array empty
        for sub in sub_items:
            n_blank = blank_rows_to_insert(item, sub)
            for _ in range(n_blank):
                rows.append(blank_row())
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
    """Load full layout JSON (normalized). Always returns a dict with at least: { columns, expandArrayPath? }."""
    path = _layout_path(name)
    if not path.exists():
        return {"name": name, "columns": [], "expandArrayPath": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"name": name, "columns": data if isinstance(data, list) else [], "expandArrayPath": None}

        normalized = dict(data)
        normalized["name"] = data.get("name") or name
        normalized["columns"] = data.get("columns", data.get("items", []))
        normalized["expandArrayPath"] = data.get("expandArrayPath") or None
        return normalized
    except Exception:
        return {"name": name, "columns": [], "expandArrayPath": None}


def save_layout(
    name: str,
    columns: list[dict],
    expand_array_path: str | None = None,
    extra: dict | None = None,
) -> None:
    """Save layout.

    columns: list of { fieldPath?, title, blank? }. Optional expand_array_path (e.g. 'contacts').
    extra: any other top-level layout keys to persist (e.g. blankRowsBefore rules).
    """
    path = _layout_path(name)

    # Preserve any unknown keys already stored on disk so opening/saving in the UI
    # doesn't wipe advanced settings.
    preserved: dict[str, Any] = {}
    try:
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                preserved = {
                    k: v for k, v in existing.items()
                    if k not in ("name", "layoutName", "columns", "items", "expandArrayPath")
                }
    except Exception:
        preserved = {}

    payload: dict[str, Any] = {"name": name, "columns": columns}
    if expand_array_path and expand_array_path.strip():
        payload["expandArrayPath"] = expand_array_path.strip()
    if preserved:
        payload.update(preserved)
    if isinstance(extra, dict) and extra:
        payload.update(extra)
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
        full["name"] = name
        out.append(full)
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
        extra = {
            k: v for k, v in item.items()
            if k not in ("name", "layoutName", "columns", "items", "expandArrayPath")
        }
        save_layout(name, columns, expand_array_path=expand, extra=extra)
        imported.append(name)
    return imported
