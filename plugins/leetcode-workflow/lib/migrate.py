"""
Migration runner for the leetcode-workflow plugin.

Used by:
  /leetcode-workflow:init   — applies baseline + any pending migrations
  /leetcode-workflow:update — applies pending migrations after a plugin update

Migration files live at <plugin_root>/migrations/000N_<desc>.sql. Each
file's last statement is `INSERT OR REPLACE INTO settings VALUES
('schema_version', 'N')` so the version cursor advances atomically with
the migration body. Files are wrapped in `BEGIN; ... COMMIT;` for the
same atomicity reason.

This module is pure SQL orchestration — no DB writes happen here beyond
running migration scripts the user authored.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / 'migrations'
_MIGRATION_RX = re.compile(r'^(\d+)_.*\.sql$')


def discover_migrations(migrations_dir: Path | None = None) -> list[tuple[int, Path]]:
    """Return [(version, path), ...] sorted ascending by version. Skips
    files that don't match the 000N_<desc>.sql convention."""
    target = migrations_dir if migrations_dir is not None else MIGRATIONS_DIR
    if not target.exists():
        return []
    found = []
    for p in sorted(target.iterdir()):
        m = _MIGRATION_RX.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    found.sort(key=lambda x: x[0])
    return found


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0]) if row else 0


def apply_pending(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> list[int]:
    """Apply migrations whose version > current schema_version. Each
    migration is responsible for bumping schema_version as its last
    statement (per convention, wrapped in BEGIN/COMMIT for atomicity).
    Returns the list of versions that were applied.

    Atomicity: if a migration fails partway through (executescript
    raises), we explicitly rollback to discard any uncommitted statements
    from the migration's BEGIN block. The exception propagates to the
    caller. Migrations applied earlier in this call stay applied.
    """
    cur     = current_version(conn)
    applied = []
    for version, path in discover_migrations(migrations_dir):
        if version <= cur:
            continue
        try:
            conn.executescript(path.read_text())
        except sqlite3.Error:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        conn.commit()
        applied.append(version)
    return applied
