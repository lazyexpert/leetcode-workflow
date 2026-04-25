"""
Subprocess tests for lib/nudge.py.

The nudge is informational — exit code is always 0; stdout is either
empty or one line. Tests verify output content, not exit code, since
the script never blocks a skill.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env

SCRIPT = PLUGIN_ROOT / 'lib' / 'nudge.py'


def _run(repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def _set_seen(repo, value):
    conn = sqlite3.connect(repo / '.claude' / 'practice.db')
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('plugin_version_seen', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (value,),
    )
    conn.commit()
    conn.close()


def _plugin_version():
    import plugin_meta
    return plugin_meta.plugin_version()


# ── silent paths ───────────────────────────────────────────────────────────

def test_silent_when_seen_matches_current(practice_repo):
    _set_seen(practice_repo, _plugin_version())
    result = _run(practice_repo)
    assert result.returncode == 0
    assert result.stdout == ''


def test_silent_when_not_initialized(empty_repo):
    """No practice.db — nudge stays silent (script can't tell if it's
    supposed to run there at all)."""
    result = _run(empty_repo)
    assert result.returncode == 0
    assert result.stdout == ''


def test_silent_when_db_corrupt(practice_repo):
    """Truncated DB file — nudge swallows the sqlite error and stays silent."""
    db_path = practice_repo / '.claude' / 'practice.db'
    db_path.write_bytes(b'not a valid sqlite file')
    result = _run(practice_repo)
    assert result.returncode == 0
    assert result.stdout == ''


# ── firing paths ───────────────────────────────────────────────────────────

def test_fires_when_seen_differs_from_current(practice_repo):
    _set_seen(practice_repo, '0.0.0')
    result = _run(practice_repo)
    assert result.returncode == 0
    expected = (f'ⓘ leetcode-workflow updated to v{_plugin_version()} — '
                f'run /leetcode-workflow:update to apply migrations')
    assert result.stdout.strip() == expected


def test_fires_when_seen_empty(practice_repo):
    """Pre-Phase-6 init left plugin_version_seen = ''. Nudge fires —
    user runs /update which populates it."""
    _set_seen(practice_repo, '')
    result = _run(practice_repo)
    assert result.returncode == 0
    assert 'ⓘ leetcode-workflow updated to' in result.stdout


def test_fires_with_current_version_in_message(practice_repo):
    """Verify the message embeds the manifest's actual version, not a
    hardcoded one."""
    _set_seen(practice_repo, '0.0.0')
    result = _run(practice_repo)
    assert f'v{_plugin_version()}' in result.stdout


# ── lifecycle: update.py dismisses the nudge ───────────────────────────────

def test_running_update_dismisses_nudge(practice_repo):
    _set_seen(practice_repo, '0.0.0')
    # Pre: nudge fires
    assert _run(practice_repo).stdout != ''
    # Run update
    update = PLUGIN_ROOT / 'scripts' / 'update' / 'update.py'
    subprocess.run(
        [sys.executable, str(update)],
        cwd=practice_repo, env=script_env(practice_repo),
        capture_output=True, text=True, check=True,
    )
    # Post: nudge silent
    assert _run(practice_repo).stdout == ''
