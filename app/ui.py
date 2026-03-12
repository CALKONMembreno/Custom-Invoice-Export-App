"""
UI: Config credentials, Manage layouts, Query & Export (CSV/XLSX).
"""
import json
import sys
from datetime import datetime
from calendar import monthrange
from tkinter import Menu, filedialog, messagebox, simpledialog
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from . import config, api, layouts, export, schemas
from .config import SCHEMAS_DIR, load_settings, save_settings


# Date options for the API
DATE_OPTIONS = api.DATE_OPTIONS

# Command Alkon brand colors (professional blue)
_theme_path = Path(__file__).resolve().parent / "themes" / "commandalkon.json"
if _theme_path.exists():
    ctk.set_default_color_theme(str(_theme_path))
else:
    ctk.set_default_color_theme("blue")
ctk.set_appearance_mode("dark")


class ConfigFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="API credentials (stored encrypted)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 4))
        ctk.CTkLabel(self, text="Entity Ref, API Key, Client ID, Client Secret, API Scope Ref", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(0, 8))

        self.entries = {}
        for key, label in [
            ("entityRef", "Entity Ref"),
            ("apiKey", "API Key"),
            ("clientId", "Client ID"),
            ("clientSecret", "Client Secret"),
            ("apiScopeRef", "API Scope Ref"),
        ]:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=label, width=120).pack(side="left", padx=(0, 8))
            e = ctk.CTkEntry(row, placeholder_text=label, width=320, show="*" if "Secret" in label or "Key" in label else "")
            e.pack(side="left", fill="x", expand=True)
            self.entries[key] = e

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=12)
        ctk.CTkButton(btn_row, text="Save credentials", command=self._save).pack(side="left", padx=(0, 8))
        self.status = ctk.CTkLabel(btn_row, text="", text_color="gray")
        self.status.pack(side="left")
        self._refresh_status()

    def _refresh_status(self):
        h = config.credentials_hash_for_display()
        if h:
            self.status.configure(text=f"Saved (••••{h})")
        else:
            self.status.configure(text="No credentials saved")

    def _save(self):
        data = {k: e.get().strip() for k, e in self.entries.items()}
        if not all(data.values()):
            messagebox.showwarning("Missing fields", "Fill all credential fields.")
            return
        try:
            config.save_credentials(data)
            self._refresh_status()
            messagebox.showinfo("Saved", "Credentials saved (encrypted).")
        except Exception as e:
            messagebox.showerror("Error", str(e))


class LayoutsFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._columns: list[dict] = []
        self._blank_row_rules: list[dict] = []
        self._blank_rows_before_first_row: int = 0
        self._build_ui()

    def _build_ui(self):
        # Scrollable container so all fields fit on small screens
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(self._scroll, text="Manage layouts", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 4))
        ctk.CTkLabel(self._scroll, text="Add columns by field path (e.g. paymentTerms.id) and optional custom title. Add blank columns as needed.", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(0, 8))

        # Schema import
        schema_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        schema_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(schema_row, text="Import schema (JSON)", command=self._import_schema, width=160).pack(side="left", padx=(0, 8))
        self.schema_path_label = ctk.CTkLabel(schema_row, text="No schema loaded", text_color="gray")
        self.schema_path_label.pack(side="left")
        self._field_paths = []
        self._array_paths = []
        self._last_imported_schema_name = None

        # Expand array
        expand_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        expand_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(expand_row, text="Expand array", width=100).pack(side="left", padx=(0, 8))
        self.expand_combo = ctk.CTkComboBox(expand_row, values=["(None)"], width=200)
        self.expand_combo.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(expand_row, text="One row per element; invoice fields repeat", font=ctk.CTkFont(size=10), text_color="gray").pack(side="left", padx=(8, 0))

        # Empty rows (blank lines)
        empty_rows_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        empty_rows_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(empty_rows_row, text="Empty rows", width=100).pack(side="left", padx=(0, 8))
        self.blank_before_each_row_entry = ctk.CTkEntry(empty_rows_row, width=70, placeholder_text="0")
        self.blank_before_each_row_entry.pack(side="left", padx=(0, 8))
        self.blank_before_each_row_entry.insert(0, "0")
        ctk.CTkLabel(
            empty_rows_row,
            text="Blank rows before the first exported row",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(empty_rows_row, text="Empty row rules…", width=140, command=self._open_blank_rows_modal).pack(side="left", padx=(8, 0))

        # Layout name + Load/Save (row 1)
        name_row1 = ctk.CTkFrame(self._scroll, fg_color="transparent")
        name_row1.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(name_row1, text="Layout name", width=100).pack(side="left", padx=(0, 8))
        self.layout_name_entry = ctk.CTkEntry(name_row1, placeholder_text="e.g. My Export", width=200)
        self.layout_name_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row1, text="Load layout", command=self._load_layout, width=100).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row1, text="Save layout", command=self._save_layout, width=100).pack(side="left", padx=(0, 8))

        # Export/Import layouts + dropdown (row 2)
        name_row2 = ctk.CTkFrame(self._scroll, fg_color="transparent")
        name_row2.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(name_row2, text="", width=100).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row2, text="Export layouts", command=self._export_layouts, width=110).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row2, text="Import layouts", command=self._import_layouts, width=110).pack(side="left", padx=(0, 8))
        self.layout_combo = ctk.CTkComboBox(name_row2, values=layouts.list_layouts(), width=180, command=self._on_select_layout)
        self.layout_combo.pack(side="left", padx=(0, 8))

        # Column list (expandable)
        ctk.CTkLabel(self._scroll, text="Columns (field path → custom title; blank = empty column)", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 4))
        list_frame = ctk.CTkScrollableFrame(self._scroll, height=220, fg_color=("gray85", "gray20"))
        list_frame.pack(fill="x", padx=10, pady=4)
        self.column_list_frame = list_frame

        btn_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btn_row, text="Add field column", command=self._add_field_column, width=140).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Add blank column", command=self._add_blank_column, width=140).pack(side="left", padx=(0, 8))
        self._refresh_layout_combo()
        self._redraw_columns()
        self._load_last_schema_if_saved()

    def _safe_int(self, s: str, default: int = 0, *, min_value: int = 0, max_value: int = 100) -> int:
        try:
            v = int(str(s).strip())
        except (TypeError, ValueError):
            return default
        if v < min_value:
            return min_value
        if v > max_value:
            return max_value
        return v

    def _set_blank_row_options_from_layout(self, layout_full: dict):
        n = self._safe_int(layout_full.get("blankRowsBeforeFirstRow"), 0)
        if not n:
            # Back-compat: older saved layouts used this key.
            n = self._safe_int(layout_full.get("blankRowsBeforeEachRow"), 0)
        if not n:
            n = self._safe_int(layout_full.get("blankRowsBeforeEveryRow"), 0)
        self._blank_rows_before_first_row = n
        try:
            self.blank_before_each_row_entry.delete(0, "end")
            self.blank_before_each_row_entry.insert(0, str(n))
        except Exception:
            pass
        rules = layout_full.get("blankRowsBefore")
        self._blank_row_rules = [dict(r) for r in rules] if isinstance(rules, list) else []

    def _get_blank_row_options_for_save(self) -> dict:
        n = self._safe_int(self.blank_before_each_row_entry.get(), 0)
        self._blank_rows_before_first_row = n
        rules = [dict(r) for r in (self._blank_row_rules or []) if isinstance(r, dict)]
        out: dict = {}
        if n:
            out["blankRowsBeforeFirstRow"] = n
        if rules:
            out["blankRowsBefore"] = rules
        return out

    def _open_blank_rows_modal(self):
        """Edit blank-row insertion rules for the layout (adds empty rows before an export row when a condition matches)."""
        rules: list[dict] = [dict(r) for r in (self._blank_row_rules or [])]
        if not rules:
            rules = [{"path": "", "operator": "is_blank", "ifValue": "", "count": 1}]

        CONDITION_OPERATORS = [
            ("equals", "equal"),
            ("not_equals", "not equal"),
            ("contains", "contains"),
            ("not_contains", "not contains"),
            ("greater", "greater"),
            ("greater_or_equal", "greater or equal"),
            ("less", "less"),
            ("less_or_equal", "less or equal"),
            ("is_blank", "is blank"),
            ("is_not_blank", "is not blank"),
        ]
        op_values = [v[0] for v in CONDITION_OPERATORS]
        op_labels = [v[1] for v in CONDITION_OPERATORS]

        win = ctk.CTkToplevel(self.winfo_toplevel())
        win.title("Empty row rules")
        win.geometry("760x360")
        win.transient(self.winfo_toplevel())

        ctk.CTkLabel(
            win,
            text="Insert blank rows before a row when a field matches a rule. For 'is blank' / 'is not blank' the value field is ignored.",
            font=ctk.CTkFont(size=11),
            wraplength=720,
        ).pack(anchor="w", padx=12, pady=(10, 6))

        header = ctk.CTkFrame(win, fg_color="transparent")
        header.pack(fill="x", padx=12)
        ctk.CTkLabel(header, text="Field path", width=280).pack(side="left")
        ctk.CTkLabel(header, text="Operator", width=140).pack(side="left")
        ctk.CTkLabel(header, text="Value", width=160).pack(side="left")
        ctk.CTkLabel(header, text="# Rows", width=70).pack(side="left")

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent", height=200)
        scroll.pack(fill="both", expand=True, padx=12, pady=6)

        entries_list: list[tuple[ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkEntry, ctk.CTkEntry]] = []

        def redraw_rules():
            for w in scroll.winfo_children():
                w.destroy()
            entries_list.clear()
            for i, r in enumerate(rules):
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)

                path_entry = ctk.CTkEntry(row, width=280, placeholder_text="e.g. invoiceSections.billables.lineItems.productId")
                path_entry.pack(side="left", padx=(0, 6))
                path_entry.insert(0, str(r.get("path") or r.get("fieldPath") or ""))

                def on_pick(idx: int):
                    def chosen(path: str):
                        if 0 <= idx < len(rules):
                            rules[idx]["path"] = path
                        redraw_rules()
                    self._open_pick_field_popup(chosen)

                ctk.CTkButton(row, text="Pick…", width=50, command=lambda idx=i: on_pick(idx)).pack(side="left", padx=(0, 10))

                op_combo = ctk.CTkComboBox(row, values=op_labels, width=140)
                op_combo.pack(side="left", padx=(0, 6))
                stored = str(r.get("operator") or "is_blank")
                if stored in op_values:
                    op_combo.set(CONDITION_OPERATORS[op_values.index(stored)][1])
                else:
                    op_combo.set("is blank")

                val_entry = ctk.CTkEntry(row, width=160, placeholder_text="(ignored for is blank)")
                val_entry.pack(side="left", padx=(0, 6))
                val_entry.insert(0, str(r.get("ifValue", "") or ""))

                count_entry = ctk.CTkEntry(row, width=70, placeholder_text="1")
                count_entry.pack(side="left", padx=(0, 6))
                count_entry.insert(0, str(r.get("count", 1) or 1))

                entries_list.append((path_entry, op_combo, val_entry, count_entry))
                ctk.CTkButton(row, text="Remove", width=70, command=lambda idx=i: _remove_rule(idx)).pack(side="left", padx=(6, 0))

        def _remove_rule(idx: int):
            if 0 <= idx < len(rules):
                rules.pop(idx)
                if not rules:
                    rules.append({"path": "", "operator": "is_blank", "ifValue": "", "count": 1})
                redraw_rules()

        def _add_rule():
            rules.append({"path": "", "operator": "is_blank", "ifValue": "", "count": 1})
            redraw_rules()

        def _save():
            new_rules: list[dict] = []
            for (path_entry, op_combo, val_entry, count_entry) in entries_list:
                path = (path_entry.get() or "").strip()
                label = (op_combo.get() or "").strip()
                try:
                    op_val = op_values[op_labels.index(label)]
                except (ValueError, IndexError):
                    op_val = "is_blank"
                if_val = (val_entry.get() or "").strip()
                count = self._safe_int(count_entry.get(), 1, min_value=0, max_value=100)
                if not path or count <= 0:
                    continue
                new_rules.append({"path": path, "operator": op_val, "ifValue": if_val, "count": count})
            self._blank_row_rules = new_rules
            win.destroy()

        redraw_rules()
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btn_row, text="Add rule", width=90, command=_add_rule).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="OK", width=80, command=_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancel", width=80, fg_color="gray", command=win.destroy).pack(side="left")

    def _load_last_schema_if_saved(self):
        """On startup, reload the last imported schema from config/schemas/ if saved."""
        name = load_settings().get("lastSchema")
        if not name:
            return
        dest = SCHEMAS_DIR / name
        if not dest.exists():
            return
        try:
            self._last_imported_schema_name = name
            self._load_schema_from_path(dest)
        except Exception:
            pass

    def _import_schema(self):
        path = filedialog.askopenfilename(
            title="Select schema JSON",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialdir=Path(__file__).resolve().parent.parent,
        )
        if not path:
            return
        try:
            self._load_schema_from_path(path)
            # Save copy to config/schemas/ (overwrites if same name) and remember for reimport
            import shutil
            name = Path(path).name
            dest = SCHEMAS_DIR / name
            shutil.copy(path, dest)
            self._last_imported_schema_name = name
            save_settings({**load_settings(), "lastSchema": name})
        except Exception as e:
            messagebox.showerror("Import error", str(e))

    def _load_schema_from_path(self, path: str | Path):
        """Load schema from file path and refresh field/array paths (does not save to config)."""
        path = Path(path)
        data = schemas.load_schema_file(path)
        self._field_paths = schemas.extract_field_paths_from_schema(data)
        self._array_paths = schemas.extract_array_paths_from_schema(data)
        self.schema_path_label.configure(text=f"Loaded {len(self._field_paths)} paths from {path.name}")
        self._refresh_expand_combo()

    def _add_field_column(self):
        self._columns.append({"fieldPath": "", "title": "", "blank": False})
        self._redraw_columns()

    def _add_blank_column(self):
        self._columns.append({"title": "Blank", "blank": True, "customText": ""})
        self._redraw_columns()

    def _open_pick_field_popup(self, on_select: Callable[[str], None]):
        """Open searchable field picker in a separate window to the right of the main app."""
        win = ctk.CTkToplevel(self)
        win.title("Pick field")
        win.geometry("420x280")
        # Position as a separate window to the right of the main app so both stay visible
        try:
            root = self.winfo_toplevel()
            root.update_idletasks()
            rx, ry = root.winfo_x(), root.winfo_y()
            rw = root.winfo_width()
            gap = 20
            win.geometry(f"420x280+{rx + rw + gap}+{ry}")
        except Exception:
            pass
        ctk.CTkLabel(win, text="Type to search, then click a path:").pack(anchor="w", padx=10, pady=(10, 2))
        path_entry = ctk.CTkEntry(win, placeholder_text="Type to search...", width=380)
        path_entry.pack(fill="x", padx=10, pady=4)
        list_frame = ctk.CTkScrollableFrame(win, width=380, height=140, fg_color=("gray90", "gray20"))
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        max_visible = 150
        all_paths = self._field_paths if self._field_paths else []

        def refresh_list():
            for w in list_frame.winfo_children():
                w.destroy()
            q = path_entry.get().strip().lower()
            filtered = [p for p in all_paths if q in p.lower()] if q else all_paths
            for p in filtered[:max_visible]:
                def make_cmd(selected_path):
                    def _():
                        on_select(selected_path)
                        win.destroy()
                    return _
                btn = ctk.CTkButton(
                    list_frame, text=p, anchor="w", height=26,
                    fg_color="transparent", text_color=("gray10", "gray90"),
                    command=make_cmd(p),
                )
                btn.pack(fill="x", pady=1)
            if len(filtered) > max_visible:
                ctk.CTkLabel(list_frame, text=f"... {len(filtered) - max_visible} more", font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w")

        path_entry.bind("<KeyRelease>", lambda e: refresh_list())
        refresh_list()
        ctk.CTkButton(win, text="Cancel", command=win.destroy, width=80, fg_color="gray").pack(pady=8)

    def _redraw_columns(self):
        for w in self.column_list_frame.winfo_children():
            w.destroy()
        try:
            self.column_list_frame.unbind("<ButtonRelease-1>")
        except Exception:
            pass
        for i, col in enumerate(self._columns):
            row = ctk.CTkFrame(self.column_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            setattr(row, "_row_index", i)
            # Drag handle
            grip = ctk.CTkLabel(row, text="⋮⋮", width=24, cursor="hand2", text_color="gray")
            grip.pack(side="left", padx=(0, 4))
            grip.bind("<Button-1>", lambda e, idx=i: self._column_drag_start(e, idx))
            content = ctk.CTkFrame(row, fg_color="transparent")
            content.pack(side="left", fill="x", expand=True)
            if col.get("blank"):
                ctk.CTkLabel(content, text="[Blank]", width=52).pack(side="left", padx=(0, 6))
                title_entry = ctk.CTkEntry(content, width=120, placeholder_text="Column title")
                title_entry.pack(side="left", padx=(0, 4))
                title_entry.insert(0, col.get("title") or "Blank")
                def sync_title_blank(idx, entry):
                    self._columns[idx]["title"] = entry.get().strip() or "Blank"
                title_entry.bind("<KeyRelease>", lambda e, idx=i, ent=title_entry: sync_title_blank(idx, ent))
                ctk.CTkLabel(content, text="Value:", width=36, font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
                custom_entry = ctk.CTkEntry(content, width=140, placeholder_text="Text in every row")
                custom_entry.pack(side="left", padx=(0, 4))
                custom_entry.insert(0, col.get("customText") or "")
                def sync_custom_blank(idx, entry):
                    self._columns[idx]["customText"] = entry.get().strip()
                custom_entry.bind("<KeyRelease>", lambda e, idx=i, ent=custom_entry: sync_custom_blank(idx, ent))
            else:
                path_entry = ctk.CTkEntry(content, width=220, placeholder_text="Field path (e.g. paymentTerms.id)")
                path_entry.pack(side="left", padx=(0, 4))
                path_entry.insert(0, col.get("fieldPath") or "")
                def sync_path(idx, entry):
                    self._columns[idx]["fieldPath"] = entry.get().strip()
                path_entry.bind("<KeyRelease>", lambda e, idx=i, ent=path_entry: sync_path(idx, ent))
                def on_pick(idx):
                    def chosen(path):
                        self._columns[idx]["fieldPath"] = path
                        if not self._columns[idx].get("title"):
                            self._columns[idx]["title"] = path
                        self._redraw_columns()
                    self._open_pick_field_popup(chosen)
                ctk.CTkButton(content, text="Pick…", width=50, command=lambda idx=i: on_pick(idx)).pack(side="left", padx=(0, 8))
                title_entry = ctk.CTkEntry(content, width=140, placeholder_text="Column title")
                title_entry.pack(side="left", padx=(0, 4))
                title_entry.insert(0, col.get("title") or col.get("fieldPath") or "")
                def sync_title(idx, entry):
                    self._columns[idx]["title"] = entry.get().strip()
                title_entry.bind("<KeyRelease>", lambda e, idx=i, ent=title_entry: sync_title(idx, ent))
                ctk.CTkButton(content, text="Conditions…", width=90, command=lambda idx=i: self._open_conditions_modal(idx)).pack(side="left", padx=(8, 0))
            btn_up = ctk.CTkButton(row, text="▲", width=28, command=lambda idx=i: self._move_column(idx, -1))
            btn_up.pack(side="right", padx=(0, 2))
            if i == 0:
                btn_up.configure(state="disabled")
            btn_down = ctk.CTkButton(row, text="▼", width=28, command=lambda idx=i: self._move_column(idx, 1))
            btn_down.pack(side="right", padx=(0, 2))
            if i == len(self._columns) - 1:
                btn_down.configure(state="disabled")
            ctk.CTkButton(row, text="Remove", width=70, command=lambda idx=i: self._remove_column(idx)).pack(side="right")
        self.column_list_frame.bind("<ButtonRelease-1>", self._on_column_drag_release)

    def _column_drag_start(self, event, index: int):
        self._drag_column_index = index

    def _on_column_drag_release(self, event):
        start = getattr(self, "_drag_column_index", None)
        if start is None:
            return
        self._drag_column_index = None
        w = self.column_list_frame.winfo_containing(event.x_root, event.y_root)
        while w and w != self.column_list_frame:
            if hasattr(w, "master") and w.master == self.column_list_frame and hasattr(w, "_row_index"):
                target = w._row_index
                if target != start and 0 <= target < len(self._columns):
                    col = self._columns.pop(start)
                    self._columns.insert(target, col)
                    self._redraw_columns()
                return
            w = w.master if hasattr(w, "master") else None

    def _move_column(self, index: int, delta: int):
        new_idx = index + delta
        if new_idx < 0 or new_idx >= len(self._columns):
            return
        self._columns[index], self._columns[new_idx] = self._columns[new_idx], self._columns[index]
        self._redraw_columns()

    def _remove_column(self, index: int):
        if 0 <= index < len(self._columns):
            self._columns.pop(index)
            self._redraw_columns()

    def _open_conditions_modal(self, column_index: int):
        """Edit replace rules for a column: operator (equals, contains, greater, is blank, etc.) + value → replace with."""
        if column_index < 0 or column_index >= len(self._columns):
            return
        col = self._columns[column_index]
        if col.get("blank"):
            return
        rules: list[dict] = [dict(r) for r in (col.get("conditions") or [])]
        if not rules:
            rules = [{"operator": "equals", "ifValue": "", "replaceWith": ""}]
        for r in rules:
            if "operator" not in r:
                r["operator"] = "equals"

        CONDITION_OPERATORS = [
            ("equals", "equal"),
            ("not_equals", "not equal"),
            ("contains", "contains"),
            ("not_contains", "not contains"),
            ("greater", "greater"),
            ("greater_or_equal", "greater or equal"),
            ("less", "less"),
            ("less_or_equal", "less or equal"),
            ("is_blank", "is blank"),
            ("is_not_blank", "is not blank"),
        ]
        op_values = [v[0] for v in CONDITION_OPERATORS]
        op_labels = [v[1] for v in CONDITION_OPERATORS]

        win = ctk.CTkToplevel(self.winfo_toplevel())
        win.title("Column conditions")
        win.geometry("600x340")
        win.transient(self.winfo_toplevel())

        ctk.CTkLabel(win, text="If the cell value matches the rule (operator + value), it is replaced. First match wins. For 'is blank' / 'is not blank' the value field is ignored.", font=ctk.CTkFont(size=11), wraplength=560).pack(anchor="w", padx=12, pady=(10, 6))
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent", height=180)
        scroll.pack(fill="x", padx=12, pady=4)
        entries_list: list[tuple[ctk.CTkComboBox, ctk.CTkEntry, ctk.CTkEntry]] = []

        def redraw_rules():
            for w in scroll.winfo_children():
                w.destroy()
            entries_list.clear()
            for i, r in enumerate(rules):
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text="If value", width=52).pack(side="left", padx=(0, 2))
                op_combo = ctk.CTkComboBox(row, values=op_labels, width=130)
                op_combo.pack(side="left", padx=(0, 4))
                stored = str(r.get("operator") or "equals")
                if stored in op_values:
                    op_combo.set(CONDITION_OPERATORS[op_values.index(stored)][1])
                else:
                    op_combo.set("equal")
                ctk.CTkLabel(row, text="", width=8).pack(side="left")
                e1 = ctk.CTkEntry(row, width=100, placeholder_text="value (ignored for is blank/not blank)")
                e1.pack(side="left", padx=(0, 6))
                e1.insert(0, str(r.get("ifValue", "") or ""))
                ctk.CTkLabel(row, text="replace with", width=85).pack(side="left", padx=(0, 4))
                e2 = ctk.CTkEntry(row, width=100, placeholder_text="replacement")
                e2.pack(side="left", padx=(0, 6))
                e2.insert(0, str(r.get("replaceWith", "") or ""))
                entries_list.append((op_combo, e1, e2))
                ctk.CTkButton(row, text="Remove", width=70, command=lambda idx=i: _remove_rule(idx)).pack(side="left", padx=(4, 0))

        def _remove_rule(idx: int):
            if 0 <= idx < len(rules):
                rules.pop(idx)
                redraw_rules()

        def _add_rule():
            rules.append({"operator": "equals", "ifValue": "", "replaceWith": ""})
            redraw_rules()

        def _save():
            for i, (op_combo, e1, e2) in enumerate(entries_list):
                if i < len(rules):
                    label = (op_combo.get() or "").strip()
                    try:
                        op_val = op_values[op_labels.index(label)]
                    except (ValueError, IndexError):
                        op_val = "equals"
                    rules[i] = {"operator": op_val, "ifValue": e1.get().strip(), "replaceWith": e2.get().strip()}
            def keep(r):
                if (r.get("operator") or "").strip() in ("is_blank", "is_not_blank"):
                    return bool(str(r.get("replaceWith") or "").strip())
                return bool(str(r.get("ifValue") or "").strip() or str(r.get("replaceWith") or "").strip())
            self._columns[column_index]["conditions"] = [r for r in rules if keep(r)]
            win.destroy()
            self._redraw_columns()

        redraw_rules()
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btn_row, text="Add rule", width=90, command=_add_rule).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="OK", width=80, command=_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancel", width=80, fg_color="gray", command=win.destroy).pack(side="left")

    def _refresh_expand_combo(self):
        values = ["(None)"] + self._array_paths
        self.expand_combo.configure(values=values)
        self.expand_combo.set("(None)")

    def _refresh_layout_combo(self):
        names = layouts.list_layouts()
        self.layout_combo.configure(values=names)
        if names:
            self.layout_combo.set(names[0])

    def _get_expand_array_path(self) -> Optional[str]:
        v = self.expand_combo.get().strip()
        return None if not v or v == "(None)" else v

    def _on_select_layout(self, name: str):
        full = layouts.load_layout_full(name)
        self._columns = [dict(c) for c in full.get("columns", [])]
        exp = full.get("expandArrayPath") or ""
        self._set_blank_row_options_from_layout(full)
        self.layout_name_entry.delete(0, "end")
        self.layout_name_entry.insert(0, name)
        expand_values = ["(None)"] + list(dict.fromkeys(self._array_paths + ([exp] if exp else [])))
        self.expand_combo.configure(values=expand_values)
        self.expand_combo.set(exp if exp else "(None)")
        self._redraw_columns()

    def _load_layout(self):
        name = self.layout_name_entry.get().strip() or self.layout_combo.get()
        if not name:
            messagebox.showwarning("Name", "Enter or select a layout name.")
            return
        full = layouts.load_layout_full(name)
        self._columns = [dict(c) for c in full.get("columns", [])]
        exp = full.get("expandArrayPath") or ""
        self._set_blank_row_options_from_layout(full)
        expand_values = ["(None)"] + list(dict.fromkeys(self._array_paths + ([exp] if exp else [])))
        self.expand_combo.configure(values=expand_values)
        self.expand_combo.set(exp if exp else "(None)")
        self.layout_name_entry.delete(0, "end")
        self.layout_name_entry.insert(0, name)
        self._redraw_columns()
        messagebox.showinfo("Loaded", f"Layout '{name}' loaded.")

    def _save_layout(self):
        name = self.layout_name_entry.get().strip()
        if not name:
            messagebox.showwarning("Name", "Enter a layout name.")
            return
        if not self._columns:
            messagebox.showwarning("Columns", "Add at least one column.")
            return
        layouts.save_layout(
            name,
            self._columns,
            expand_array_path=self._get_expand_array_path(),
            extra=self._get_blank_row_options_for_save(),
        )
        self._refresh_layout_combo()
        self.layout_combo.set(name)
        messagebox.showinfo("Saved", f"Layout '{name}' saved.")

    def _export_layouts(self):
        """Export all layouts to a JSON file for sharing with customers."""
        names = layouts.list_layouts()
        if not names:
            messagebox.showinfo("Export layouts", "No layouts to export. Save at least one layout first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export layouts",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialfile="invoice_export_layouts.json",
        )
        if not path:
            return
        try:
            data = {"layouts": layouts.export_layouts_to_list(None), "version": 1}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Export layouts", f"Exported {len(data['layouts'])} layout(s) to {path}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def _import_layouts(self):
        """Import layouts from a JSON file (e.g. shared by another user)."""
        path = filedialog.askopenfilename(
            title="Import layouts",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                list_data = raw
            else:
                list_data = raw.get("layouts", raw.get("layout", []))
                if not isinstance(list_data, list):
                    list_data = [list_data] if list_data else []
            imported = layouts.import_layouts_from_list(list_data)
            self._refresh_layout_combo()
            if imported:
                messagebox.showinfo("Import layouts", f"Imported {len(imported)} layout(s): {', '.join(imported)}")
            else:
                messagebox.showwarning("Import layouts", "No valid layouts found in the file.")
        except Exception as e:
            messagebox.showerror("Import error", str(e))

    def get_current_columns(self) -> list[dict]:
        return list(self._columns)


class ExportFrame(ctk.CTkFrame):
    def __init__(self, master, on_export: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_export = on_export
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Query & export invoices", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 4))

        # Date filter: either date option or custom range (mutually exclusive)
        date_section = ctk.CTkFrame(self, fg_color="transparent")
        date_section.pack(fill="x", padx=10, pady=4)

        date_mode_row = ctk.CTkFrame(date_section, fg_color="transparent")
        date_mode_row.pack(fill="x")
        ctk.CTkLabel(date_mode_row, text="Date filter", width=100).pack(side="left", padx=(0, 8))
        self.date_mode = ctk.CTkSegmentedButton(
            date_mode_row,
            values=["Date option", "Date range"],
            command=self._on_date_mode_change,
        )
        self.date_mode.pack(side="left", padx=(0, 8))
        self.date_mode.set("Date option")

        self.option_row = ctk.CTkFrame(date_section, fg_color="transparent")
        self.option_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(self.option_row, text="", width=100).pack(side="left", padx=(0, 8))
        self.date_combo = ctk.CTkComboBox(self.option_row, values=DATE_OPTIONS, width=180)
        self.date_combo.set("Yesterday")
        self.date_combo.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(self.option_row, text="(e.g. Yesterday, Last_7_Days)", font=ctk.CTkFont(size=10), text_color="gray").pack(side="left", padx=(8, 0))

        self.range_row = ctk.CTkFrame(date_section, fg_color="transparent")
        ctk.CTkLabel(self.range_row, text="", width=100).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(self.range_row, text="Start (ISO-8601)", width=110).pack(side="left", padx=(0, 4))
        self.start_date_entry = ctk.CTkEntry(self.range_row, width=200, placeholder_text="2024-01-01T00:00:00Z")
        self.start_date_entry.pack(side="left", padx=(0, 4))
        ctk.CTkButton(self.range_row, text="Pick date", width=80, command=lambda: self._pick_date("start")).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(self.range_row, text="End (ISO-8601)", width=100).pack(side="left", padx=(0, 4))
        self.end_date_entry = ctk.CTkEntry(self.range_row, width=200, placeholder_text="2024-01-31T23:59:59Z")
        self.end_date_entry.pack(side="left", padx=(0, 4))
        ctk.CTkButton(self.range_row, text="Pick date", width=80, command=lambda: self._pick_date("end")).pack(side="left", padx=(0, 8))
        self.range_row.pack_forget()  # hidden by default (Date option shown)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row2, text="Layout", width=100).pack(side="left", padx=(0, 8))
        self.layout_combo = ctk.CTkComboBox(row2, values=layouts.list_layouts(), width=200)
        self.layout_combo.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="Refresh", width=70, command=self._refresh_layout_combo).pack(side="left", padx=(0, 8))
        self._refresh_layout_combo()

        self.log_text = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=8)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btn_row, text="Export to CSV", command=lambda: self._run_export("csv"), width=140).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Export to XLSX", command=lambda: self._run_export("xlsx"), width=140).pack(side="left", padx=(0, 8))

    def _on_date_mode_change(self, value: str):
        if value == "Date option":
            self.range_row.pack_forget()
            self.option_row.pack(fill="x", pady=(4, 0))
        else:
            self.option_row.pack_forget()
            self.range_row.pack(fill="x", pady=(4, 0))
            self._set_default_date_range()

    def _set_default_date_range(self):
        """Set Start to first day of current month 00:00, End to last day 23:59:59 if entries are empty."""
        from calendar import monthrange
        now = datetime.utcnow()
        y, m = now.year, now.month
        _, last = monthrange(y, m)
        start_default = f"{y}-{m:02d}-01T00:00:00Z"
        end_default = f"{y}-{m:02d}-{last:02d}T23:59:59Z"
        if not self.start_date_entry.get().strip():
            self.start_date_entry.delete(0, "end")
            self.start_date_entry.insert(0, start_default)
        if not self.end_date_entry.get().strip():
            self.end_date_entry.delete(0, "end")
            self.end_date_entry.insert(0, end_default)

    def _pick_date(self, which: str):
        """Open date picker (year/month/day dropdowns); set Start to 00:00:00Z or End to 23:59:59Z."""
        entry = self.start_date_entry if which == "start" else self.end_date_entry
        time_suffix = "T00:00:00Z" if which == "start" else "T23:59:59Z"
        current = entry.get().strip()
        try:
            if current and "T" in current:
                date_part = current.split("T")[0]
                initial = datetime.strptime(date_part, "%Y-%m-%d")
            else:
                initial = datetime.utcnow()
        except Exception:
            initial = datetime.utcnow()

        result = [None]

        def on_ok():
            try:
                y = int(year_combo.get())
                m = int(month_combo.get())
                d = int(day_combo.get())
                _, last = monthrange(y, m)
                d = min(d, last)
                result[0] = f"{y:04d}-{m:02d}-{d:02d}"
            except (ValueError, TypeError):
                pass
            win.destroy()

        win = ctk.CTkToplevel(self.winfo_toplevel())
        win.title("Start date" if which == "start" else "End date")
        win.geometry("260x120")
        win.minsize(240, 100)
        win.transient(self.winfo_toplevel())
        win.grab_set()

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(row, text="Year", width=28).pack(side="left", padx=(0, 2))
        years = [str(initial.year + i) for i in range(-5, 11)]
        year_combo = ctk.CTkComboBox(row, values=years, width=58)
        year_combo.set(str(initial.year))
        year_combo.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(row, text="Month", width=36).pack(side="left", padx=(0, 2))
        months = [f"{i:02d}" for i in range(1, 13)]
        month_combo = ctk.CTkComboBox(row, values=months, width=44)
        month_combo.set(f"{initial.month:02d}")
        month_combo.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(row, text="Day", width=22).pack(side="left", padx=(0, 2))
        days = [f"{i:02d}" for i in range(1, 32)]
        day_combo = ctk.CTkComboBox(row, values=days, width=44)
        _, last_day = monthrange(initial.year, initial.month)
        day_combo.set(f"{min(initial.day, last_day):02d}")
        day_combo.pack(side="left", padx=(0, 4))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(btn_row, text="OK", width=80, command=on_ok).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancel", width=80, fg_color="gray", command=win.destroy).pack(side="left")

        win.wait_window(win)
        if result[0]:
            iso = f"{result[0]}{time_suffix}"
            entry.delete(0, "end")
            entry.insert(0, iso)

    def _refresh_layout_combo(self):
        names = layouts.list_layouts()
        self.layout_combo.configure(values=names if names else ["(No layouts – create one in Manage Layouts)"])
        if names:
            self.layout_combo.set(names[0])

    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _run_export(self, fmt: str):
        layout_name = self.layout_combo.get()
        if not layout_name or layout_name.startswith("("):
            messagebox.showwarning("Layout", "Create and select a layout in Manage Layouts first.")
            return
        layout_full = layouts.load_layout_full(layout_name)
        columns = layout_full.get("columns", [])
        expand_array_path = layout_full.get("expandArrayPath")
        if not columns:
            messagebox.showwarning("Layout", "Selected layout has no columns.")
            return
        use_range = self.date_mode.get() == "Date range"
        start_date: Optional[str] = None
        end_date: Optional[str] = None
        date_option: Optional[str] = None
        if use_range:
            start_date = self.start_date_entry.get().strip() or None
            end_date = self.end_date_entry.get().strip() or None
            if not start_date or not end_date:
                messagebox.showwarning("Date range", "Enter both Start and End date (ISO-8601, e.g. 2024-01-01T00:00:00Z).")
                return
            self._log(f"Fetching invoices (startDate={start_date}, endDate={end_date})...")
        else:
            date_option = self.date_combo.get()
            self._log(f"Fetching invoices (dateOption={date_option})...")
        self.update_idletasks()
        try:
            items = api.fetch_all_invoice_items(
                date_option=date_option,
                filtered_fields=True,
                start_date=start_date,
                end_date=end_date,
            )
            self._log(f"Fetched {len(items)} invoice(s).")
            if not items:
                self._log("No data to export.")
                messagebox.showinfo("Export", "No invoices to export.")
                return
            default_name = export.default_export_filename(fmt)
            path = filedialog.asksaveasfilename(
                title=f"Save as {fmt.upper()}",
                defaultextension=f".{fmt}",
                filetypes=[(fmt.upper(), f"*.{fmt}"), ("All", "*.*")],
                initialfile=default_name,
            )
            if not path:
                return
            if fmt == "csv":
                export.export_to_csv(items, columns, path, expand_array_path=expand_array_path, layout_options=layout_full)
            else:
                export.export_to_xlsx(items, columns, path, expand_array_path=expand_array_path, layout_options=layout_full)
            num_rows = len(layouts.rows_from_items(items, columns, expand_array_path, layout_options=layout_full))
            self._log(f"Exported to {path}")
            messagebox.showinfo("Export", f"Exported {num_rows} row(s) to {path}")
            if self._on_export:
                self._on_export()
        except Exception as e:
            self._log(f"Error: {e}")
            messagebox.showerror("Export error", str(e))


def _docs_path() -> Path:
    """Path to README.md: bundle root when frozen, else project root."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "README.md"
    return Path(__file__).resolve().parent.parent / "README.md"


def _markdown_to_plain(md: str) -> str:
    """Convert basic Markdown to plain text for readable display in a textbox."""
    import re
    def strip_bold(s: str) -> str:
        return re.sub(r"\*\*([^*]+)\*\*", r"\1", s)

    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    in_code = False
    code_indent = "    "
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            if in_code:
                out.append("")
            continue
        if in_code:
            out.append(code_indent + line)
            continue
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if re.match(r"^[-_]{3,}$", stripped):
            out.append("")
            out.append("─" * 40)
            out.append("")
            continue
        if stripped.startswith("#"):
            level = 0
            while level < len(stripped) and stripped[level] == "#":
                level += 1
            rest = strip_bold(stripped[level:].strip())
            if level == 1:
                out.append("")
                out.append(rest.upper())
                out.append("")
            else:
                out.append("")
                out.append(rest)
                out.append("")
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            out.append("  • " + strip_bold(stripped[2:].strip()))
            continue
        if re.match(r"^\d+\.\s", stripped):
            out.append("  " + strip_bold(stripped))
            continue
        out.append(strip_bold(line))
    return "\n".join(out).strip() + "\n"


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Command Alkon – Invoice Export")
        self.geometry("900x640")
        self.minsize(760, 520)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_help_menu()

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.tabview.add("Export")
        self.tabview.add("Manage layouts")
        self.tabview.add("Settings")
        self.tabview.add("Documentation")

        self.config_frame = ConfigFrame(self.tabview.tab("Settings"), fg_color="transparent")
        self.config_frame.pack(fill="both", expand=True)

        self.layouts_frame = LayoutsFrame(self.tabview.tab("Manage layouts"), fg_color="transparent")
        self.layouts_frame.pack(fill="both", expand=True)

        self.export_frame = ExportFrame(self.tabview.tab("Export"), fg_color="transparent", on_export=self._on_export_done)
        self.export_frame.pack(fill="both", expand=True)

        self._doc_frame = ctk.CTkFrame(self.tabview.tab("Documentation"), fg_color="transparent")
        self._doc_frame.pack(fill="both", expand=True)
        self._doc_text = ctk.CTkTextbox(self._doc_frame, font=ctk.CTkFont(size=11), wrap="word")
        self._doc_text.pack(fill="both", expand=True, padx=12, pady=12)
        self._doc_text.insert("1.0", self._load_documentation())
        self._doc_text.configure(state="disabled")

    def _build_help_menu(self):
        try:
            tk_root = getattr(self, "tk", self)
            menubar = Menu(tk_root)
            help_menu = Menu(menubar, tearoff=0)
            help_menu.add_command(label="View documentation", command=self._focus_documentation_tab)
            menubar.add_cascade(label="Help", menu=help_menu)
            tk_root.configure(menu=menubar)
        except Exception:
            pass

    def _load_documentation(self) -> str:
        path = _docs_path()
        try:
            raw = path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            raw = ""
        if not raw.strip():
            return "Documentation not found. See README.md in the application folder."
        return _markdown_to_plain(raw)

    def _focus_documentation_tab(self):
        self.tabview.set("Documentation")

    def _on_export_done(self):
        self.export_frame._refresh_layout_combo()


def run_app():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
