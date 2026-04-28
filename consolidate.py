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
    'asset tag':         'serial_no',
    's.no':              'serial_no',
    'laptop s.no':       'serial_no',
    'laptop s.no.':      'serial_no',

    # Current / primary user
    'full name':         'current_user',
    'current user':      'current_user',
    'user name':         'current_user',
    'username':          'current_user',
    'assigned to':       'current_user',
    'name':              'current_user',

    # Old / previous user
    'old user':          'old_user',
    'previous user':     'old_user',

    # Employee code / ID
    'employee id':       'employee_code',
    'employee code':     'employee_code',
    'emp id':            'employee_code',
    'emp code':          'employee_code',

    # PO Number
    'po number':         'po_number',
    'po no.':            'po_number',
    'po no':             'po_number',

    # CPU
    'cpu':               'cpu',
    'system details':    'cpu',
    'processor':         'cpu',

    # Make / Model
    'make':              'make',
    'brand':             'make',
    'model':             'model',
    'model no':          'model',
    'model no.':         'model',
    'make/model':        'make_model_combined',
    'brand/model':       'make_model_combined',

    # Device type
    'type':              'type',
    'device type':       'type',
    'asset type':        'type',

    # Host name
    'host id':           'host_name',
    'host name':         'host_name',
    'hostname':          'host_name',
    'computer name':     'host_name',
    'system name':       'host_name',
    'device name':       'host_name',

    # RAM
    'memory':            'ram',
    'ram':               'ram',
    'ram (gb)':          'ram',

    # OS
    'window os':         'os',
    'windows os':        'os',
    'os':                'os',
    'operating system':  'os',

    # OS Build / Version — FIX: added more common build/version names
    '22h2':              'os_build',
    '21h2':              'os_build',
    '23h2':              'os_build',
    '24h2':              'os_build',
    'os build':          'os_build',
    'os version':        'os_build',
    'windows version':   'os_build',
    'build':             'os_build',
    'build version':     'os_build',

    # Storage
    'hdd/ssd':           'storage',
    'hdd':               'storage',
    'ssd':               'storage',
    'storage':           'storage',
    'hard disk':         'storage',
    'disk':              'storage',

    # Equipment lifecycle
    'equipment life cycle': 'lifecycle',
    'life cycle':           'lifecycle',
    'lifecycle':            'lifecycle',
    'age':                  'lifecycle',

    # Designation
    'designation':       'designation',
    'job title':         'designation',
    'title':             'designation',

    # Agreement columns
    'laptop agreement document verified chd':      'agreement_verified',
    'laptop agreement document verified or not':   'agreement_verified',
    'laptop aggrement':                            'agreement_doc',
    'laptop agreement document':                   'agreement_doc',
    'agreement':                                   'agreement_doc',

    # Employee status
    'employee status':   'employee_status',
    'status':            'employee_status',

    # Hardware location
    'hardware location': 'location',
    'location':          'location',
    'office':            'location',
    'city':              'location',

    # Seat number
    'seat number':       'seat_number',
    'seat no':           'seat_number',
    'seat no.':          'seat_number',

    # Row number
    'sr.no.':            'sr_no',
    'sr. no':            'sr_no',
    'sr no':             'sr_no',
    'sr.no':             'sr_no',
    's. no':             'sr_no',
    'no.':               'sr_no',
    'no':                'sr_no',
}

STANDARD_COLS = [
    'sr_no', 'employee_status', 'old_user', 'current_user',
    'employee_code', 'seat_number', 'location', 'po_number',
    'cpu', 'make', 'model', 'type', 'serial_no', 'host_name',
    'ram', 'os', 'os_build', 'storage', 'lifecycle',
    'designation', 'agreement_verified', 'agreement_doc',
    'source_sheet'
]

# Keywords in current_user that indicate IT stock (not a real person)
# FIX: changed from exact-match list to keyword list for substring matching
STOCK_KEYWORDS = [
    'it stock', 'stock', 'new dev laptop', 'faulty',
    'repair', 'server room', 'spare', 'unassigned',
]
STOCK_EXACT = {'na', 'nan', 'n/a', 'nil', '-', '', 'none'}


# ─── BUG FIX 1: Column name cleaner ──────────────────────────────────────────
# Excel cells often contain non-breaking spaces (\xa0) or other
# invisible unicode that defeats a plain .strip().lower()

def clean_col_name(col):
    """Normalize a raw Excel column header to a plain lowercase string."""
    s = str(col)
    # Replace all whitespace variants (including \xa0 non-breaking space)
    s = re.sub(r'[\s\xa0]+', ' ', s)
    return s.strip().lower()


# ─── BUG FIX 2: Header-row auto-detection ────────────────────────────────────
# Many inventory sheets have a merged title row (e.g. "GGN Inventory") as
# row 0. Without this fix pandas uses that as the header and no column
# names ever match COLUMN_MAP.

def find_header_row(excel_path, sheet, max_scan=10):
    """
    Scan the first `max_scan` rows and return the 0-based row index
    whose values best match COLUMN_MAP keys.  Falls back to 0 if
    nothing matches at all.
    """
    try:
        df_raw = pd.read_excel(
            excel_path, sheet_name=sheet,
            header=None, dtype=str, nrows=max_scan
        )
    except Exception:
        return 0

    best_row, best_score = 0, 0
    for i, row in df_raw.iterrows():
        score = sum(
            1 for v in row.dropna()
            if clean_col_name(v) in COLUMN_MAP
        )
        if score > best_score:
            best_score = score
            best_row = i

    return best_row


# ─── Normalizers ─────────────────────────────────────────────────────────────

def normalize_ram(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    val = str(val).upper().replace(' ', '')
    m = re.search(r'(\d+)', val)
    return f"{m.group(1)} GB" if m else str(val).strip()


# BUG FIX 3: normalize_os used bare `'11' in v` which matched strings like
# "Office 2011" or build version numbers, incorrectly labelling them
# "Windows 11".  Now requires the word 'windows' to be present first.

def normalize_os(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    v = str(val).strip().lower()
    if 'linux' in v or 'ubuntu' in v or 'debian' in v:
        return 'Linux'
    if 'mac' in v or 'macos' in v or 'osx' in v or 'os x' in v:
        return 'macOS'
    # Require 'windows' context before deciding the version number
    if 'windows' in v:
        if '11' in v:
            return 'Windows 11'
        if '10' in v:
            return 'Windows 10'
        if '7' in v:
            return 'Windows 7'
        return 'Windows'
    # Fall back: bare version numbers with no OS name mentioned
    if re.search(r'\b11\b', v):
        return 'Windows 11'
    if re.search(r'\b10\b', v):
        return 'Windows 10'
    return str(val).strip()


def normalize_type(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    v = str(val).strip().lower()
    if 'laptop' in v or 'notebook' in v:
        return 'Laptop'
    if 'mac mini' in v:
        return 'MAC Mini'
    if 'macbook' in v:
        return 'MacBook'
    if 'desktop' in v or 'cpu' in v or 'tower' in v:
        return 'Desktop'
    return str(val).strip().title()


def normalize_make(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan'):
        return ''
    return str(val).strip().title()


# ─── BUG FIX 4: Duplicate-column coalescing after mapping ────────────────────
# If a sheet has both "RAM" and "Memory" columns, both rename to "ram".
# Pandas stores two columns with the same name, and df[STANDARD_COLS]
# then returns duplicate columns which breaks downstream processing.
# Fix: merge duplicates by taking the first non-empty value per row.

def coalesce_duplicate_cols(df):
    """Merge columns that share the same name after mapping."""
    seen = {}
    for i, col in enumerate(df.columns):
        seen.setdefault(col, []).append(i)

    duplicates = {col: idxs for col, idxs in seen.items() if len(idxs) > 1}
    if not duplicates:
        return df

    drop_positions = []
    for col, positions in duplicates.items():
        # Coalesce: first non-empty value wins
        merged = df.iloc[:, positions[0]].copy()
        for pos in positions[1:]:
            other = df.iloc[:, pos]
            # Fill blanks / NaNs in `merged` from `other`
            mask = merged.isna() | (merged.astype(str).str.strip() == '')
            merged = merged.where(~mask, other)
            drop_positions.append(pos)
        df.iloc[:, positions[0]] = merged

    # Drop the extra positions (keep the first)
    cols_to_drop = df.columns[drop_positions]
    df = df.drop(columns=cols_to_drop)
    return df


# ─── Column mapping ───────────────────────────────────────────────────────────

def map_columns(df):
    renamed = {}
    for col in df.columns:
        key = clean_col_name(col)   # BUG FIX 1: use cleaned key
        if key in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[key]
    df = df.rename(columns=renamed)

    # BUG FIX 4: coalesce any duplicate-named columns before proceeding
    df = coalesce_duplicate_cols(df)

    # Split combined Make/Model column (e.g. "Lenovo L14" → Lenovo, L14)
    if 'make_model_combined' in df.columns:
        if 'make' not in df.columns:
            df['make'] = df['make_model_combined'].apply(
                lambda x: (
                    str(x).split()[0]
                    if pd.notna(x) and str(x).strip() not in ('', 'nan')
                    else np.nan
                )
            )
        if 'model' not in df.columns:
            df['model'] = df['make_model_combined'].apply(
                lambda x: (
                    ' '.join(str(x).split()[1:])
                    if pd.notna(x) and len(str(x).split()) > 1
                    and str(x).strip() not in ('', 'nan')
                    else np.nan
                )
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
            # BUG FIX 2: detect the real header row before reading
            header_row = find_header_row(excel_path, sheet)
            if header_row > 0:
                print(f"  Header found at row {header_row} : {sheet}")

            df = pd.read_excel(
                excel_path, sheet_name=sheet,
                dtype=str, header=header_row
            )
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
    master['os']           = master['os'].apply(normalize_os)      # BUG FIX 3
    master['type']         = master['type'].apply(normalize_type)
    master['make']         = master['make'].apply(normalize_make)
    master['current_user'] = master['current_user'].apply(lambda x: str(x).strip())

    # ── BUG FIX 5: tag stock vs assigned using substring matching ─────────────
    # Old code used `.isin(STOCK_PATTERNS)` which required an exact match.
    # Values like "IT Stock - GGN" or "Faulty/Repair" were silently misclassified
    # as assigned equipment.

    def _is_stock(user_val):
        v = str(user_val).strip().lower()
        if v in STOCK_EXACT:
            return True
        return any(kw in v for kw in STOCK_KEYWORDS)

    master['is_assigned'] = ~master['current_user'].apply(_is_stock)

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