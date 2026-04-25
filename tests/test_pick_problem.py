"""
Subprocess tests for scripts/retry/pick_problem.py.

Random-mode determinism: tests seed a single-element pool so the
random.choice() result is the only valid answer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from conftest import PLUGIN_ROOT, script_env

SCRIPT = PLUGIN_ROOT / 'scripts' / 'retry' / 'pick_problem.py'


def _run(repo, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def _seed_problem(repo, number, difficulty, title, *,
                  ext='ts', body='let x = 1;', closed_offset_sec=0,
                  in_progress=False, revisit=False, duration=10):
    """Create a problem folder + db rows. closed_offset_sec is how long ago
    the (closed) attempt started, so we can control cooldown/stale logic."""
    folder = f'{number}.{title.replace(" ", "_")}'
    section = 'SQL' if difficulty is None else difficulty
    d = repo / 'src' / section / folder
    d.mkdir(parents=True, exist_ok=True)
    sfile_ext = 'sql' if difficulty is None else ext
    (d / f'solution.{sfile_ext}').write_text(body)

    import db
    conn = db.open_db()
    kind = 'sql' if difficulty is None else 'algorithmic'
    db.upsert_problem(conn, number, title, difficulty, kind, folder)
    if not in_progress:
        started_at = int(time.time()) - closed_offset_sec
        conn.execute(
            'INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit) '
            'VALUES (?, ?, ?, ?)',
            (number, started_at, duration, 1 if revisit else 0),
        )
    conn.commit()
    conn.close()


def _set_cooldown(repo, days):
    (repo / 'config.json').write_text(json.dumps({'review_cooldown_days': days}))


# ── random mode ────────────────────────────────────────────────────────────

def test_pick_random_picks_the_only_stale_candidate(practice_repo):
    _set_cooldown(practice_repo, 0)
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=86400)
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['number']        == 1
    assert payload['title']         == 'Two Sum'
    assert payload['difficulty']    == 'Easy'
    assert payload['solution_path'] == 'src/Easy/1.Two_Sum/solution.ts'
    assert payload['language_name'] == 'typescript'
    assert 'stale' in payload['reasons']


def test_pick_random_empty_pool_when_cooldown_holds(practice_repo):
    _set_cooldown(practice_repo, 30)
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=60)
    result = _run(practice_repo)
    assert result.returncode == 1
    assert 'No retry candidates outside the cooldown window' in result.stderr


def test_pick_random_empty_pool_when_no_problems(practice_repo):
    result = _run(practice_repo)
    assert result.returncode == 1
    assert 'No retry candidates' in result.stderr


def test_pick_random_skips_sql(practice_repo):
    _set_cooldown(practice_repo, 0)
    # Only an SQL problem in the pool — random mode finds nothing.
    _seed_problem(practice_repo, 177, None, 'Nth Highest Salary', closed_offset_sec=86400)
    result = _run(practice_repo)
    assert result.returncode == 1
    assert 'No retry candidates' in result.stderr


def test_pick_random_picks_from_eligible_only(practice_repo):
    """One algorithmic problem stale, another within cooldown — only the
    stale one is eligible."""
    _set_cooldown(practice_repo, 7)
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=10 * 86400)  # stale
    _seed_problem(practice_repo, 2, 'Easy', 'Add Two Numbers', closed_offset_sec=60)  # fresh
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['number'] == 1


def test_pick_random_includes_reasons(practice_repo):
    _set_cooldown(practice_repo, 0)
    # 20 min on Easy (default 15) → timing_bad; revisit=True → complexity_bad; stale via cooldown=0.
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum',
                  closed_offset_sec=86400, revisit=True, duration=20)
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload['reasons']) == {'timing', 'complexity', 'stale'}


# ── explicit mode ──────────────────────────────────────────────────────────

def test_pick_explicit_finds_problem(practice_repo):
    _seed_problem(practice_repo, 19, 'Medium', 'Remove Nth Node From End of List',
                  closed_offset_sec=60)
    result = _run(practice_repo, '19')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['number']     == 19
    assert payload['difficulty'] == 'Medium'
    assert payload['solution_path'].endswith('solution.ts')


def test_pick_explicit_bypasses_cooldown(practice_repo):
    _set_cooldown(practice_repo, 30)
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=60)
    result = _run(practice_repo, '1')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['number'] == 1
    # Reasons should be empty — recent attempt, within Easy threshold, no revisit.
    assert payload['reasons'] == []


def test_pick_explicit_unknown_number(practice_repo):
    result = _run(practice_repo, '999')
    assert result.returncode == 1
    assert 'problem 999 not found' in result.stderr


def test_pick_explicit_rejects_sql(practice_repo):
    _seed_problem(practice_repo, 177, None, 'Nth Highest Salary')
    result = _run(practice_repo, '177')
    assert result.returncode == 1
    assert 'not algorithmic' in result.stderr


def test_pick_explicit_non_int_arg(practice_repo):
    result = _run(practice_repo, 'nineteen')
    assert result.returncode != 0


# ── shared error paths ─────────────────────────────────────────────────────

def test_pick_errors_when_not_initialized(empty_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr


def test_pick_errors_on_glob_collision(practice_repo):
    """Two solution files in the folder → can't disambiguate."""
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=60)
    folder = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    (folder / 'solution.py').write_text('extra')
    result = _run(practice_repo, '1')
    assert result.returncode == 1
    assert 'could not find a single solution file' in result.stderr


def test_pick_does_not_mutate_db(practice_repo):
    """pick_problem is read-only: no new attempt opened, no file rewritten."""
    _set_cooldown(practice_repo, 0)
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', closed_offset_sec=86400,
                  body='ORIGINAL')
    _run(practice_repo)

    # Solution file untouched.
    assert (practice_repo / 'src/Easy/1.Two_Sum/solution.ts').read_text() == 'ORIGINAL'
    # No new in-progress attempt.
    import db
    conn = db.open_db()
    assert db.latest_open_attempt(conn, 1) is None
    conn.close()
