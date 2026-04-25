"""
Subprocess tests for skills/update/scripts/update.py.

The update orchestration is tested against the real (empty) migrations
dir — migration runner edge cases live in test_migrate.py with stubbed
fixture dirs.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'update' / 'scripts' / 'update.py'


def _run(repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def _read_setting(repo, key):
    conn = sqlite3.connect(repo / '.claude' / 'practice.db')
    try:
        row = conn.execute(
            'SELECT value FROM settings WHERE key = ?', (key,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _plugin_version():
    import plugin_meta
    return plugin_meta.plugin_version()


# ── happy path: no pending migrations ──────────────────────────────────────

def test_update_no_pending_says_up_to_date(practice_repo):
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    assert 'schema is up-to-date' in result.stdout
    assert 'schema_version = 0' in result.stdout


def test_update_bumps_plugin_version_seen(practice_repo):
    # Force seen back to '' so we observe the bump.
    conn = sqlite3.connect(practice_repo / '.claude' / 'practice.db')
    conn.execute("UPDATE settings SET value = '' WHERE key = 'plugin_version_seen'")
    conn.commit()
    conn.close()

    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    assert _read_setting(practice_repo, 'plugin_version_seen') == _plugin_version()
    assert f'plugin_version_seen = {_plugin_version()}' in result.stdout


def test_update_idempotent(practice_repo):
    """Running update twice is safe and produces the same end state."""
    _run(practice_repo)
    state1 = _read_setting(practice_repo, 'plugin_version_seen')
    _run(practice_repo)
    state2 = _read_setting(practice_repo, 'plugin_version_seen')
    assert state1 == state2 == _plugin_version()


def test_update_renders_views(practice_repo):
    """View files should be rewritten — verify by deleting them and
    confirming they're recreated."""
    for name in ('progress.md', 'timings.md', 'retry.md',
                 'patterns-coverage.md', 'history.md'):
        (practice_repo / name).unlink(missing_ok=True)
    _run(practice_repo)
    for name in ('progress.md', 'timings.md', 'retry.md',
                 'patterns-coverage.md', 'history.md'):
        assert (practice_repo / name).exists()


def test_update_dumps_sql(practice_repo):
    _run(practice_repo)
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'CREATE TABLE' in sql
    assert "'plugin_version_seen'" in sql


def test_update_syncs_config_into_db(practice_repo):
    """If the user changed config.json since init, update should mirror
    the new thresholds into the DB."""
    (practice_repo / 'config.json').write_text(json.dumps({
        'language': {'extension': 'ts', 'name': 'typescript'},
        'retry_thresholds_minutes': {'Easy': 9, 'Medium': 24, 'Hard': 49},
        'review_cooldown_days': 14,
    }))
    _run(practice_repo)

    conn = sqlite3.connect(practice_repo / '.claude' / 'practice.db')
    try:
        rows = dict(conn.execute('SELECT difficulty, minutes FROM thresholds'))
        assert rows == {'Easy': 9, 'Medium': 24, 'Hard': 49}
        cooldown = conn.execute(
            "SELECT value FROM settings WHERE key = 'review_cooldown_days'"
        ).fetchone()
        assert cooldown == ('14',)
    finally:
        conn.close()


# ── error paths ────────────────────────────────────────────────────────────

def test_update_errors_when_not_initialized(empty_repo):
    result = _run(empty_repo)
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr


def test_update_rebuilds_db_from_sql_when_db_missing(practice_repo):
    """Fresh-clone state: practice.sql exists but practice.db is missing.
    open_db() rebuilds; update proceeds normally."""
    # Seed the dump first.
    import db
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.dump_sql(conn)
    conn.close()
    # Drop the binary.
    (practice_repo / '.claude' / 'practice.db').unlink()

    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    # Rebuilt DB has the row.
    conn = sqlite3.connect(practice_repo / '.claude' / 'practice.db')
    try:
        row = conn.execute('SELECT title FROM problems WHERE number = 1').fetchone()
        assert row == ('Two Sum',)
    finally:
        conn.close()
