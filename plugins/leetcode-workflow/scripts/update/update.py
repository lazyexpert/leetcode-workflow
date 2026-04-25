#!/usr/bin/env python3
"""
Apply pending DB migrations after a plugin update, refresh views, and
mark the current plugin version as seen (dismissing the update nudge).

Reads no input. Operates on the practice repo at cwd (or LEETCODE_REPO).

Behaviour:
  1. Open practice.db (rebuild from practice.sql if .db is absent —
     typical fresh-clone state).
  2. Apply migrations whose version > settings.schema_version. Each
     migration must wrap its body in BEGIN/COMMIT and end with the
     schema_version bump. apply_pending rolls back partial state if a
     migration fails.
  3. db.sync_config — mirror current config.json into the DB tables
     consulted by views.
  4. Bump settings.plugin_version_seen to the manifest's current version.
  5. Re-render the five views (schema changes may alter what they show).
  6. Refresh practice.sql.

Stdout: human-readable summary.

Exit codes:
  0 success
  1 not initialised / migration failed
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db            # noqa: E402
import migrate       # noqa: E402
import plugin_meta   # noqa: E402
import render        # noqa: E402


def main() -> int:
    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    pre_version = migrate.current_version(conn)
    try:
        applied = migrate.apply_pending(conn)
    except sqlite3.Error as e:
        conn.close()
        print(f'ERROR: migration failed: {e}', file=sys.stderr)
        return 1
    post_version = migrate.current_version(conn)

    try:
        db.sync_config(conn)
        version = plugin_meta.plugin_version()
        db.upsert_setting(conn, 'plugin_version_seen', version)
        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()

    if applied:
        print(f'update: applied migrations {applied} '
              f'(schema {pre_version} → {post_version})')
    else:
        print(f'update: schema is up-to-date (schema_version = {post_version})')
    print(f'        plugin_version_seen = {version}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
