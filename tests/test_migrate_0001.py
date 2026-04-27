"""
Tests for migration 0001_imported_attempts.sql.

Verifies the migration applies cleanly on top of the v0 baseline,
adds the `imported` column with the right default, leaves existing
data untouched, and bumps schema_version to 1.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

PLUGIN_ROOT  = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
MIGRATION    = PLUGIN_ROOT / 'migrations' / '0001_imported_attempts.sql'


def _baseline_then_migration(practice_repo):
    """Open the practice DB (baseline already applied by the fixture)
    and run migration 0001 against it. Returns the open connection."""
    import db
    import migrate
    conn = db.open_db()
    migrate.apply_pending(conn, migrations_dir=PLUGIN_ROOT / 'migrations')
    return conn


def test_0001_adds_imported_column(practice_repo):
    conn = _baseline_then_migration(practice_repo)
    try:
        cols = {r[1]: r for r in conn.execute('PRAGMA table_info(attempts)')}
        assert 'imported' in cols
        # column shape: type INTEGER, NOT NULL, default 0
        _, name, ctype, notnull, dflt, _ = cols['imported']
        assert ctype.upper()         == 'INTEGER'
        assert int(notnull)          == 1
        assert str(dflt).strip("'")  == '0'
    finally:
        conn.close()


def test_0001_bumps_schema_version(practice_repo):
    import migrate
    conn = _baseline_then_migration(practice_repo)
    try:
        assert migrate.current_version(conn) == 1
    finally:
        conn.close()


def test_0001_existing_attempts_default_to_zero(practice_repo):
    """Apply migration to a DB that already has attempts. Existing rows
    should pick up imported = 0 via the column default — they were not
    imported."""
    import db
    import migrate
    conn = db.open_db()
    # Seed a problem + attempt under the v0 baseline (no `imported` col yet).
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.start_attempt(conn, 1)
    conn.commit()

    migrate.apply_pending(conn, migrations_dir=PLUGIN_ROOT / 'migrations')

    rows = list(conn.execute(
        'SELECT problem_number, imported FROM attempts WHERE problem_number = 1'
    ))
    assert rows == [(1, 0)]
    conn.close()


def test_0001_idempotent_via_runner(practice_repo):
    """Re-running apply_pending after 0001 is a no-op — schema_version
    is already 1, so the migration body isn't re-executed."""
    import migrate
    conn = _baseline_then_migration(practice_repo)
    try:
        applied = migrate.apply_pending(conn, migrations_dir=PLUGIN_ROOT / 'migrations')
        assert applied == []
        assert migrate.current_version(conn) == 1
    finally:
        conn.close()


def test_0001_allows_imported_attempts_with_null_duration(practice_repo):
    """After migration, a row with duration_minutes IS NULL AND imported = 1
    is valid — the new shape that /import relies on."""
    conn = _baseline_then_migration(practice_repo)
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
