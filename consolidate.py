"""
consolidate.py
--------------
Reads all sheets from your inventory Excel file,
maps column names to a standard schema, cleans data,
and saves a single master_inventory.csv.

Usage:
    python consolidate.py <your_file.xlsx>
"""

import pandas as pd
import numpy as np
import re
import os
import sys

# ─── Standard column mapping ─────────────────────────────────────────────────
# Maps every known column name variation → standard name
COLUMN_MAP = {
    # Serial number
    'laptop serial no.': 'serial_no',
    'laptop serial no':  'serial_no',
    'serial no':         'serial_no',
    'serial no.':        'serial_no',
    'serial number':     'serial_no',

    # Current / primary user
    'full name':         'current_user',
    'current user':      'current_user',

    # Old / previous user
    'old user':          'old_user',

    # Employee code / ID
    'employee id':       'employee_code',
    'employee code':     'employee_code',

    # PO Number
    'po number':         'po_number',
    'po no.':            'po_number',
    'po no':             'po_number',

    # CPU
    'cpu':               'cpu',
    'system details':    'cpu',

    # Make / Model
    'make':              'make',
    'model':             'model',
    'make/model':        'make_model_combined',

    # Device type
    'type':              'type',

    # Host name
    'host id':           'host_name',
    'host name':         'host_name',

    # RAM
    'memory':            'ram',
    'ram':               'ram',

    # OS
    'window os':         'os',
    'windows os':        'os',
    'os':                'os',

    # OS Build / Version
    '22h2':              'os_build',

    # Storage
    'hdd/ssd':           'storage',
    'hdd':               'storage',

    # Equipment lifecycle
    'equipment life cycle': 'lifecycle',

    # Designation
    'designation':       'designation',

    # Agreement columns
    'laptop agreement document verified chd':      'agreement_verified',
    'laptop agreement document verified or not':   'agreement_verified',
    'laptop aggrement':                            'agreement_doc',
    'laptop agreement document':                   'agreement_doc',

    # Employee status
    'employee status':   'employee_status',

    # Hardware location
    'hardware location': 'location',

    # Seat number
    'seat number':       'seat_number',

    # Row number
    'sr.no.':            'sr_no',
    'sr. no':            'sr_no',
    'sr no':             'sr_no',
    'sr.no':             'sr_no',
}

STANDARD_COLS = [
    'sr_no', 'employee_status', 'old_user', 'current_user',
    'employee_code', 'seat_number', 'location', 'po_number',
    'cpu', 'make', 'model', 'type', 'serial_no', 'host_name',
    'ram', 'os', 'os_build', 'storage', 'lifecycle',
    'designation', 'agreement_verified', 'agreement_doc',
    'source_sheet'
]

# Values in current_user that indicate IT stock (not a real person)
STOCK_PATTERNS = [
    'it stock', 'stock', 'new dev laptop', 'na', 'nan',
    'faulty', 'repair', 'it stock ggn', 'it stock noida',
    'it stock chd', 'it stock mohali', 'server room'
]


# ─── Normalizers ─────────────────────────────────────────────────────────────

def normalize_ram(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    val = str(val).upper().replace(' ', '')
    m = re.search(r'(\d+)', val)
    return f"{m.group(1)} GB" if m else str(val).strip()


def normalize_os(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    v = str(val).strip().lower()
    if 'linux' in v:
        return 'Linux'
    if 'mac' in v:
        return 'macOS'
    if '11' in v:
        return 'Windows 11'
    if '10' in v:
        return 'Windows 10'
    return str(val).strip()


def normalize_type(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    v = str(val).strip().lower()
    if 'laptop' in v:
        return 'Laptop'
    if 'mac mini' in v:
        return 'MAC Mini'
    if 'desktop' in v or 'cpu' in v:
        return 'Desktop'
    return str(val).strip().title()


def normalize_make(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    return str(val).strip().title()


# ─── Column mapping ───────────────────────────────────────────────────────────

def map_columns(df):
    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[key]
    df = df.rename(columns=renamed)

    # Split combined Make/Model column (e.g. "Lenovo L14" → Lenovo, L14)
    if 'make_model_combined' in df.columns:
        if 'make' not in df.columns:
            df['make'] = df['make_model_combined'].apply(
                lambda x: str(x).split()[0] if pd.notna(x) and str(x).strip() else np.nan
            )
        if 'model' not in df.columns:
            df['model'] = df['make_model_combined'].apply(
                lambda x: ' '.join(str(x).split()[1:]) if pd.notna(x) and len(str(x).split()) > 1 else np.nan
            )
        df.drop(columns=['make_model_combined'], inplace=True)

    return df


# ─── Main consolidation ───────────────────────────────────────────────────────

def consolidate(excel_path):
    if not os.path.exists(excel_path):
        print(f"ERROR: File not found → {excel_path}")
        sys.exit(1)

    print(f"\nReading: {excel_path}")
    xl = pd.ExcelFile(excel_path)
    sheets = xl.sheet_names
    print(f"Found {len(sheets)} sheets: {sheets}\n")

    all_dfs = []
    skipped = []

    for sheet in sheets:
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet, dtype=str)
            df = df.dropna(how='all').dropna(axis=1, how='all')

            if df.empty:
                print(f"  SKIP (empty)     : {sheet}")
                skipped.append(sheet)
                continue

            df['source_sheet'] = sheet
            df = map_columns(df)

            # Add any missing standard columns
            for col in STANDARD_COLS:
                if col not in df.columns:
                    df[col] = np.nan

            df = df[STANDARD_COLS]

            # Drop rows where current_user is completely blank
            df = df[df['current_user'].notna()]
            df = df[df['current_user'].astype(str).str.strip() != '']

            print(f"  OK ({len(df):>3} rows)    : {sheet}")
            all_dfs.append(df)

        except Exception as e:
            print(f"  ERROR            : {sheet} → {e}")
            skipped.append(sheet)

    if not all_dfs:
        print("\nNo data loaded. Check your file and sheet structure.")
        sys.exit(1)

    master = pd.concat(all_dfs, ignore_index=True)
    master = master.fillna('')

    # ── Normalize fields ──
    master['ram']          = master['ram'].apply(normalize_ram)
    master['os']           = master['os'].apply(normalize_os)
    master['type']         = master['type'].apply(normalize_type)
    master['make']         = master['make'].apply(normalize_make)
    master['current_user'] = master['current_user'].apply(lambda x: str(x).strip())

    # ── Tag stock vs assigned ──
    master['is_assigned'] = ~master['current_user'].str.lower().str.strip().isin(STOCK_PATTERNS)

    # ── Save ──
    out_dir  = os.path.dirname(os.path.abspath(excel_path))
    out_path = os.path.join(out_dir, 'master_inventory.csv')
    master.to_csv(out_path, index=False)

    # ── Summary ──
    print(f"\n{'='*55}")
    print(f"  Total rows merged     : {len(master)}")
    print(f"  Assigned equipment    : {master['is_assigned'].sum()}")
    print(f"  In stock / unassigned : {(~master['is_assigned']).sum()}")
    print(f"  Laptops               : {(master['type'] == 'Laptop').sum()}")
    print(f"  Desktops              : {(master['type'] == 'Desktop').sum()}")
    print(f"  Mac Mini              : {(master['type'] == 'MAC Mini').sum()}")
    print(f"  Missing serial nos.   : {(master['serial_no'] == '').sum()}")
    print(f"  Agreements verified   : {(master['agreement_verified'] != '').sum()}")
    if skipped:
        print(f"  Skipped sheets        : {skipped}")
    print(f"{'='*55}")
    print(f"\n  Saved → {out_path}\n")

    return master


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python consolidate.py <path_to_inventory.xlsx>")
        print("Example: python consolidate.py Inventory.xlsx")
        sys.exit(1)

    consolidate(sys.argv[1])
