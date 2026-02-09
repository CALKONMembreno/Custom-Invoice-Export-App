"""
UI: Config credentials, Manage layouts, Query & Export (CSV/XLSX).
"""
import json
from tkinter import filedialog, messagebox, simpledialog
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
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Manage layouts", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 4))
        ctk.CTkLabel(self, text="Add columns by field path (e.g. paymentTerms.id) and optional custom title. Add blank columns as needed.", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(0, 8))

        # Schema import
        schema_row = ctk.CTkFrame(self, fg_color="transparent")
        schema_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(schema_row, text="Import schema (JSON)", command=self._import_schema, width=160).pack(side="left", padx=(0, 8))
        self.schema_path_label = ctk.CTkLabel(schema_row, text="No schema loaded", text_color="gray")
        self.schema_path_label.pack(side="left")
        self._field_paths: list[str] = []
        self._array_paths: list[str] = []
        self._last_imported_schema_name: Optional[str] = None

        # Expand array (optional): one row per array element, parent fields repeated
        expand_row = ctk.CTkFrame(self, fg_color="transparent")
        expand_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(expand_row, text="Expand array", width=100).pack(side="left", padx=(0, 8))
        self.expand_combo = ctk.CTkComboBox(expand_row, values=["(None)"], width=200)
        self.expand_combo.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(expand_row, text="One row per element; invoice fields repeat", font=ctk.CTkFont(size=10), text_color="gray").pack(side="left", padx=(8, 0))

        # Layout name
        name_row = ctk.CTkFrame(self, fg_color="transparent")
        name_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(name_row, text="Layout name", width=100).pack(side="left", padx=(0, 8))
        self.layout_name_entry = ctk.CTkEntry(name_row, placeholder_text="e.g. My Export", width=200)
        self.layout_name_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row, text="Load layout", command=self._load_layout, width=100).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row, text="Save layout", command=self._save_layout, width=100).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row, text="Export layouts", command=self._export_layouts, width=110).pack(side="left", padx=(0, 8))
        ctk.CTkButton(name_row, text="Import layouts", command=self._import_layouts, width=110).pack(side="left", padx=(0, 8))
        self.layout_combo = ctk.CTkComboBox(name_row, values=layouts.list_layouts(), width=140, command=self._on_select_layout)
        self.layout_combo.pack(side="left", padx=(0, 8))

        # Column list
        ctk.CTkLabel(self, text="Columns (field path → custom title; blank = empty column)", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 4))
        list_frame = ctk.CTkScrollableFrame(self, height=200, fg_color=("gray85", "gray20"))
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.column_list_frame = list_frame

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btn_row, text="Add field column", command=self._add_field_column, width=140).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Add blank column", command=self._add_blank_column, width=140).pack(side="left", padx=(0, 8))
        self._refresh_layout_combo()
        self._redraw_columns()
        self._load_last_schema_if_saved()

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
        layouts.save_layout(name, self._columns, expand_array_path=self._get_expand_array_path())
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

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row1, text="Date range", width=100).pack(side="left", padx=(0, 8))
        self.date_combo = ctk.CTkComboBox(row1, values=DATE_OPTIONS, width=180)
        self.date_combo.set("Yesterday")
        self.date_combo.pack(side="left", padx=(0, 8))

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
        date_option = self.date_combo.get()
        self._log(f"Fetching invoices (dateOption={date_option})...")
        self.update_idletasks()
        try:
            items = api.fetch_all_invoice_items(date_option=date_option, filtered_fields=True)
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
                export.export_to_csv(items, columns, path, expand_array_path=expand_array_path)
            else:
                export.export_to_xlsx(items, columns, path, expand_array_path=expand_array_path)
            num_rows = len(layouts.rows_from_items(items, columns, expand_array_path))
            self._log(f"Exported to {path}")
            messagebox.showinfo("Export", f"Exported {num_rows} row(s) to {path}")
            if self._on_export:
                self._on_export()
        except Exception as e:
            self._log(f"Error: {e}")
            messagebox.showerror("Export error", str(e))


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Command Alkon – Invoice Export")
        self.geometry("720x560")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self, width=700, height=520)
        self.tabview.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.tabview.add("Manage layouts")
        self.tabview.add("Export")
        self.tabview.add("Config")

        self.config_frame = ConfigFrame(self.tabview.tab("Config"), fg_color="transparent")
        self.config_frame.pack(fill="both", expand=True)

        self.layouts_frame = LayoutsFrame(self.tabview.tab("Manage layouts"), fg_color="transparent")
        self.layouts_frame.pack(fill="both", expand=True)

        self.export_frame = ExportFrame(self.tabview.tab("Export"), fg_color="transparent", on_export=self._on_export_done)
        self.export_frame.pack(fill="both", expand=True)

    def _on_export_done(self):
        self.export_frame._refresh_layout_combo()


def run_app():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
