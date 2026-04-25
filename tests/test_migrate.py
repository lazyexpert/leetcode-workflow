"""
Unit tests for lib/migrate.py.

Discovery + version-read tests use no DB writes. Lifecycle tests
(applying real fixture migrations against a baseline DB) verify the
runner's transactional behaviour: idempotency, partial-state upgrade,
atomic rollback on failure.
"""
from __future__ import annotations

import sqlite3

import pytest

# ── discover_migrations ─────────────────────────────────────────────────────

def test_discover_empty_dir(tmp_path):
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    assert migrate.discover_migrations(d) == []


def test_discover_missing_dir(tmp_path):
    import migrate
    assert migrate.discover_migrations(tmp_path / 'absent') == []


def test_discover_filters_non_migration_files(tmp_path):
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    (d / '0001_init.sql').write_text('-- noop')
    (d / 'README.md').write_text('not a migration')
    (d / 'notes.txt').write_text('also not')
    found = migrate.discover_migrations(d)
    assert [v for v, _ in found] == [1]


def test_discover_orders_by_version(tmp_path):
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    (d / '0010_late.sql').write_text('-- noop')
    (d / '0002_mid.sql').write_text('-- noop')
    (d / '0001_first.sql').write_text('-- noop')
    found = migrate.discover_migrations(d)
    assert [v for v, _ in found] == [1, 2, 10]


# ── current_version ─────────────────────────────────────────────────────────

def test_current_version_reads_baseline(practice_repo):
    import db
    import migrate
    conn = db.open_db()
    try:
        assert migrate.current_version(conn) == 0
    finally:
        conn.close()


def test_current_version_returns_zero_when_setting_missing():
    import migrate
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);'
    )
    try:
        assert migrate.current_version(conn) == 0
    finally:
        conn.close()


# ── apply_pending lifecycle (fixture migrations) ────────────────────────────

def _migration(content: str) -> str:
    """Wrap a migration body in BEGIN/COMMIT + the schema_version bump."""
    return content


def _write_migration(d, version, body):
    (d / f'{version:04d}_test.sql').write_text(
        f'BEGIN;\n{body}\n'
        f"INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '{version}');\n"
        f'COMMIT;\n'
    )


def test_apply_pending_no_migrations_noop(practice_repo):
    """Phase 5/6: real migrations/ dir is empty — no-op."""
    import db
    import migrate
    conn = db.open_db()
    try:
        applied = migrate.apply_pending(conn)
        assert applied == []
        assert migrate.current_version(conn) == 0
    finally:
        conn.close()


def test_apply_pending_runs_migration_and_bumps_version(practice_repo, tmp_path):
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    _write_migration(d, 1, 'ALTER TABLE problems ADD COLUMN tags TEXT;')

    conn = db.open_db()
    try:
        applied = migrate.apply_pending(conn, migrations_dir=d)
        assert applied == [1]
        assert migrate.current_version(conn) == 1
        # New column actually exists.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(problems)")]
        assert 'tags' in cols
    finally:
        conn.close()


def test_apply_pending_runs_in_numerical_order(practice_repo, tmp_path):
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    _write_migration(d, 1, 'ALTER TABLE problems ADD COLUMN col_a TEXT;')
    _write_migration(d, 2, 'ALTER TABLE problems ADD COLUMN col_b TEXT;')
    _write_migration(d, 10, 'ALTER TABLE problems ADD COLUMN col_j TEXT;')

    conn = db.open_db()
    try:
        applied = migrate.apply_pending(conn, migrations_dir=d)
        assert applied == [1, 2, 10]
        assert migrate.current_version(conn) == 10
    finally:
        conn.close()


def test_apply_pending_skips_already_applied(practice_repo, tmp_path):
    """If schema_version is already 5, only migrations >5 are applied."""
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    for v in (1, 2, 5, 10):
        _write_migration(d, v, f'-- migration v{v} (no schema change)')

    conn = db.open_db()
    try:
        # Force schema_version to 5
        db.upsert_setting(conn, 'schema_version', '5')
        conn.commit()

        applied = migrate.apply_pending(conn, migrations_dir=d)
        assert applied == [10]
        assert migrate.current_version(conn) == 10
    finally:
        conn.close()


def test_apply_pending_idempotent(practice_repo, tmp_path):
    """Running apply_pending twice produces the same result the second time."""
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    _write_migration(d, 1, 'ALTER TABLE problems ADD COLUMN tags TEXT;')

    conn = db.open_db()
    try:
        first  = migrate.apply_pending(conn, migrations_dir=d)
        second = migrate.apply_pending(conn, migrations_dir=d)
        assert first  == [1]
        assert second == []
        assert migrate.current_version(conn) == 1
    finally:
        conn.close()


def test_apply_pending_atomicity_on_failure(practice_repo, tmp_path):
    """A migration that fails partway through must leave the DB unchanged.
    Schema_version should remain at its pre-call value, and any DDL the
    failed migration ran before crashing must be rolled back."""
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    # Two ALTERs adding the same column — second one fails, first is rolled back.
    (d / '0001_broken.sql').write_text(
        'BEGIN;\n'
        'ALTER TABLE problems ADD COLUMN dup_col TEXT;\n'
        'ALTER TABLE problems ADD COLUMN dup_col TEXT;\n'  # duplicate column
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '1');\n"
        'COMMIT;\n'
    )

    conn = db.open_db()
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate.apply_pending(conn, migrations_dir=d)

        # Version untouched.
        assert migrate.current_version(conn) == 0
        # Column not present (rollback worked).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(problems)")]
        assert 'dup_col' not in cols
    finally:
        conn.close()


def test_apply_pending_stops_at_first_failure(practice_repo, tmp_path):
    """If 0001 succeeds and 0002 fails, 0001 stays applied; 0003 is not
    reached. apply_pending raises and current_version reflects the
    successful migration only."""
    import db
    import migrate
    d = tmp_path / 'migrations'
    d.mkdir()
    _write_migration(d, 1, 'ALTER TABLE problems ADD COLUMN col_ok TEXT;')
    (d / '0002_broken.sql').write_text(
        'BEGIN;\n'
        'ALTER TABLE problems ADD COLUMN col_ok TEXT;\n'  # already exists
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '2');\n"
        'COMMIT;\n'
    )
    _write_migration(d, 3, 'ALTER TABLE problems ADD COLUMN col_three TEXT;')

    conn = db.open_db()
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate.apply_pending(conn, migrations_dir=d)

        assert migrate.current_version(conn) == 1
        cols = [r[1] for r in conn.execute("PRAGMA table_info(problems)")]
        assert 'col_ok'    in cols     # migration 1 stayed
        assert 'col_three' not in cols  # migration 3 not reached
    finally:
        conn.close()
