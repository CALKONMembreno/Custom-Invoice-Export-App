# Command Alkon – Invoice Export

On-premise desktop app to query Command Alkon billing invoices and export to CSV or XLSX using configurable layouts.

Created by: Cristopher Membreno, Solutions Specialist

Support: cmembreno@commandalkon.com, +13464957475

---

## Tabs

- **Export** – Choose date filter, layout, and export to CSV or XLSX.
- **Manage layouts** – Define columns, conditions, expand array, import schema, save/load/export/import layouts.
- **Settings** – Store API credentials (encrypted).

---

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

## Build .exe (on-premise)

```bash
pip install -r requirements.txt
pyinstaller invoice_export.spec
```

The executable is in `dist/InvoiceExport.exe`. Config, layouts, and imported schemas are stored in the `config/` folder next to the exe (or next to the project when run from source).

---

## Settings (API credentials)

Store **Entity Ref**, **API Key**, **Client ID**, **Client Secret**, and **API Scope Ref**. Credentials are saved encrypted. The app uses the same OAuth-style login and token refresh as the reference example.

---

## Export tab

1. **Date filter**
   - **Date option** – Use a preset: Today, Yesterday, Last_7_Days, Last_Month, etc.
   - **Date range** – Enter Start and End in ISO-8601 (e.g. `2024-01-01T00:00:00Z`, `2024-01-31T23:59:59Z`). Use **Pick date** for each to choose Year/Month/Day; Start defaults to 00:00:00 and End to 23:59:59. When you switch to Date range, defaults are first and last day of the current month.
2. **Layout** – Choose a saved layout (create and edit in Manage layouts).
3. **Export to CSV** or **Export to XLSX** – Fetches all invoice pages and writes the file.

---

## Manage layouts

- **Import schema (JSON)** – Load a JSON file (e.g. `exampleschema.json`) with an `items` structure. The app extracts field paths (e.g. `paymentTerms.id`, `invoiceSections.billables.lineItems.q`) and saves the file to `config/schemas/` for reuse. The **Expand array** dropdown and **Pick…** field list are filled from the schema.
- **Expand array** – Choose an array path (e.g. `invoiceSections.billables.lineItems`) to export **one row per element**; invoice-level columns repeat on each row. Use **(None)** for one row per invoice.
- **Columns** – Add **field column** (path + optional title) or **blank column** (title + optional custom text in every row). Use **Pick…** to choose a path from the schema. Reorder with the grip (⋮⋮), ▲/▼, or drag. **Conditions…** lets you define replace rules (see below).
- **Layout name** – **Load** / **Save** layout by name. **Export layouts** writes all saved layouts to a JSON file; **Import layouts** loads that file (overwrites same names).

### Optional: blank rows (empty lines)

Layouts can optionally insert **blank rows** into the export output (CSV/XLSX). This can be configured in the **Manage layouts** tab (Empty rows / Empty row rules…), and is also stored in the saved layout JSON file in `config/layouts/*.json`.

- **blankRowsBeforeEachRow** – Integer. Adds N blank rows **before every exported row**.
- **blankRowsBeforeFirstRow** – Integer. Adds N blank rows **before the first exported row** (right after headers).
- **blankRowsBeforeEmptyExpandedRow** – Integer (advanced JSON-only option). When **Expand array** is set and an invoice has an empty array at that path, the app still emits one row (parent columns filled, expanded columns empty). Set this to add N extra blank rows **before** that “empty expanded” row.
- **blankRowsBefore** – List of rules. Each rule can insert blank rows before any output row when the resolved value at a path matches a condition.

Example:

```json
{
   "name": "My Layout",
   "columns": [
      {"fieldPath": "id", "title": "InvoiceNbr", "blank": false},
      {"fieldPath": "invoiceSections.billables.lineItems.productId", "title": "ProductId", "blank": false}
   ],
   "expandArrayPath": "invoiceSections.billables.lineItems",
   "blankRowsBeforeFirstRow": 3,
   "blankRowsBeforeEmptyExpandedRow": 2,
   "blankRowsBefore": [
      {"path": "invoiceSections.billables.lineItems.productId", "operator": "is_blank", "count": 1}
   ]
}
```

### Column conditions

For any field column, **Conditions…** lets you add rules: **if** the cell value matches a rule, **replace** with a given value. First matching rule wins. Supported operators:

- **equal** / **not equal** – Exact match (text or number).
- **contains** / **not contains** – Substring in cell value.
- **greater** / **greater or equal** / **less** / **less or equal** – Numeric when both sides are numbers; otherwise string comparison.
- **is blank** / **is not blank** – No comparison value; match empty or non-empty cells.

---

## Field paths and arrays

- **Dot notation** – Paths like `paymentTerms.id`, `profile.firstName`, `invoiceSections.billables.lineItems.q`.
- **First element** – If the next segment is a property name, the app uses the **first** element of an array (e.g. `contacts.email` → first contact’s email).
- **Numeric index** – Use a number for a specific index: `contacts.0.email`, `invoiceSections.1.projectName`.
- **Expand array** – With **Expand array** set (e.g. `invoiceSections.billables.lineItems`), the export has one row per array element; headers appear once; invoice-level columns repeat on each row.

---

## Export and import layouts (sharing)

- **Export layouts** – Saves all saved layouts to a single JSON file (columns, titles, conditions, expand array, blank column text). Share this file with other users or machines.
- **Import layouts** – Load that JSON file; all layouts in the file are added (same names overwrite). No need to reconfigure columns by hand.

---

## Date options (presets)

When using **Date option**: Today, Yesterday, Tomorrow, This_Week, Last_3_Days, Last_7_Days, Last_30_Days, This_Month, Last_Month, Last_3_Months, Last_6_Months, Last_12_Months, Last_12_Hours, Last_18_Hours, Last_24_Hours, This_Year, Last_Year.

---

## Requirements

- Python 3.10+
- requests, customtkinter, cryptography, openpyxl (see `requirements.txt`)
