"""Sync the public Google Drive folder into data/drive_raw, then rebuild the parquet if anything changed.

Listing: Drive API with an API key (env GOOGLE_API_KEY or .streamlit/secrets.toml) when available
(only changed files are downloaded, using md5Checksum); otherwise `gdown` (no change detection, so
every file is re-downloaded when a sync runs).
Offline / error: the last downloaded copy keeps being used.
"""
import json
import os
import time
import tomllib

import requests

from src.config import BASE_DIR, DRIVE_FOLDER_ID, DRIVE_RAW_DIR, SYNC_MANIFEST

API = 'https://www.googleapis.com/drive/v3/files'
FOLDER_MIME = 'application/vnd.google-apps.folder'
SHEET_MIME = 'application/vnd.google-apps.spreadsheet'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def api_key():
    key = os.environ.get('GOOGLE_API_KEY')
    if key:
        return key
    path = os.path.join(BASE_DIR, '.streamlit', 'secrets.toml')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return tomllib.load(f).get('GOOGLE_API_KEY')
    return None


def _list_api(folder_id, key, prefix=''):
    """Recursively list a public folder with the Drive API."""
    out, token = [], None
    while True:
        r = requests.get(API, params={
            'q': f"'{folder_id}' in parents and trashed=false", 'key': key, 'pageSize': 1000, 'pageToken': token,
            'fields': 'nextPageToken,files(id,name,mimeType,md5Checksum,modifiedTime)'}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for f in data['files']:
            if f['mimeType'] == FOLDER_MIME:
                out += _list_api(f['id'], key, os.path.join(prefix, f['name']))
            elif f['name'].lower().endswith('.xlsx') or f['mimeType'] == SHEET_MIME:
                name = f['name'] if f['name'].lower().endswith('.xlsx') else f['name'] + '.xlsx'
                out.append({**f, 'path': os.path.join(prefix, name), 'version': f.get('md5Checksum') or f['modifiedTime']})
        token = data.get('nextPageToken')
        if not token:
            return out


def _download_api(f, dest, key):
    if f['mimeType'] == SHEET_MIME:
        r = requests.get(f"{API}/{f['id']}/export", params={'mimeType': XLSX_MIME, 'key': key}, timeout=120)
    else:
        r = requests.get(f"{API}/{f['id']}", params={'alt': 'media', 'key': key}, timeout=120)
    r.raise_for_status()
    with open(dest, 'wb') as fh:
        fh.write(r.content)


def _sync_gdown():
    """No API key: let gdown fetch the whole public folder (re-downloads everything)."""
    import gdown
    files = gdown.download_folder(id=DRIVE_FOLDER_ID, output=DRIVE_RAW_DIR, quiet=True, use_cookies=False)
    return {os.path.relpath(f, DRIVE_RAW_DIR): 'gdown' for f in files or []}


def sync_drive():
    """Returns dict(changed, mode, files, error). Never raises."""
    os.makedirs(DRIVE_RAW_DIR, exist_ok=True)
    manifest = {}
    if os.path.exists(SYNC_MANIFEST):
        with open(SYNC_MANIFEST, encoding='utf-8') as fh:
            manifest = json.load(fh)
    result = {'changed': False, 'mode': None, 'files': len(manifest), 'error': None}
    try:
        key = api_key()
        if key:
            result['mode'] = 'api'
            remote = _list_api(DRIVE_FOLDER_ID, key)
            new = {}
            for f in remote:
                dest = os.path.join(DRIVE_RAW_DIR, f['path'])
                new[f['path']] = f['version']
                if manifest.get(f['path']) != f['version'] or not os.path.exists(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    _download_api(f, dest, key)
                    result['changed'] = True
        else:
            result['mode'] = 'gdown'
            new = _sync_gdown()
            result['changed'] = True
        result['files'] = len(new)
        os.makedirs(os.path.dirname(SYNC_MANIFEST), exist_ok=True)
        with open(SYNC_MANIFEST, 'w', encoding='utf-8') as fh:
            json.dump({**new, '_synced_at': time.time()}, fh)
    except Exception as e:  # offline, quota, bad key ... keep using the local copy
        result['error'] = f'{type(e).__name__}: {str(e)[:200]}'
    return result


def last_synced():
    try:
        with open(SYNC_MANIFEST, encoding='utf-8') as fh:
            return json.load(fh).get('_synced_at')
    except Exception:
        return None


def sync_and_build(force_etl=False):
    """Sync from Drive, rebuild the parquet if files changed (or it is missing)."""
    import importlib
    from src import config
    res = sync_drive()
    if res['changed'] or force_etl or not os.path.exists(config.PARQUET_FILE):
        importlib.reload(config)  # RAW_DATA_DIR may now point at the synced copy
        import src.etl as etl
        importlib.reload(etl)
        etl.run_etl()
        res['rebuilt'] = True
    return res
