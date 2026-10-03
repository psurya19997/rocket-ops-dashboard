# BTP Leaderboard Dashboard

```
pip install -r requirements.txt
python -m streamlit run app.py
```

Data comes from a public Google Drive folder (ID in `src/config.py`). On start the app syncs it into
`data/drive_raw/`, rebuilds `data/btp.parquet` if anything changed, and shows "Data as of" in the sidebar.

- **Auto-refresh (every 10 min):** needs a free Google API key. Copy `.streamlit/secrets.toml.example`
  to `.streamlit/secrets.toml` and paste the key. Only changed files are downloaded.
- **No key:** use the "Refresh data now" button (re-downloads everything, about 1 minute).
- **Offline / Drive error:** the last downloaded copy keeps being used.
- Manual rebuild from local files: `python -m src.etl` (uses `data/drive_raw` if present, else `Leaderboard/`).

Rules (see the "Data notes" tab): Unmapped parents are never ranked; the state Total row feeds the KPI cards;
duplicate loads of a unit/date are dropped; units under the Min AWCs filter are not ranked.
