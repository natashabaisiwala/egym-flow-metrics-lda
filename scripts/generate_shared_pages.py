"""
DEPRECATED — do not use.

This script was an early draft of the Space agent's shared-pages logic. It
duplicated the entire chart/HTML rendering engine inline instead of importing
generate_dashboards_live.py, so it has drifted from the engine and is NOT
what the Space agent (Dataleap agent id a_w9zf9du2yy0wtizi02j7) actually runs.

Use scripts/update_shared_pages.py instead. That script:
  - bootstraps /agent/home/generate_dashboards_live.py from this repo's
    scripts/generate_dashboards_live.py (imported as a module, never executed
    via its run()),
  - discovers every data-<realm>.json file at repo root,
  - merges them into one {"realms": {...}} structure (reporting a
    config_error if two files claim the same realm id),
  - calls main_index_html(), global_dashboard_html(), and upload_page_html()
    from the imported engine module,
  - pushes ONLY index.html, global-dashboard.html, and upload.html.

This file is kept only so old links/history aren't broken. It performs no
action if executed and will be removed once nothing references it.
"""

if __name__ == '__main__':
    raise SystemExit(
        "generate_shared_pages.py is deprecated — use scripts/update_shared_pages.py instead."
    )
