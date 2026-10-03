import numpy as np
import pandas as pd
from src.config import THRESHOLDS, METRIC_TABS

# every column we show a week-over-week change for
DELTA_COLS = sorted({m[0] for tab in METRIC_TABS.values() for m in tab['kpis'] + tab['rank']} | {'active_30d', 'power_pct'})


def eligible(df, min_awcs):
    """Real physical units only: no Total / Unmapped rows, and at least `min_awcs` AWCs."""
    return df[~df['is_total'] & ~df['is_unmapped'] & (df['total_awc'] >= min_awcs)]


def add_deltas(cur, prev):
    """Add <col>_delta (vs previous snapshot, matched on unit_id) and active_30d_chg_pct."""
    cur = cur.copy()
    if cur.empty:
        return cur
    p = prev.set_index('unit_id') if prev is not None and not prev.empty else None
    for c in DELTA_COLS:
        cur[f'{c}_delta'] = (cur[c] - cur['unit_id'].map(p[c])) if p is not None else np.nan
    prev_active = cur['unit_id'].map(p['active_30d']) if p is not None else np.nan
    cur['active_30d_chg_pct'] = (cur['active_30d'] - prev_active) / prev_active.where(prev_active > 0) * 100
    return cur


def best_first(df, metric, direction):
    """Rows with a value, ordered best -> worst ('neutral' = highest first)."""
    d = df.dropna(subset=[metric])
    return d.sort_values(metric, ascending=(direction == 'lower'), kind='stable')


def attention_flags(df):
    """Rows breaching a needs-attention rule, with the rule(s) that fired."""
    if df.empty:
        return df.assign(reason=pd.Series(dtype=str))
    t = THRESHOLDS
    rules = {
        f"{t['zero_parent_pct_high']:.0f}%+ AWCs have no parent": df['zero_parent_pct'] >= t['zero_parent_pct_high'],
        f"Active 30d down {abs(t['active_30d_drop']):.0f}%+ vs last snapshot": df['active_30d_chg_pct'] <= t['active_30d_drop'],
        f"Churn {t['churn_pct_high']:.0f}%+": df['churn_pct'] >= t['churn_pct_high'],
    }
    reason = pd.Series('', index=df.index)
    for label, mask in rules.items():
        mask = mask.fillna(False)
        reason = reason.where(~mask, reason + np.where(reason == '', '', '; ') + label)
    out = df.assign(reason=reason)
    return out[out['reason'] != '']
