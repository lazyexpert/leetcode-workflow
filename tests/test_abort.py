"""
Subprocess tests for skills/abort/scripts/abort.py.
"""
from __future__ import annotations

import subprocess
import sys
import time

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'abort' / 'scripts' / 'abort.py'


def _run(repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def _scaffold(repo, number, difficulty, title, *, ext='ts', body=''):
    """Create folder + solution file, upsert problem, open in-progress attempt
    (matches what /new does)."""
    folder = f'{number}.{title.replace(" ", "_")}'
    section = 'SQL' if difficulty is None else difficulty
    sfile_ext = 'sql' if difficulty is None else ext
    d = repo / 'src' / section / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f'solution.{sfile_ext}').write_text(body)

    import db
    conn = db.open_db()
    kind = 'sql' if difficulty is None else 'algorithmic'
    db.upsert_problem(conn, number, title, difficulty, kind, folder)
    if kind == 'algorithmic':
        db.start_attempt(conn, number)
    conn.commit()
    conn.close()
    return d


def _close_attempt(repo, number):
    """Backdate + close the open attempt so it counts as a prior committed
    attempt for the next abort cycle."""
    import db
    conn = db.open_db()
    aid = db.latest_open_attempt(conn, number)[0]
    conn.execute('UPDATE attempts SET started_at = ? WHERE id = ?',
                 (int(time.time()) - 600, aid))
    db.complete_attempt(conn, aid, revisit=False)
    conn.commit()
    conn.close()


# ── sole-attempt rollback ──────────────────────────────────────────────────

def test_abort_sole_attempt_removes_problem_and_folder(practice_repo):
    folder = _scaffold(practice_repo, 1, 'Easy', 'Two Sum')
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    assert 'problem and folder removed' in result.stdout
    assert '1. Two Sum (Easy)' in result.stdout

    assert not folder.exists()
    import db
    conn = db.open_db()
    assert conn.execute('SELECT * FROM problems WHERE number = 1').fetchone() is None
    assert conn.execute('SELECT * FROM attempts WHERE problem_number = 1').fetchone() is None
    conn.close()


def test_abort_sole_attempt_cascades_patterns(practice_repo):
    folder = _scaffold(practice_repo, 1, 'Easy', 'Two Sum')
    import db
    conn = db.open_db()
    db.replace_patterns(conn, 1, ['Hash Map / Hash Set'])
    conn.commit()
    conn.close()

    _run(practice_repo)

    conn = db.open_db()
    rows = list(conn.execute('SELECT * FROM patterns WHERE problem_number = 1'))
    assert rows == []
    conn.close()


def test_abort_sole_attempt_sql_uses_sql_label(practice_repo):
    _scaffold(practice_repo, 177, None, 'Nth Highest Salary')
    # SQL "scaffold" via _scaffold doesn't open an attempt — synthesize one
    # to mimic an aborted /new mid-flight.
    import db
    conn = db.open_db()
    conn.execute(
        'INSERT INTO attempts (problem_number, started_at, duration_minutes) '
        'VALUES (?, ?, NULL)', (177, int(time.time())),
    )
    conn.commit()
    conn.close()

    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    assert '177. Nth Highest Salary (SQL)' in result.stdout


# ── prior-attempts: restore from HEAD ──────────────────────────────────────

def test_abort_with_prior_attempt_restores_from_head(git_repo):
    """One committed attempt + one in-progress attempt. Abort restores the
    solution file to its committed content; problem and the prior attempt
    survive."""
    folder = _scaffold(git_repo, 1, 'Easy', 'Two Sum', body='COMMITTED')
    _close_attempt(git_repo, 1)
    # Commit the closed-attempt state.
    subprocess.run(['git', 'add', '.'], cwd=git_repo, check=True)
    subprocess.run(['git', 'commit', '-q', '-m', '1. Easy. Two Sum'],
                   cwd=git_repo, check=True)

    # Now an in-progress retry: clobber the solution + open new attempt.
    sfile = folder / 'solution.ts'
    sfile.write_text('IN PROGRESS')
    import db
    conn = db.open_db()
    db.start_attempt(conn, 1)
    conn.commit()
    conn.close()

    result = _run(git_repo)
    assert result.returncode == 0, result.stderr
    assert f'restored src/Easy/1.Two_Sum/solution.ts' in result.stdout

    # Solution file restored.
    assert sfile.read_text() == 'COMMITTED'
    # Problem survives, only one attempt remains.
    conn = db.open_db()
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 1'))
    assert len(rows) == 1
    assert conn.execute('SELECT title FROM problems WHERE number = 1').fetchone() == ('Two Sum',)
    conn.close()


def test_abort_with_prior_attempt_no_solution_file_graceful(git_repo):
    """Edge case: prior attempts exist in DB but folder/file missing on disk."""
    folder = _scaffold(git_repo, 1, 'Easy', 'Two Sum')
    _close_attempt(git_repo, 1)
    # Open second attempt
    import db
    conn = db.open_db()
    db.start_attempt(conn, 1)
    conn.commit()
    conn.close()
    # Wipe folder to simulate disk drift.
    import shutil as _sh
    _sh.rmtree(folder)

    result = _run(git_repo)
    assert result.returncode == 0, result.stderr
    assert 'no solution file present to restore' in result.stdout


# ── nothing to abort ───────────────────────────────────────────────────────

def test_abort_no_in_progress_returns_1(practice_repo):
    result = _run(practice_repo)
    assert result.returncode == 1
    assert 'No in-progress attempt to abort' in result.stderr


def test_abort_with_only_closed_attempts_is_noop(practice_repo):
    _scaffold(practice_repo, 1, 'Easy', 'Two Sum')
    _close_attempt(practice_repo, 1)
    result = _run(practice_repo)
    assert result.returncode == 1


def test_abort_errors_when_not_initialized(empty_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr


# ── view + dump regen ──────────────────────────────────────────────────────

def test_abort_renders_views_and_dumps(practice_repo):
    _scaffold(practice_repo, 1, 'Easy', 'Two Sum')
    _run(practice_repo)
    # progress.md should reflect zero problems after the rollback.
    progress = (practice_repo / 'progress.md').read_text()
    assert '| **Total**  | **0** |' in progress
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'Two Sum' not in sql
