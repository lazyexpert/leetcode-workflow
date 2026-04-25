#!/usr/bin/env python3
"""
Print the update nudge if the user's plugin_version_seen differs from
the current plugin manifest version. Otherwise prints nothing.

Output (single line, or empty):
  ⓘ leetcode-workflow updated to v<X.Y.Z> — run /leetcode-workflow:update to apply migrations

Exit code: always 0. The nudge is purely informational and must never
fail a skill. If the repo isn't initialised, the DB is unreadable, or
the manifest can't be loaded, the script exits silently.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import plugin_meta  # noqa: E402


def main() -> int:
    if not db.DB_PATH.exists():
        return 0  # not initialised; silent

    try:
        conn = sqlite3.connect(db.DB_PATH)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'plugin_version_seen'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return 0

    try:
        current = plugin_meta.plugin_version()
    except (FileNotFoundError, KeyError, ValueError):
        return 0

    seen = row[0] if row else ''
    if seen == current:
        return 0

    print(f'ⓘ leetcode-workflow updated to v{current} — '
          f'run /leetcode-workflow:update to apply migrations')
    return 0


if __name__ == '__main__':
    sys.exit(main())
