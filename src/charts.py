import plotly.graph_objects as go
from src.config import COLORS

LAYOUT = dict(margin=dict(l=0, r=10, t=36, b=0), font=dict(size=12))


def plot_rank_bar(df, metric, title, color, decimals=1, unit=''):
    """Horizontal bars for an already-selected (and ordered) handful of units."""
    if df.empty:
        return go.Figure().update_layout(title=title, **LAYOUT)
    d = df.iloc[::-1]  # first row on top
    fig = go.Figure(go.Bar(x=d[metric], y=d['unit_name'], orientation='h', marker_color=color,
                           text=d[metric].map(lambda v: f'{v:,.{decimals}f}{unit}'),
                           textposition='outside', cliponaxis=False))
    fig.update_layout(title=title, height=max(220, 44 * len(d) + 80), xaxis_title=None, **LAYOUT)
    fig.update_xaxes(range=[0, max(d[metric].max() * 1.25, 1)])
    return fig


def plot_stage_mix(totals):
    labels = ['Not onboarded', 'Partially onboarded', 'Fully onboarded']
    vals = [totals.get('not_onboarded', 0), totals.get('partially_onboarded', 0), totals.get('fully_onboarded', 0)]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation='h',
                           marker_color=[COLORS['not_onboarded'], COLORS['partial'], COLORS['primary']],
                           text=[f'{v:,.0f}' for v in vals], textposition='outside', cliponaxis=False))
    fig.update_layout(title='Parent stage mix', xaxis_title='Parents', height=260, **LAYOUT)
    fig.update_yaxes(autorange='reversed')
    return fig


def plot_decay(row):
    labels = ['7d', '15d', '30d', '60d']
    vals = [row.get(f'active_{d}', 0) for d in ('7d', '15d', '30d', '60d')]
    fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=['#B5D4F4', '#85B7EB', COLORS['primary'], '#185FA5'],
                           text=[f'{v:,.0f}' for v in vals], textposition='outside'))
    fig.update_layout(title='Active parents by window', yaxis_title='Parents', height=300, **LAYOUT)
    return fig


def plot_trend(hist, metric, title):
    fig = go.Figure()
    for name, g in hist.groupby('unit_name'):
        g = g.sort_values('date')
        fig.add_trace(go.Scatter(x=g['date'], y=g[metric], mode='lines+markers', name=name))
    fig.update_layout(title=title, height=320, xaxis=dict(tickformat='%d %b', tickmode='array',
                      tickvals=sorted(hist['date'].unique())), legend=dict(orientation='h', y=-0.2), **LAYOUT)
    return fig


def plot_bubble(df):
    if df.empty:
        return go.Figure().update_layout(title='Scale vs quality', **LAYOUT)
    fig = go.Figure(go.Scatter(
        x=df['fully_onboarded'], y=df['power_pct'], mode='markers', text=df['unit_name'],
        marker=dict(size=df['total_awc'].clip(lower=1), sizemode='area',
                    sizeref=2. * df['total_awc'].max() / (36 ** 2), sizemin=4, color=COLORS['primary'], opacity=.55),
        hovertemplate='%{text}<br>Onboarded %{x:,.0f}<br>Power %{y:.1f}%<extra></extra>'))
    fig.update_layout(title='Scale vs quality (bubble = AWCs)', xaxis_title='Fully onboarded parents',
                      yaxis_title='Power user %', height=360, **LAYOUT)
    return fig
