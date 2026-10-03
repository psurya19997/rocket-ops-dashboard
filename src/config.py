import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_RAW_DIR = os.path.join(BASE_DIR, 'Leaderboard')       # your original downloads (never modified)
DRIVE_RAW_DIR = os.path.join(BASE_DIR, 'data', 'drive_raw')  # synced copy of the Drive folder
RAW_DATA_DIR = DRIVE_RAW_DIR if os.path.isdir(DRIVE_RAW_DIR) and any(f.endswith('.xlsx') for _, _, fs in os.walk(DRIVE_RAW_DIR) for f in fs) else LOCAL_RAW_DIR

# Google Drive source (public folder, 'Anyone with the link: Viewer')
DRIVE_FOLDER_ID = '1K6gVDeDvP3DKpqGKJHcwO8pIUodNYO7v'
SYNC_TTL_SECONDS = 600
SYNC_MANIFEST = os.path.join(BASE_DIR, 'data', 'sync_manifest.json')
DATA_DIR = os.path.join(BASE_DIR, 'data')
PARQUET_FILE = os.path.join(DATA_DIR, 'btp.parquet')
QUALITY_FILE = os.path.join(DATA_DIR, 'data_quality.csv')
RECON_FILE = os.path.join(DATA_DIR, 'reconciliation.csv')

# Column mapping for ETL
COLUMN_MAP = {
    'Total_register_photo_parents': 'registered',
    'Register_whatsappable_parents (A=B+C+D)': 'whatsappable',
    'Overall_fully_onboarded_parents': 'fully_onboarded',
    'Overall_partially_onboarded_parents': 'partially_onboarded',
    'Register_whatsappable_but_not_onboarded (B)': 'not_onboarded',
    'Total_parents_active_for_past_7_days': 'active_7d',
    'Total_parents_active_for_past_15_days': 'active_15d',
    'Total_parents_active_for_past_30_days': 'active_30d',
    'Total_parents_active_for_past_60_days': 'active_60d',
    'Power_user_parents': 'power_users',
    '%power_user_parents': 'power_pct',
    '#parents_inactive_for_ more_than_50%_of_week_since_onboarding': 'inactive_50',
    '%awc_with_0_parents': 'zero_parent_pct',
    '%awc_with_sector_meeting': 'sector_meeting_pct',
    '%udise_with_10+_parents': 'udise_10plus_pct',
    'Overall_onboarded_36_months_older_parents': 'aged_out',
    'awc_with_min_1_parent': 'awc_with_1_parent'
}

# Needs-attention thresholds
THRESHOLDS = {
    'zero_parent_pct_high': 50.0,
    'active_30d_drop': -10.0, # -10% week over week change
    'churn_pct_high': 35.0
}

DEFAULT_MIN_AWCS = 5
TOP_N = 5

# Metric tabs. direction: 'higher' = higher is better, 'lower' = lower is better, 'neutral' = signal only.
# metric tuple: (column, label, unit, direction, decimals)
METRIC_TABS = {
    'Reach': {
        'kpis': [('total_awc', 'Total AWCs', '', 'neutral', 0),
                 ('coverage_pct', 'AWC coverage', '%', 'higher', 1),
                 ('zero_parent_pct', 'AWCs with 0 parents', '%', 'lower', 1),
                 ('udise_10plus_pct', 'AWCs with 10+ parents', '%', 'higher', 1)],
        'rank': [('coverage_pct', 'Coverage % (AWCs with ≥1 parent)', '%', 'higher', 1),
                 ('zero_parent_pct', 'AWCs with 0 parents %', '%', 'lower', 1),
                 ('udise_10plus_pct', 'AWCs with 10+ parents %', '%', 'higher', 1)],
    },
    'Onboarding': {
        'kpis': [('fully_onboarded', 'Fully onboarded', '', 'higher', 0),
                 ('partially_onboarded', 'Partially onboarded', '', 'lower', 0),
                 ('onboarded_per_awc', 'Onboarded per AWC', '', 'higher', 1),
                 ('aged_out', 'Aged past 36 months', '', 'neutral', 0)],
        'rank': [('onboarded_per_awc', 'Fully onboarded per AWC', '', 'higher', 1),
                 ('partially_onboarded', 'Partially onboarded (backlog to nudge)', '', 'lower', 0),
                 ('aged_out_pct', 'Aged past 36 months, % of onboarded', '%', 'neutral', 1)],
    },
    'Engagement': {
        'kpis': [('active_30d', 'Active 30d', '', 'higher', 0),
                 ('active30_pct', 'Active 30d % of onboarded', '%', 'higher', 1),
                 ('power_pct', 'Power users', '%', 'higher', 1),
                 ('inactive_50', 'Inactive >50% of weeks', '', 'lower', 0)],
        'rank': [('active30_pct', 'Active 30d % of onboarded', '%', 'higher', 1),
                 ('power_pct', 'Power user %', '%', 'higher', 1)],
    },
    'Field ops': {
        'kpis': [('sector_meeting_pct', 'AWCs with sector meeting', '%', 'higher', 1)],
        'rank': [('sector_meeting_pct', 'AWCs with sector meeting %', '%', 'higher', 1)],
    },
}

# UI Config
COLORS = {
    'primary': '#378ADD',
    'coverage': '#1D9E75',
    'partial': '#EF9F27',
    'not_onboarded': '#B4B2A9',
    'alert': '#A32D2D'
}
