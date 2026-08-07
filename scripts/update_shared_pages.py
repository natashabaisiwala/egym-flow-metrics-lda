"""
Space agent — Shared Pages Updater (PTC script)
Rebuilds ONLY index.html, global-dashboard.html, and upload.html in
oleksandrabobina/egym-flow-metrics-lda by merging every data-<realm>.json file
found at repo root and calling the pure HTML-builder functions from
generate_dashboards_live.py (imported as a module — never its run(), which
also writes per-realm team pages that belong to the realm agents).
Prints exactly ONE JSON object to stdout describing the outcome:
  {"status": "ok", "realms_included": [...], "pages_updated": [...]}
  {"status": "config_error", "message": "...", "conflicting_files": [...]}
  {"status": "error", "message": "..."}
"""
import sys, json, base64, importlib.util
from agent_tools import call_tool

OWNER = 'oleksandrabobina'
REPO  = 'egym-flow-metrics-lda'
ENGINE_PATH = '/agent/home/generate_dashboards_live.py'


def _result(status, **kw):
    out = {"status": status}
    out.update(kw)
    print(json.dumps(out))
    return out


def main():
    if len(sys.argv) < 2:
        _result("error", message="Missing GitHub connection ID argument.")
        sys.exit(1)
    gh_conn = sys.argv[1]

    # Import the shared rendering engine module (bootstrapped separately to
    # ENGINE_PATH before this script is run — see agent instructions step 1).
    try:
        spec = importlib.util.spec_from_file_location("generate_dashboards_live", ENGINE_PATH)
        gdl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gdl)
    except Exception as e:
        _result("error", message=f"Failed to import {ENGINE_PATH}: {e}")
        sys.exit(1)

    try:
        root = call_tool('github_get_file_contents', {
            'connectionId': gh_conn, 'owner': OWNER, 'repo': REPO, 'path': '/'})
        data_files = sorted(
            e['path'] for e in (root if isinstance(root, list) else [])
            if e.get('type') == 'file' and e['name'].startswith('data-') and e['name'].endswith('.json'))
    except Exception as e:
        _result("error", message=f"Failed to list repo root: {e}")
        sys.exit(1)

    if not data_files:
        _result("error", message="No data-*.json files found at repo root — nothing to merge.")
        sys.exit(1)

    merged = {"realms": {}}
    claimed_by = {}
    try:
        for path in data_files:
            r = call_tool('github_get_file_contents', {
                'connectionId': gh_conn, 'owner': OWNER, 'repo': REPO, 'path': path})
            d = json.loads(base64.b64decode(r['content'].replace('\n', '')).decode())
            for rid, realm in d.get('realms', {}).items():
                if rid in claimed_by:
                    _result("config_error",
                            message=f"Realm id '{rid}' is claimed by both {claimed_by[rid]} and {path}.",
                            conflicting_files=[claimed_by[rid], path])
                    sys.exit(1)
                claimed_by[rid] = path
                merged['realms'][rid] = realm
    except Exception as e:
        _result("error", message=f"Failed to load/merge realm data files: {e}")
        sys.exit(1)

    # Trim to the display window exactly like the realm pages do, for visual consistency.
    try:
        for r in merged['realms'].values():
            gdl._trim_realm(r)
    except Exception as e:
        _result("error", message=f"Failed while trimming realm data for display: {e}")
        sys.exit(1)

    try:
        pages = {
            'index.html': gdl.main_index_html(merged),
            'global-dashboard.html': gdl.global_dashboard_html(merged),
            'upload.html': gdl.upload_page_html(),
        }
    except Exception as e:
        _result("error", message=f"Failed while rendering shared pages: {e}")
        sys.exit(1)

    pushed = []
    try:
        for path, html in pages.items():
            fresh = call_tool('github_get_file_contents', {
                'connectionId': gh_conn, 'owner': OWNER, 'repo': REPO, 'path': path})
            sha = fresh.get('sha') if isinstance(fresh, dict) else None
            a = {'connectionId': gh_conn, 'owner': OWNER, 'repo': REPO,
                 'path': path, 'message': f"Space agent: update {path}", 'content': html}
            if sha:
                a['sha'] = sha
            call_tool('github_create_or_update_file', a)
            pushed.append(path)
    except Exception as e:
        _result("error", message=f"Failed while pushing shared pages (pushed so far: {pushed}): {e}")
        sys.exit(1)

    _result("ok", realms_included=sorted(merged['realms'].keys()), pages_updated=pushed)


if __name__ == '__main__':
    main()
