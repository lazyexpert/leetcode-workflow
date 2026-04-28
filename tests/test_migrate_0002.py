"""
Tests for migration 0002_portable_retry_flags.sql.

Verifies that applying 0002 on top of baseline + 0001:
  * recreates the retry_flags VIEW
  * stores a definition free of unixepoch()
  * leaves the VIEW queryable with sane results on a populated DB
  * advances schema_version to 2

The motivation for this migration is portability — `unixepoch()` is
SQLite 3.38+ only, and the macos-latest GHA runner with Python 3.9
ships an older SQLite where any retry_flags query fails to compile.
We can't simulate that locally (the dev box has a recent SQLite), but
we can confirm structurally that the function reference is gone.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

PLUGIN_ROOT  = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
MIGRATIONS   = PLUGIN_ROOT / 'migrations'


def _isolate(tmp_path: Path, *names: str) -> Path:
    """Build a tmp migrations dir containing the named migrations only,
    so tests can apply controlled subsets (e.g. just 0001+0002).
    Idempotent so the same test can call _isolate twice without conflict."""
    d = tmp_path / 'migrations-isolated'
    d.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(MIGRATIONS / name, d / name)
    return d


def _open_with_0001_and_0002(baseline_repo, tmp_path):
    import db
    import migrate
    conn = db.open_db()
    isolated = _isolate(
        tmp_path,
        '0001_imported_attempts.sql',
        '0002_portable_retry_flags.sql',
    )
    migrate.apply_pending(conn, migrations_dir=isolated)
    return conn


def test_0002_bumps_schema_version_to_two(baseline_repo, tmp_path):
    import migrate
    conn = _open_with_0001_and_0002(baseline_repo, tmp_path)
    try:
        assert migrate.current_version(conn) == 2
    finally:
        conn.close()


def test_0002_view_definition_drops_unixepoch(baseline_repo, tmp_path):
    """The stored VIEW SQL must not reference unixepoch — that's the
    whole point of the migration. Use sqlite_master to read back the
    DDL SQLite stored when CREATE VIEW ran."""
    conn = _open_with_0001_and_0002(baseline_repo, tmp_path)
    try:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'view' AND name = 'retry_flags'"
        ).fetchone()[0]
        assert 'unixepoch' not in sql.lower()
        # Sanity: the portable replacement is in place.
        assert "strftime('%s', 'now')" in sql
    finally:
        conn.close()


def test_0002_retry_flags_query_works_on_populated_db(baseline_repo, tmp_path):
    """End-to-end: with a problem and an old attempt, retry_flags should
    be queryable and report `stale = 1` (default cooldown is 7 days; the
    seeded attempt is 30 days old)."""
    import db
    conn = _open_with_0001_and_0002(baseline_repo, tmp_path)
    try:
        # Mirror the default cooldown into thresholds so timing flag has
        # a value to compare against (the helper writes both).
        db.sync_config(conn)
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        # Attempt seeded 30 days ago.
        old_ts = int(time.time()) - 30 * 86400
        conn.execute(
            'INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit, imported) '
            'VALUES (?, ?, 5, 0, 0)',
            (1, old_ts),
        )
        conn.commit()

        rows = list(conn.execute(
            'SELECT number, timing_bad, complexity_bad, stale FROM retry_flags'
        ))
        assert len(rows) == 1
        number, timing_bad, complexity_bad, stale = rows[0]
        assert number == 1
        assert stale  == 1   # 30 days >> 7-day cooldown
        assert timing_bad     == 0   # 5 min < 15 min Easy threshold
        assert complexity_bad == 0
    finally:
        conn.close()


def test_0002_idempotent_via_runner(baseline_repo, tmp_path):
    """Re-running apply_pending after 0002 is a no-op."""
    import migrate
    conn = _open_with_0001_and_0002(baseline_repo, tmp_path)
    try:
        isolated = _isolate(
            tmp_path,
            '0001_imported_attempts.sql',
            '0002_portable_retry_flags.sql',
        )
        # Note: the dir already exists from setup; recreate cleanly.
        applied = migrate.apply_pending(conn, migrations_dir=isolated)
        assert applied == []
        assert migrate.current_version(conn) == 2
    finally:
        conn.close()
