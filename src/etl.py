"""ETL: stack all leaderboard xlsx files into one clean parquet.

Row types in the raw data
- real unit      : a physical district / project / sector
- Total          : state total (district file only). Equals sum(real units) + Unmapped.
- Unmapped       : parents we cannot place in any district/project/sector. Not a
                   physical location, so it is never ranked; it is reported separately.
"""
import os
import glob
import pandas as pd
import numpy as np
import re
from src.config import RAW_DATA_DIR, PARQUET_FILE, QUALITY_FILE, COLUMN_MAP

UNMAPPED_LABEL = "Unmapped (location unknown)"
TOTAL_LABEL = "State total"
ID_COLS = ['district_id', 'project_code', 'sector_code']
KEY_COLS = ['level', 'date', 'state_name', 'unit_id']
LEVEL_FOLDERS = {'District_level': 'district', 'Project Leaderboard': 'project', 'Sector Leaderboard': 'sector'}


def safe_div(num, den):
    """Division returning NaN when the denominator is 0 or missing."""
    num = pd.to_numeric(num, errors='coerce')
    den = pd.to_numeric(den, errors='coerce')
    return num / den.where(den != 0)


def split_district(name):
    """'Ambala (अंबाला)' -> ('Ambala', 'अंबाला')."""
    if pd.isna(name):
        return None, None
    m = re.search(r'\((.*?)\)', str(name))
    english = re.sub(r'\(.*?\)', '', str(name)).strip()
    return english, (m.group(1).strip() if m else None)


def _as_id(s):
    """Mixed int/float/str ids -> clean strings ('108.0' -> '108'); NaN stays NaN."""
    return s.map(lambda v: np.nan if pd.isna(v) else re.sub(r'\.0$', '', str(v).strip()))


def _level_of(path):
    base = os.path.basename(path).lower()
    if 'launch' in base:
        return None  # launch file has a different grain; not used in v1
    for key, level in (('district', 'district'), ('project', 'project'), ('sector', 'sector')):
        if key in base:
            return level
    return None


def load_raw():
    frames, dropped_null_dates = [], 0
    for f in glob.glob(os.path.join(RAW_DATA_DIR, '**', '*.xlsx'), recursive=True):
        level = _level_of(f)
        if level is None or os.path.basename(f).startswith('~$'):  # skip Excel lock files
            continue
        raw = pd.read_excel(f)
        n = len(raw)
        raw = raw.dropna(subset=['Date'])  # blank spacer rows
        dropped_null_dates += n - len(raw)
        raw['level'] = level
        frames.append(raw)
    return pd.concat(frames, ignore_index=True), dropped_null_dates


def build_units(df):
    """Create unit_id / unit_name and the is_total / is_unmapped flags."""
    for c in ID_COLS:
        if c in df.columns:
            df[c] = _as_id(df[c])

    names = df['district'].astype(str).str.strip().str.lower()
    df['is_total'] = (df['level'] == 'district') & (names == 'total')

    unmapped = df['district'].isna() | (df['district_id'].astype(str).str.lower() == 'unmapped')
    unmapped |= df['project_name'].astype(str).str.lower().eq('unmapped') if 'project_name' in df else False
    unmapped |= df['sector_code'].astype(str).str.lower().eq('unmapped') if 'sector_code' in df else False
    df['is_unmapped'] = unmapped & ~df['is_total']

    id_col = {'district': 'district_id', 'project': 'project_code', 'sector': 'sector_code'}
    name_col = {'district': 'district', 'project': 'project_name', 'sector': 'sector_name'}
    df['unit_id'] = pd.Series(np.nan, index=df.index, dtype=object)
    df['unit_name'] = pd.Series(np.nan, index=df.index, dtype=object)
    for level in id_col:
        m = df['level'] == level
        df.loc[m, 'unit_id'] = df.loc[m, id_col[level]]
        df.loc[m, 'unit_name'] = df.loc[m, name_col[level]]

    df.loc[df['is_total'], ['unit_id', 'unit_name']] = ['TOTAL', TOTAL_LABEL]
    df.loc[df['is_unmapped'], ['unit_id', 'unit_name']] = ['UNMAPPED', UNMAPPED_LABEL]
    df['unit_id'] = df['unit_id'].fillna(df['unit_name']).astype(str)
    df['unit_name'] = df['unit_name'].astype(str)
    return df


def add_metrics(df):
    df['coverage_pct'] = safe_div(df['awc_with_1_parent'], df['total_awc']) * 100
    df['onboarding_rate'] = safe_div(df['fully_onboarded'], df['whatsappable']) * 100  # can exceed 100
    df['onboarded_per_awc'] = safe_div(df['fully_onboarded'], df['total_awc'])
    df['active30_pct'] = safe_div(df['active_30d'], df['fully_onboarded']) * 100
    df['retention_ratio'] = safe_div(df['active_30d'], df['active_60d'])
    df['aged_out_pct'] = safe_div(df['aged_out'], df['fully_onboarded']) * 100
    df['churn_pct'] = safe_div(df['inactive_50'], df['fully_onboarded']) * 100
    return df


def reconcile(df):
    """Check state Total == sum(real units) + Unmapped, per level/state/date."""
    rows = []
    totals = df[df['is_total']].set_index(['state_name', 'date'])
    for level in ('district', 'project', 'sector'):
        sub = df[(df['level'] == level) & ~df['is_total']]
        s = sub.groupby(['state_name', 'date'])[['total_awc', 'fully_onboarded']].sum()
        j = s.join(totals[['total_awc', 'fully_onboarded']], rsuffix='_total', how='inner')
        rows.append({
            'level': level,
            'state_dates_checked': len(j),
            'parents_mismatch': int((j['fully_onboarded'] != j['fully_onboarded_total']).sum()),
            'awc_count_mismatch': int((j['total_awc'] != j['total_awc_total']).sum()),
        })
    return rows


def run_etl():
    df, dropped_null_dates = load_raw()
    df = df.rename(columns=COLUMN_MAP)
    df.columns = [str(c).lower() for c in df.columns]
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['state_name'] = df['state_name'].fillna('Unknown')

    df = build_units(df)
    parts = df['district'].map(split_district)
    df['district'] = [p[0] for p in parts]
    df['district_local'] = [p[1] for p in parts]
    m = (df['level'] == 'district') & ~df['is_total'] & ~df['is_unmapped']
    df.loc[m, 'unit_name'] = df.loc[m, 'district']  # English name only
    df['product_primary'] = df['product_name'].map(
        lambda x: 'Unknown' if pd.isna(x) else str(x).split(',')[0].strip())

    # Same unit loaded twice for a date (re-runs/duplicates): keep the last row.
    before = len(df)
    df = df.drop_duplicates(subset=KEY_COLS, keep='last')
    dropped_dupes = before - len(df)

    df = add_metrics(df)
    df = df.sort_values(['level', 'state_name', 'date', 'unit_name']).reset_index(drop=True)

    os.makedirs(os.path.dirname(PARQUET_FILE), exist_ok=True)
    df.to_parquet(PARQUET_FILE, index=False)

    snaps = df.groupby('state_name')['date'].nunique()
    dq = pd.DataFrame([{
        'rows_kept': len(df),
        'dropped_blank_rows': dropped_null_dates,
        'dropped_duplicate_units': dropped_dupes,
        'total_rows': int(df['is_total'].sum()),
        'unmapped_rows': int(df['is_unmapped'].sum()),
        'rows_fully_gt_whatsappable': int((df['fully_onboarded'] > df['whatsappable']).sum()),
        'states_with_lt3_snapshots': ';'.join(snaps[snaps < 3].index),
    }])
    dq.to_csv(QUALITY_FILE, index=False)
    pd.DataFrame(reconcile(df)).to_csv(QUALITY_FILE.replace('data_quality', 'reconciliation'), index=False)
    print(dq.T.to_string())
    print(pd.DataFrame(reconcile(df)).to_string(index=False))
    return df


if __name__ == "__main__":
    run_etl()
