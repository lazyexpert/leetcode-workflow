"""
Subprocess tests for lib/render_and_dump.py — the shared "regenerate views
and refresh the SQL dump" CLI.
"""
from __future__ import annotations

import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env

SCRIPT = PLUGIN_ROOT / 'lib' / 'render_and_dump.py'


def test_render_and_dump_writes_views_and_sql(practice_repo):
    # Seed via lib so we don't depend on other scripts.
    import db
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.upsert_thresholds(conn, db.load_thresholds())
    conn.commit()
    conn.close()

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=practice_repo, env=script_env(practice_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ('progress.md', 'timings.md', 'retry.md',
                 'patterns-coverage.md', 'history.md'):
        assert (practice_repo / name).exists()
    assert 'Two Sum' in (practice_repo / '.claude' / 'practice.sql').read_text()


def test_render_and_dump_errors_when_not_initialized(empty_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr
