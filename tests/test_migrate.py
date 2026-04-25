"""
Unit tests for lib/migrate.py.

Phase 5 covers the basic shape (discovery, version reading, no-op when no
migrations exist). Phase 6 will exercise the full lifecycle (partial
upgrades, idempotency, atomicity, version stamping) once update.py lands.
"""
from __future__ import annotations

import sqlite3

import pytest


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


def test_apply_pending_no_migrations_noop(practice_repo):
    """Phase 5: real migrations/ dir is empty. apply_pending is a no-op."""
    import db
    import migrate
    conn = db.open_db()
    try:
        applied = migrate.apply_pending(conn)
        assert applied == []
        assert migrate.current_version(conn) == 0
    finally:
        conn.close()


def test_apply_pending_empty_dir(tmp_path, practice_repo):
    import db
    import migrate
    conn = db.open_db()
    try:
        d = tmp_path / 'migrations'
        d.mkdir()
        applied = migrate.apply_pending(conn, migrations_dir=d)
        assert applied == []
    finally:
        conn.close()
