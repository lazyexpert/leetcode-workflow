"""
Tests for migration 0001_imported_attempts.sql.

Each test isolates 0001 by copying just that file into a tmp migrations
directory and applying it on top of `baseline_repo` (the v0 baseline
fixture, no other migrations yet). This keeps the assertions stable as
later migrations stack — without it, asserting `schema_version == 1`
breaks the moment 0002 lands.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
MIGRATION   = PLUGIN_ROOT / 'migrations' / '0001_imported_attempts.sql'


def _isolate_0001(tmp_path: Path) -> Path:
    """Build a tmp migrations dir containing only 0001. Idempotent so
    a single test can call it more than once."""
    d = tmp_path / 'migrations-only-0001'
    d.mkdir(exist_ok=True)
    shutil.copy(MIGRATION, d / MIGRATION.name)
    return d


def _open_with_0001(baseline_repo, tmp_path):
    import db
    import migrate
    conn = db.open_db()
    migrate.apply_pending(conn, migrations_dir=_isolate_0001(tmp_path))
    return conn


def test_0001_adds_imported_column(baseline_repo, tmp_path):
    conn = _open_with_0001(baseline_repo, tmp_path)
    try:
        cols = {r[1]: r for r in conn.execute('PRAGMA table_info(attempts)')}
        assert 'imported' in cols
        # column shape: type INTEGER, NOT NULL, default 0
        _, _, ctype, notnull, dflt, _ = cols['imported']
        assert ctype.upper()         == 'INTEGER'
        assert int(notnull)          == 1
        assert str(dflt).strip("'")  == '0'
    finally:
        conn.close()


def test_0001_bumps_schema_version_to_one(baseline_repo, tmp_path):
    """Applying 0001 alone advances schema_version from 0 to 1."""
    import migrate
    conn = _open_with_0001(baseline_repo, tmp_path)
    try:
        assert migrate.current_version(conn) == 1
    finally:
        conn.close()


def test_0001_existing_attempts_default_to_zero(baseline_repo, tmp_path):
    """Apply migration on a baseline DB that already has attempts.
    Existing rows should pick up imported = 0 via the column default."""
    import db
    import migrate
    conn = db.open_db()
    # Seed under v0 baseline (no `imported` column yet).
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.start_attempt(conn, 1)
    conn.commit()

    migrate.apply_pending(conn, migrations_dir=_isolate_0001(tmp_path))

    rows = list(conn.execute(
        'SELECT problem_number, imported FROM attempts WHERE problem_number = 1'
    ))
    assert rows == [(1, 0)]
    conn.close()


def test_0001_idempotent_via_runner(baseline_repo, tmp_path):
    """Re-running apply_pending after 0001 is a no-op — schema_version
    is already 1, so the migration body isn't re-executed."""
    import migrate
    conn = _open_with_0001(baseline_repo, tmp_path)
    try:
        applied = migrate.apply_pending(
            conn, migrations_dir=_isolate_0001(tmp_path),
        )
        assert applied == []
        assert migrate.current_version(conn) == 1
    finally:
        conn.close()


def test_0001_allows_imported_attempts_with_null_duration(baseline_repo, tmp_path):
    """After migration, a row with duration_minutes IS NULL AND imported = 1
    is valid — the new shape that /import relies on."""
    conn = _open_with_0001(baseline_repo, tmp_path)
    try:
        conn.execute(
            "INSERT INTO problems VALUES (1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum', ?)",
            (int(time.time()),),
        )
        conn.execute(
            "INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit, imported) "
            "VALUES (1, ?, NULL, 0, 1)",
            (int(time.time()),),
        )
        conn.commit()
        row = conn.execute(
            'SELECT duration_minutes, imported FROM attempts WHERE problem_number = 1'
        ).fetchone()
        assert row == (None, 1)
    except sqlite3.Error as e:
        # Surface the exact SQLite error if the schema rejects the row.
        raise AssertionError(f'imported attempt rejected: {e}') from e
    finally:
        conn.close()
