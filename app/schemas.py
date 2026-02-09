"""
Load JSON schemas (e.g. exampleschema.json) and extract flat field paths for layouts.
Paths use dot notation for nested fields, e.g. paymentTerms.id, profile.firstName.
"""
import json
from pathlib import Path
from typing import Any


def _collect_paths(obj: Any, prefix: str = "") -> list[str]:
    """Recursively collect dot-separated paths (e.g. paymentTerms.id). For arrays, uses first element."""
    out: list[str] = []
    if obj is None:
        if prefix:
            out.append(prefix)
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = k if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                out.extend(_collect_paths(v, key))
            elif isinstance(v, list) and v:
                first = v[0]
                if isinstance(first, (dict, list)):
                    out.extend(_collect_paths(first, key))  # e.g. contacts.email from first
                else:
                    out.append(key)
            else:
                out.append(key)
        return out
    if isinstance(obj, list) and obj:
        first = obj[0]
        if isinstance(first, (dict, list)):
            out.extend(_collect_paths(first, prefix))
        elif prefix:
            out.append(prefix)
        return out
    if prefix:
        out.append(prefix)
    return out


def _get_schema_root(schema: dict | list) -> Any:
    """Return the root object (first item) from schema for scanning."""
    if isinstance(schema, list) and schema:
        return schema[0]
    if isinstance(schema, dict) and "items" in schema:
        items = schema["items"]
        return items[0] if isinstance(items, list) and items else schema
    return schema


def extract_field_paths_from_schema(schema: dict | list) -> list[str]:
    """
    Extract a sorted list of field paths from a schema (e.g. invoice item).
    If schema has 'items', uses first item as the object to scan; otherwise uses root.
    """
    root = _get_schema_root(schema)
    paths = _collect_paths(root)
    return sorted(set(p for p in paths if p))


def extract_array_paths_from_schema(schema: dict | list) -> list[str]:
    """
    Extract array paths for "Expand array" option: top-level and one level of nesting
    so e.g. 'invoiceSections.billables.lineItems' is available for one row per line item.
    """
    root = _get_schema_root(schema)
    if not isinstance(root, dict):
        return []
    out = []
    for k, v in root.items():
        if isinstance(v, list) and v and isinstance(v[0], (dict, list)):
            out.append(k)
            # Add nested array paths (e.g. invoiceSections.billables.lineItems)
            first = v[0]
            if isinstance(first, dict):
                for k2, v2 in first.items():
                    if isinstance(v2, list) and v2 and isinstance(v2[0], (dict, list)):
                        nested = f"{k}.{k2}"
                        out.append(nested)
                        first2 = v2[0]
                        if isinstance(first2, dict):
                            for k3, v3 in first2.items():
                                if isinstance(v3, list) and v3 and isinstance(v3[0], (dict, list)):
                                    out.append(f"{nested}.{k3}")
    return sorted(out)


def load_schema_file(path: str | Path) -> dict | list:
    """Load JSON schema from file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_field_paths_from_file(path: str | Path) -> list[str]:
    """Load schema file and return field paths for layout reference."""
    data = load_schema_file(path)
    return extract_field_paths_from_schema(data)
