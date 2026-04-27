"""
Subprocess tests for scripts/import_repo/preflight.py.

Three exit codes:
  * 0 — fresh init'd practice repo, ready to import
  * 1 — not initialised
  * 2 — already populated
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import script_env

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
SCRIPT      = PLUGIN_ROOT / 'scripts' / 'import_repo' / 'preflight.py'


def _run(repo: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def test_preflight_ready_on_fresh_init(practice_repo):
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    assert 'preflight: ready' in result.stdout


def test_preflight_exits_one_when_not_initialised(empty_repo):
    result = _run(empty_repo)
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr


def test_preflight_exits_two_when_problems_exist(practice_repo):
    """Seeding a problem under the baseline and running preflight should
    exit 2 — /import refuses to merge into a populated repo."""
    import db
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    conn.commit()
    conn.close()

    result = _run(practice_repo)
    assert result.returncode == 2
    assert 'already has 1 problem' in result.stderr
