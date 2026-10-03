import os
import pandas as pd
import streamlit as st
from src.config import PARQUET_FILE, QUALITY_FILE, RECON_FILE


def data_version():
    """Changes whenever the ETL rewrites the parquet, so cached data refreshes."""
    return os.path.getmtime(PARQUET_FILE) if os.path.exists(PARQUET_FILE) else 0


@st.cache_data
def load_data(version=0):
    try:
        return pd.read_parquet(PARQUET_FILE).sort_values('date')
    except Exception as e:  # missing file -> app shows "run ETL"
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


@st.cache_data
def load_reports(version=0):
    out = {}
    for name, path in (('quality', QUALITY_FILE), ('recon', RECON_FILE)):
        try:
            out[name] = pd.read_csv(path)
        except Exception:
            out[name] = pd.DataFrame()
    return out


def get_snapshot_dates(df):
    """Newest first."""
    return sorted(df['date'].dropna().unique(), reverse=True) if not df.empty else []


def partial_states(df, min_snapshots=3):
    n = df.groupby('state_name')['date'].nunique()
    return n[n < min_snapshots].index.tolist()
