# Custom Invoice Export App

On-premise desktop app to query Command Alkon billing invoices and export to CSV or XLSX using configurable layouts.

## Features

- **Config (credentials)** – Store API credentials encrypted (Entity Ref, API Key, Client ID, Client Secret, API Scope Ref). Same OAuth-style login/refresh as `example.py`.
- **Manage layouts** – Define export columns by field path (e.g. `paymentTerms.id`, `profile.firstName`) with optional custom column titles. Add blank columns. Import a JSON schema to get a list of field paths for reuse. **Export layouts** to a JSON file to share with customers; **Import layouts** to load a shared file.
- **Export** – Pick date range (`dateOption`: Today, Yesterday, Last_7_Days, etc.), choose a layout, then export to CSV or XLSX. Fetches all pages automatically using `pageToken`.

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

The executable is created in `dist/InvoiceExport.exe`. Config, layouts, and imported schemas are stored in the `config/` folder next to the exe (or next to the project when run from source).

## Export and import layouts (for customers)

To reuse layouts across machines or share with customers:

- **Export layouts** – In Manage layouts, click **Export layouts**, choose a location, and save a `.json` file (e.g. `invoice_export_layouts.json`). The file contains all your saved layouts (columns, titles, expand array, blank column custom text).
- **Import layouts** – On another machine or for a customer, click **Import layouts** and select that JSON file. All layouts in the file are added (existing names are overwritten). The customer can then use those layouts in the Export tab.

The export file is plain JSON and can be versioned or edited if needed.

## Schema import

Use **Manage layouts** → **Import schema (JSON)** and select a JSON file (e.g. `exampleschema.json`) that has an `items` array. The app extracts nested field paths (e.g. `paymentTerms.id`) so you can pick them when adding columns. Imported files are copied to `config/schemas/` for reuse.

## How arrays are managed

Invoice data often contains **arrays** (e.g. `contacts`, `invoiceSections`, `billables`, `lineItems`). Layout field paths handle them like this:

- **First element by default** – If the next path segment is a property name (not a number), the app uses the **first** element of the array.  
  Examples:  
  - `contacts.email` → first contact’s email  
  - `contacts.firstName` → first contact’s first name  
  - `profile.firstName` → from the single `profile` object (no array)

- **Specific index** – Use a **numeric** segment to target an index.  
  Examples:  
  - `contacts.0.email` → first contact’s email  
  - `contacts.1.email` → second contact’s email  
  - `invoiceSections.0.projectName` → first section’s project name  
  - `invoiceSections.1.customerName` → second section’s customer name  

- **Nested arrays** – Same rules apply at each level: use the next key for “first element” or a number for an index.  
  Example: `invoiceSections.0.billables.0.orderId` → first section’s first billable’s order ID.

- **Whole array/object** – If the path ends at an array or object, the cell value is the **JSON string** of that value (e.g. for debugging or custom use).

When you **import a schema**, the extracted field paths use the first element for arrays (e.g. `contacts.email`), so you get one column per logical field. You can still add or edit paths manually to use explicit indices (e.g. `contacts.1.phone`) when needed.

## Export all array items and repeated headers

You can **export one row per array element** instead of one row per invoice:

1. In **Manage layouts**, set **Expand array** to the array you want to expand (e.g. `contacts`, `invoiceSections`). The dropdown is filled when you import a schema (it lists top-level arrays). Choose **(None)** for normal export (one row per invoice).
2. Save the layout. When you export, the app will:
   - Output **one row for each element** in that array (e.g. one row per contact).
   - **Repeat the same column headers** once at the top (no repeated header rows in the file).
   - **Repeat parent/invoice fields** on every row: invoice-level columns (e.g. `id`, `crn`, `paymentTerms.id`) have the same value on each row for that invoice; columns under the expanded array (e.g. `contacts.email`) get the value for the current element.

Example: with **Expand array** = `contacts` and columns `id`, `crn`, `contacts.email`, `contacts.firstName`, an invoice with two contacts produces two data rows, both with the same `id` and `crn`, and different `contacts.email` / `contacts.firstName`. Headers appear once; the “headers” (invoice-level fields) are repeated on each row.

If the array is empty for an invoice, one row is still emitted with invoice fields filled and the array columns blank.

## Date options

Supported `dateOption` values: Today, Yesterday, Tomorrow, This_Week, Last_3_Days, Last_7_Days, Last_30_Days, This_Month, Last_Month, Last_3_Months, Last_6_Months, Last_12_Months, Last_12_Hours, Last_18_Hours, Last_24_Hours, This_Year, Last_Year.
