import pandas as pd
import streamlit as st

from src.charts import plot_decay, plot_rank_bar, plot_stage_mix, plot_trend
from src.components import render_kpis, render_needs_attention, render_unmapped
from src.config import COLORS, DEFAULT_MIN_AWCS, METRIC_TABS, THRESHOLDS, TOP_N
from src.loaders import data_version, get_snapshot_dates, load_data, load_reports, partial_states
from src.sync import api_key, last_synced, sync_and_build
from src.config import SYNC_TTL_SECONDS
from src.metrics import DELTA_COLS, add_deltas, attention_flags, best_first, eligible

st.set_page_config(page_title="BTP Leaderboard", layout="wide")



@st.cache_data(ttl=SYNC_TTL_SECONDS, show_spinner="Checking Google Drive for new data...")
def auto_sync():
    return sync_and_build()


# With an API key the check is cheap (only changed files download), so do it every few minutes.
# Without one a sync re-downloads every file (~1 min), so only do it when there is no data yet or on request.
sync_info = auto_sync() if api_key() or data_version() == 0 else None

df = load_data(data_version())
if df.empty:
    st.error("No data found. Run `python -m src.etl` first.")
    st.stop()

# ---------------------------------------------------------------- sidebar
st.sidebar.title("Filters")
if st.sidebar.button("Refresh data now", help="Pull the latest files from the Google Drive folder."):
    with st.spinner("Syncing from Google Drive..."):
        sync_info = sync_and_build()
    st.cache_data.clear()
    st.rerun()
stubs = partial_states(df)
show_partial = st.sidebar.checkbox("Show partial states", value=False,
                                   help="States with fewer than 3 snapshots: " + ", ".join(stubs))
states = sorted(s for s in df['state_name'].unique() if show_partial or s not in stubs)
state = st.sidebar.selectbox("State", states)

state_df = df[df['state_name'] == state]
dates = get_snapshot_dates(state_df)
sel_date = st.sidebar.selectbox("Snapshot date", dates, format_func=lambda d: pd.Timestamp(d).strftime('%d %b %Y'))
prev_date = next((d for d in dates if d < sel_date), None)

dist_rows = state_df[(state_df['level'] == 'district') & ~state_df['is_total'] & ~state_df['is_unmapped']]
district = st.sidebar.selectbox("District", ['All'] + sorted(dist_rows['district'].dropna().unique()))
level = st.sidebar.radio("Level", ['District', 'Project', 'Sector']).lower()
min_awcs = st.sidebar.slider("Min AWCs per unit", 1, 100, DEFAULT_MIN_AWCS,
                             help="Hides tiny units whose rates are noisy. Lower it to see small units.")


_ls = last_synced()
st.sidebar.caption("Data as of " + pd.Timestamp(df['date'].max()).strftime('%d %b %Y')
                   + (" · synced " + pd.Timestamp(_ls, unit='s', tz='UTC').tz_convert('Asia/Kolkata').strftime('%d %b %H:%M') if _ls else " · local files"))
if sync_info and sync_info.get('error'):
    st.sidebar.warning("Drive sync failed, showing last downloaded data. " + sync_info['error'])
if not api_key():
    st.sidebar.caption("No API key set: auto-refresh is off, use the button above.")


# ---------------------------------------------------------------- data for the selection
def snapshot(date):
    """Real units of the chosen level on one date (Total / Unmapped excluded, size filter applied)."""
    if date is None:
        return pd.DataFrame()
    rows = state_df[(state_df['date'] == date) & (state_df['level'] == level)]
    return eligible(rows, min_awcs)


def district_filter(units):
    if district == 'All' or units.empty:
        return units
    return units[units['district'] == district]


def kpi_row(date):
    """Headline numbers: state Total row, or the chosen district's own row."""
    if date is None:
        return None
    rows = state_df[(state_df['date'] == date) & (state_df['level'] == 'district')]
    r = rows[rows['is_total']] if district == 'All' else rows[~rows['is_total'] & ~rows['is_unmapped'] & (rows['district'] == district)]
    return r.iloc[0] if len(r) else None


cur = district_filter(add_deltas(snapshot(sel_date), snapshot(prev_date)))

totals, prev_totals = kpi_row(sel_date), kpi_row(prev_date)
if totals is None:
    st.warning("No headline row for this selection.")
    st.stop()
totals = totals.copy()
for c in DELTA_COLS:
    totals[f'{c}_delta'] = totals[c] - prev_totals[c] if prev_totals is not None else float('nan')

unmapped_rows = state_df[(state_df['date'] == sel_date) & (state_df['level'] == 'district') & state_df['is_unmapped']]
unmapped = unmapped_rows.iloc[0] if (district == 'All' and len(unmapped_rows)) else None
state_total = kpi_row(sel_date) if district == 'All' else None

st.title(f"BTP Leaderboard — {state}" + ("" if district == 'All' else f" / {district}"))
st.caption(f"Snapshot {pd.Timestamp(sel_date).strftime('%d %b %Y')}"
           + (f" · compared with {pd.Timestamp(prev_date).strftime('%d %b %Y')}" if prev_date is not None else " · first snapshot, no comparison")
           + f" · ranking {len(cur)} {level}s with ≥ {min_awcs} AWCs")

tab_names = ["Overview", *METRIC_TABS, "Trends", "Data notes"]
tabs = dict(zip(tab_names, st.tabs(tab_names)))

# ---------------------------------------------------------------- overview
with tabs['Overview']:
    render_kpis(totals, [('total_awc', 'Total AWCs', '', 'neutral', 0),
                         ('coverage_pct', 'AWC coverage', '%', 'higher', 1),
                         ('fully_onboarded', 'Fully onboarded', '', 'higher', 0),
                         ('active_30d', 'Active 30d', '', 'higher', 0),
                         ('power_pct', 'Power users', '%', 'higher', 1)])
    if unmapped is not None:
        render_unmapped(unmapped, state_total)
    c1, c2 = st.columns([1, 1.4])
    c1.plotly_chart(plot_stage_mix(totals), width='stretch')
    with c2:
        st.markdown("**Needs attention**")
        render_needs_attention(attention_flags(cur))
    st.caption("KPI cards use the state Total row, which includes unmapped parents.")


# ---------------------------------------------------------------- metric tabs
def metric_tab(name):
    spec = METRIC_TABS[name]
    render_kpis(totals, spec['kpis'])
    if cur.empty:
        st.info("No units match the filters. Lower 'Min AWCs' or change level.")
        return

    labels = {m[1]: m for m in spec['rank']}
    pick = st.radio("Rank by", list(labels), horizontal=True, key=f"rank_{name}")
    col, label, unit, direction, dec = labels[pick]

    ordered = best_first(cur, col, direction)
    missing = len(cur) - len(ordered)
    if ordered.empty:
        st.info("No data for this metric in the selection.")
        return
    if missing:
        st.caption(f"{missing} of {len(cur)} units have no value for this metric and are not ranked.")

    left, right = ordered.head(TOP_N), ordered.tail(TOP_N).iloc[::-1]
    if direction == 'higher':
        a = (f"Best {len(left)}", COLORS['coverage'])
        b = (f"Bottom {len(right)} — needs attention", COLORS['alert'])
    elif direction == 'lower':
        a = (f"Lowest {len(left)} — best", COLORS['coverage'])
        b = (f"Highest {len(right)} — needs attention", COLORS['alert'])
    else:
        a = (f"Highest {len(left)}", COLORS['primary'])
        b = (f"Lowest {len(right)}", COLORS['not_onboarded'])
    c1, c2 = st.columns(2)
    c1.plotly_chart(plot_rank_bar(left, col, a[0], a[1], dec, unit), width='stretch')
    c2.plotly_chart(plot_rank_bar(right, col, b[0], b[1], dec, unit), width='stretch')
    if direction == 'neutral':
        st.caption("Signal, not good or bad: children aging past 36 months leave the program. "
                   "High values mean those units need new enrolments to replace them.")

    st.markdown(f"**{label}: all units**")
    table = ordered.assign(rank=range(1, len(ordered) + 1))
    search = st.text_input("Search unit", key=f"search_{name}")
    if search:
        table = table[table['unit_name'].str.contains(search, case=False, na=False)]
    show = table[['rank', 'unit_name', 'district', col, f'{col}_delta', 'total_awc', 'fully_onboarded']]
    st.dataframe(
        show, width='stretch', hide_index=True,
        column_config={
            'rank': st.column_config.NumberColumn('Rank', format='%d'),
            'unit_name': 'Unit', 'district': 'District',
            col: st.column_config.NumberColumn(label.split(' (')[0], format=f'%.{dec}f'),
            f'{col}_delta': st.column_config.NumberColumn('Δ vs last', format=f'%+.{dec}f'),
            'total_awc': st.column_config.NumberColumn('AWCs', format='%d'),
            'fully_onboarded': st.column_config.NumberColumn('Onboarded', format='%d'),
        })
    st.download_button("Download CSV", show.to_csv(index=False),
                       f"btp_{state}_{level}_{col}_{pd.Timestamp(sel_date):%Y%m%d}.csv", key=f"dl_{name}")


for name in METRIC_TABS:
    with tabs[name]:
        metric_tab(name)

# ---------------------------------------------------------------- trends
with tabs['Trends']:
    options = cur.sort_values('fully_onboarded', ascending=False)['unit_name'].tolist() if not cur.empty else []
    picks = st.multiselect(f"Compare {level}s (max 5)", options, default=options[:3], max_selections=5)
    id_map = dict(zip(cur['unit_name'], cur['unit_id'])) if not cur.empty else {}
    hist = state_df[(state_df['level'] == level) & state_df['unit_id'].isin([id_map[p] for p in picks])]
    if st.checkbox("Add state total", value=True):
        hist = pd.concat([hist, state_df[(state_df['level'] == 'district') & state_df['is_total']]])
    if hist.empty:
        st.info("Pick at least one unit.")
    else:
        all_metrics = {m[1]: m[0] for tab in METRIC_TABS.values() for m in tab['rank']}
        chosen = st.multiselect("Metrics", list(all_metrics), default=list(all_metrics)[:2])
        cols = st.columns(2)
        for i, lab in enumerate(chosen):
            cols[i % 2].plotly_chart(plot_trend(hist, all_metrics[lab], lab), width='stretch')
        cols2 = st.columns(2)
        cols2[0].plotly_chart(plot_trend(hist, 'fully_onboarded', 'Fully onboarded parents'), width='stretch')
        cols2[1].plotly_chart(plot_decay(totals), width='stretch')
    st.caption("Decay chart shows the state total (or the chosen district) on the selected date.")

# ---------------------------------------------------------------- notes
with tabs['Data notes']:
    rep = load_reports(data_version())
    st.markdown(f"""
### Metric definitions
| Metric | Meaning |
|---|---|
| Coverage % | AWCs with ≥1 parent onboarded / total AWCs |
| AWCs with 0 parents % | share of AWCs with no parent onboarded (lower is better) |
| AWCs with 10+ parents % | share of AWCs with ≥10 parents onboarded |
| Onboarded per AWC | fully onboarded parents / total AWCs |
| Partially onboarded | parents who started but did not finish onboarding (backlog to nudge) |
| Aged past 36 months | onboarded children now older than 3 (program is Birth to 3), as count and % of onboarded; a pipeline signal, not good or bad |
| Active 30d % | parents active in 30d / fully onboarded |
| Power % | power users / fully onboarded (as supplied) |
| Churn % | parents inactive >50% of weeks / fully onboarded |
| AWCs with sector meeting % | share of AWCs where a sector meeting was held (blank in some rows, not ranked there) |

### Rules
* **Unmapped** rows are parents whose district/project/sector is unknown. Not a place, so never ranked; shown separately and included in the state Total.
* **State Total** (district file) = sum of districts + Unmapped. Used for KPI cards.
* Units under the *Min AWCs* filter are not ranked (default {DEFAULT_MIN_AWCS}). Percentages from tiny units are noisy.
* Needs attention: ≥{THRESHOLDS['zero_parent_pct_high']:.0f}% AWCs with no parent, active 30d down ≥{abs(THRESHOLDS['active_30d_drop']):.0f}% vs the previous snapshot, or churn ≥{THRESHOLDS['churn_pct_high']:.0f}%.
* AWC counts differ between the district file and the project/sector files; parent counts reconcile. Coverage % is only comparable within a level.
* Partial states (few snapshots) are hidden unless enabled. Launch-level file is not used in v1.
""")
    if not rep['quality'].empty:
        st.markdown("### ETL data quality")
        st.dataframe(rep['quality'].astype(str).T.rename(columns={0: 'value'}), width='stretch')
    if not rep['recon'].empty:
        st.markdown("### Reconciliation with state totals")
        st.dataframe(rep['recon'], hide_index=True, width='stretch')
