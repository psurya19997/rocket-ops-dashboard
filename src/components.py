import pandas as pd
import streamlit as st

DELTA_COLOR = {'higher': 'normal', 'lower': 'inverse', 'neutral': 'off'}


def fmt_value(v, unit='', decimals=0):
    return '–' if v is None or pd.isna(v) else f"{v:,.{decimals}f}{unit}"


def render_kpis(t, kpis):
    """t: headline row with <col>_delta columns. kpis: [(col, label, unit, direction, decimals)]."""
    cols = st.columns(len(kpis))
    for slot, (col, label, unit, direction, dec) in zip(cols, kpis):
        d = t.get(f'{col}_delta')
        delta = None if d is None or pd.isna(d) else f"{d:+,.{dec}f}{' pt' if unit == '%' else ''}"
        slot.metric(label, fmt_value(t.get(col), unit, dec), delta, delta_color=DELTA_COLOR[direction])


def render_unmapped(row, state_total):
    """Unmapped = parents with no known district/project/sector. Reported, never ranked."""
    if row is None:
        return
    share = row['fully_onboarded'] / state_total['fully_onboarded'] * 100 if state_total is not None and state_total.get('fully_onboarded') else 0
    st.info(
        f"**Unmapped parents (location unknown, not ranked):** {row['fully_onboarded']:,.0f} fully onboarded "
        f"({share:.1f}% of state), {row['active_30d']:,.0f} active in 30d, power users {row['power_pct']:.1f}%."
    )


def render_needs_attention(df):
    if df.empty:
        st.success("No units flagged.")
        return
    st.dataframe(
        df.sort_values('zero_parent_pct', ascending=False)[
            ['unit_name', 'zero_parent_pct', 'active_30d_chg_pct', 'churn_pct', 'reason']]
        .rename(columns={'unit_name': 'Unit', 'zero_parent_pct': '0-parent AWCs %',
                         'active_30d_chg_pct': 'Active 30d Δ%', 'churn_pct': 'Churn %', 'reason': 'Why'}),
        width='stretch', hide_index=True,
        column_config={'0-parent AWCs %': st.column_config.NumberColumn(format='%.0f'),
                       'Active 30d Δ%': st.column_config.NumberColumn(format='%+.1f'),
                       'Churn %': st.column_config.NumberColumn(format='%.0f')})
