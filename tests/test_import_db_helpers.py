"""
Tests for the new lib/db.py helpers introduced for /leetcode-workflow:import:

* `import_attempt(conn, number, started_at)` — inserts a completed-but-
  imported attempt row (imported = 1, duration_minutes = NULL).
* `latest_open_attempt(conn, number)` — must now ignore imported rows.

All tests apply migration 0001 to the baseline DB so the `imported`
column exists.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
MIGRATIONS  = PLUGIN_ROOT / 'migrations'


def _open_with_migration():
    import db
    import migrate
    conn = db.open_db()
    migrate.apply_pending(conn, migrations_dir=MIGRATIONS)
    return conn


def test_import_attempt_inserts_with_imported_flag(practice_repo):
    import db
    conn = _open_with_migration()
    try:
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        ts = 1_521_093_780
        attempt_id = db.import_attempt(conn, 1, ts)
        row = conn.execute(
            'SELECT id, problem_number, started_at, duration_minutes, revisit, imported '
            'FROM attempts WHERE id = ?',
            (attempt_id,),
        ).fetchone()
        assert row == (attempt_id, 1, ts, None, 0, 1)
    finally:
        conn.close()


def test_import_attempt_collision_bumps_started_at(practice_repo):
    """If two imports for the same problem share a timestamp (synthetic
    test, but git mtime can collide on the same second), the helper bumps
    by a second to satisfy UNIQUE(problem_number, started_at)."""
    import db
    conn = _open_with_migration()
    try:
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        ts = 1_521_093_780
        first  = db.import_attempt(conn, 1, ts)
        second = db.import_attempt(conn, 1, ts)
        first_ts = conn.execute(
            'SELECT started_at FROM attempts WHERE id = ?', (first,)
        ).fetchone()[0]
        second_ts = conn.execute(
            'SELECT started_at FROM attempts WHERE id = ?', (second,)
        ).fetchone()[0]
        assert first_ts  == ts
        assert second_ts == ts + 1
    finally:
        conn.close()


def test_latest_open_attempt_ignores_imported(practice_repo):
    """An imported attempt must not be returned by latest_open_attempt —
    /done would otherwise close it and compute multi-year durations."""
    import db
    conn = _open_with_migration()
    try:
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        # An imported attempt that LOOKS open (NULL duration) but isn't.
        db.import_attempt(conn, 1, 1_521_093_780)
        assert db.latest_open_attempt(conn, 1) is None
    finally:
        conn.close()


def test_latest_open_attempt_finds_real_open_attempt_alongside_import(practice_repo):
    """An import sits in the table; user starts a fresh /new attempt; the
    fresh one (imported = 0, duration NULL) is what latest_open_attempt
    returns, not the import."""
    import db
    conn = _open_with_migration()
    try:
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        db.import_attempt(conn, 1, 1_521_093_780)
        fresh_id = db.start_attempt(conn, 1)
        result = db.latest_open_attempt(conn, 1)
        assert result is not None
        attempt_id, _ = result
        assert attempt_id == fresh_id
    finally:
        conn.close()


def test_complete_attempt_works_after_import_in_same_problem(practice_repo):
    """End-to-end: import → fresh attempt → complete it. The completed
    attempt should not collide with the import, and timing should
    measure from the fresh started_at, not the import's."""
    import db
    conn = _open_with_migration()
    try:
        db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        db.import_attempt(conn, 1, 1_521_093_780)   # 2018-ish
        # Fresh attempt — start_attempt uses time.time(), so completion
        # produces a sane (small) duration_minutes.
        fresh_id = db.start_attempt(conn, 1)
        duration = db.complete_attempt(conn, fresh_id, revisit=False)
        # Sub-minute solves bucket to 1 minute (per complete_attempt docstring).
        assert duration <= 1
    finally:
        conn.close()
