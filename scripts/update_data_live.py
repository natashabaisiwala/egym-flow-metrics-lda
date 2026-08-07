"""
EGYM Flow Metrics — data.json updater (safe, chronological insert)  [reusable]

Call update(conn_id, realm_id, month_str, team_values[, card_values]) from the
ExecutionAgent after computing metrics. Handles:
  - Fresh fetch of data.json right before writing
  - Deduplication (exits quietly if month already present)
  - Chronological insertion (NOT blind append) into months + every series array
  - Safety checks that abort the write instead of corrupting other realms' data

SCHEMA (two shapes supported):
  * Standard realm (Core, Apps, Wellpass): realm["teams"][tid] = {fl1:{...}, fl2:{...}}.
    Pass team_values = {tid: {"fl1": {...}, "fl2": {...}}}.
  * Split realm (Machine): realm["teams"][tid] = {fl1:{...}} (8 task teams) AND
    realm["epic_cards"][cid] = {fl2:{...}} (7 epic cards). Pass team_values for the
    fl1 teams and card_values = {cid: {"fl2": {...}}} for the epic cards.

Each container is updated ONLY for the fl-levels it actually contains, so a team with
just fl1 (or a card with just fl2) is handled correctly. Series not present in the
supplied *_values repeat the previous month's value (or None if no history yet).
"""
import json, base64
from agent_tools import call_tool

OWNER = 'oleksandrabobina'
REPO = 'egym-flow-metrics-lda'

MONTH_NUM = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
             'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}

def _sort_key(m):
    mon, yy = m.split()
    return (2000 + int(yy), MONTH_NUM[mon])

def _insertion_index(months, new_month):
    """Find the index where new_month should be inserted to keep months chronologically sorted."""
    key = _sort_key(new_month)
    for i, m in enumerate(months):
        if _sort_key(m) > key:
            return i
    return len(months)

class UpdateAborted(Exception):
    pass

def _fls(container):
    """The fl-levels ('fl1'/'fl2') actually present in a team/epic-card container."""
    return [fl for fl in ('fl1', 'fl2') if fl in container]

def _fetch(conn_id, data_path='data-machine.json'):
    r = call_tool('github_get_file_contents', {
        'connectionId': conn_id, 'owner': OWNER, 'repo': REPO, 'path': data_path})
    data = json.loads(base64.b64decode(r['content'].replace('\n', '')).decode())
    return r['sha'], data

def month_present(conn_id, realm_id, month_str, data_path='data-machine.json'):
    """Cheap idempotency pre-check: True if month_str is already recorded for realm_id."""
    _, data = _fetch(conn_id, data_path)
    realm = data['realms'].get(realm_id)
    return bool(realm and month_str in realm['months'])

def _snapshot_container_last(container):
    i = None
    out = {}
    for fl in _fls(container):
        out[fl] = {}
        for k, arr in container[fl].items():
            out[fl][k] = arr[-1] if isinstance(arr, list) and arr else None
    return out

def latest_values(conn_id, realm_id, data_path='data-machine.json'):
    """Most recent month's TEAM values as {tid: {fl: {...}}} (present fl-levels only).
    Returns None if the realm has no data yet. Backward-compatible for Core/Apps
    (teams have fl1+fl2) and correct for Machine (teams have fl1 only)."""
    _, data = _fetch(conn_id, data_path)
    realm = data['realms'].get(realm_id)
    if not realm or not realm.get('months'):
        return None
    return {tid: _snapshot_container_last(t) for tid, t in realm['teams'].items()}

def latest_cards(conn_id, realm_id, data_path='data-machine.json'):
    """Most recent month's EPIC-CARD values as {cid: {'fl2': {...}}} for split realms
    (Machine). Returns None if the realm has no epic_cards or no data yet."""
    _, data = _fetch(conn_id, data_path)
    realm = data['realms'].get(realm_id)
    if not realm or not realm.get('months') or not realm.get('epic_cards'):
        return None
    return {cid: _snapshot_container_last(c) for cid, c in realm['epic_cards'].items()}

def _insert_series(container, idx, vals):
    """Insert one month's values into each present fl-level array of a team/card at idx.
    Series missing from `vals` repeat the previous value (fallback), or None if empty."""
    for fl in _fls(container):
        for key in container[fl]:
            arr = container[fl][key]
            if vals and fl in vals and key in vals[fl]:
                new_val = vals[fl][key]
            elif len(arr) > 0:
                prev_i = min(idx, len(arr)) - 1
                new_val = arr[prev_i] if prev_i >= 0 else None
            else:
                new_val = None
            container[fl][key] = arr[:idx] + [new_val] + arr[idx:]

def _check_lengths(realm_id, kind, mapping, n_months):
    for cid, container in mapping.items():
        for fl in _fls(container):
            for key, arr in container[fl].items():
                if len(arr) != n_months:
                    raise UpdateAborted(
                        f"Safety check failed: {realm_id}.{kind}.{cid}.{fl}.{key} has length "
                        f"{len(arr)} but months has length {n_months}. Aborting write.")

def update(conn_id, realm_id, month_str, team_values, card_values=None, commit_prefix="Data",
           data_path='data-machine.json'):
    """
    Returns {"status": "updated"|"duplicate", "index": int, "months": [...]}.
    Raises UpdateAborted if a safety check fails — caller MUST surface it and must NOT
    retry blindly. card_values is only used for split realms that have realm["epic_cards"].
    """
    # 1. Fresh fetch right before writing
    sha, data = _fetch(conn_id, data_path)

    if realm_id not in data['realms']:
        raise UpdateAborted(f"Unknown realm_id '{realm_id}' — not present in data.json realms.")

    realm = data['realms'][realm_id]
    months = realm['months']

    # 2. Deduplication check
    if month_str in months:
        return {"status": "duplicate", "index": months.index(month_str), "months": months}

    # 3. Compute chronological insertion index
    idx = _insertion_index(months, month_str)

    # snapshot of OTHER realms before mutation, to validate nothing else got touched/corrupted
    other_realms_before = {
        rid: {"months_len": len(r_['months']), "team_count": len(r_['teams'])}
        for rid, r_ in data['realms'].items() if rid != realm_id
    }

    # 4. Insert new month + values for every team (and epic-card) at idx
    new_months = months[:idx] + [month_str] + months[idx:]
    realm['months'] = new_months

    for tid, team in realm['teams'].items():
        _insert_series(team, idx, team_values.get(tid))

    has_cards = bool(realm.get('epic_cards'))
    if has_cards:
        for cid, card in realm['epic_cards'].items():
            _insert_series(card, idx, (card_values or {}).get(cid))

    # 5. Safety checks before pushing
    _check_lengths(realm_id, "teams", realm['teams'], len(new_months))
    if has_cards:
        _check_lengths(realm_id, "epic_cards", realm['epic_cards'], len(new_months))

    for rid, before in other_realms_before.items():
        after_realm = data['realms'][rid]
        if before['team_count'] > 0 and len(after_realm['teams']) == 0:
            raise UpdateAborted(
                f"Safety check failed: realm '{rid}' had {before['team_count']} teams before "
                f"this update but now has 0. Aborting write to prevent data loss.")
        if len(after_realm['months']) < before['months_len']:
            raise UpdateAborted(
                f"Safety check failed: realm '{rid}' months array shrank from "
                f"{before['months_len']} to {len(after_realm['months'])}. Aborting write.")

    # 6. Push
    content = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    call_tool('github_create_or_update_file', {
        'connectionId': conn_id, 'owner': OWNER, 'repo': REPO,
        'path': data_path,
        'message': f'{commit_prefix} {realm_id}: {month_str}',
        'content': content,
        'sha': sha,
    })

    return {"status": "updated", "index": idx, "months": new_months}
