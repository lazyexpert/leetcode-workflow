"""
Subprocess tests for scripts/import_repo/bulk_seed.py.

Tests build a fixture manifest pointing at solution files in a tmp
"source" dir, run bulk_seed inside a fresh practice repo (with
migration 0001 applied so the `imported` column exists), and assert:
  * problems / attempts / patterns rows land correctly
  * solution files copied to canonical paths
  * READMEs written from manifest statements
  * five MD views regenerated, .sql dump written
  * preconditions enforced (not initialised, populated DB)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import PLUGIN_ROOT, script_env

SCRIPT     = PLUGIN_ROOT / 'scripts' / 'import_repo' / 'bulk_seed.py'
MIGRATIONS = PLUGIN_ROOT / 'migrations'


def _apply_migration(repo: Path):
    import db
    import migrate
    conn = db.open_db()
    try:
        migrate.apply_pending(conn, migrations_dir=MIGRATIONS)
    finally:
        conn.close()


def _run(repo: Path, manifest: dict):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(manifest),
        capture_output=True, text=True,
    )


def _make_source_solution(tmp_path: Path, name: str, body: str) -> Path:
    src = tmp_path / 'src' / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body)
    return src


def _problem(**over):
    base = {
        'number':           1,
        'title':            'Two Sum',
        'difficulty':       'Easy',
        'type':             'algorithmic',
        'statement':        'Given an array of integers...',
        'started_at':       1_521_093_780,
        'patterns':         [],
        'solution_source':  '',  # filled by tests
    }
    base.update(over)
    return base


def test_bulk_seed_happy_path(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    src = _make_source_solution(tmp_path, 'two_sum.ts',
                                'function twoSum() { return []; }\n')

    manifest = {'problems': [_problem(solution_source=str(src))]}
    result   = _run(practice_repo, manifest)
    assert result.returncode == 0, result.stderr
    assert 'imported: 1 problems' in result.stdout

    target_dir = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    assert (target_dir / 'solution.ts').read_text() == \
        'function twoSum() { return []; }\n'
    assert (target_dir / 'README.md').read_text().startswith('# 1. Two Sum')

    import db
    conn = db.open_db()
    try:
        prob = conn.execute(
            'SELECT title, difficulty, kind, folder FROM problems WHERE number = 1'
        ).fetchone()
        assert prob == ('Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
        att = conn.execute(
            'SELECT started_at, duration_minutes, revisit, imported '
            'FROM attempts WHERE problem_number = 1'
        ).fetchone()
        assert att == (1_521_093_780, None, 0, 1)
    finally:
        conn.close()

    # Views were rendered + dump was written.
    assert (practice_repo / 'progress.md').exists()
    assert (practice_repo / '.claude' / 'practice.sql').exists()


def test_bulk_seed_records_patterns(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    src = _make_source_solution(tmp_path, 'two_sum.ts', 'x\n')

    manifest = {'problems': [_problem(
        solution_source=str(src),
        patterns=['Hash Map / Hash Set', 'Two Pointers'],
    )]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 0, result.stderr

    import db
    conn = db.open_db()
    try:
        rows = sorted(r[0] for r in conn.execute(
            'SELECT pattern FROM patterns WHERE problem_number = 1'
        ))
        assert rows == ['Hash Map / Hash Set', 'Two Pointers']
    finally:
        conn.close()


def test_bulk_seed_handles_sql_problem(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    src = _make_source_solution(tmp_path, 'nth_salary.sql',
                                'SELECT MAX(salary) FROM Employee;\n')

    manifest = {'problems': [_problem(
        number=177, title='Nth Highest Salary', difficulty='', type='SQL',
        solution_source=str(src),
    )]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 0, result.stderr

    target = practice_repo / 'src' / 'SQL' / '177.Nth_Highest_Salary' / 'solution.sql'
    assert target.exists()

    import db
    conn = db.open_db()
    try:
        prob = conn.execute(
            'SELECT difficulty, kind, folder FROM problems WHERE number = 177'
        ).fetchone()
        assert prob == (None, 'sql', '177.Nth_Highest_Salary')
    finally:
        conn.close()


def test_bulk_seed_multiple_problems(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    src1 = _make_source_solution(tmp_path, 'two_sum.ts',     'a\n')
    src2 = _make_source_solution(tmp_path, 'add_two.ts',     'b\n')
    src3 = _make_source_solution(tmp_path, 'longest_sub.ts', 'c\n')

    manifest = {'problems': [
        _problem(number=1, title='Two Sum', difficulty='Easy',
                 solution_source=str(src1)),
        _problem(number=2, title='Add Two Numbers', difficulty='Medium',
                 solution_source=str(src2), started_at=1_530_000_000),
        _problem(number=3, title='Longest Substring Without Repeating Characters',
                 difficulty='Medium', solution_source=str(src3),
                 started_at=1_540_000_000),
    ]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 0, result.stderr
    assert 'imported: 3 problems' in result.stdout

    import db
    conn = db.open_db()
    try:
        n = conn.execute('SELECT COUNT(*) FROM problems').fetchone()[0]
        assert n == 3
        n_attempts = conn.execute(
            'SELECT COUNT(*) FROM attempts WHERE imported = 1'
        ).fetchone()[0]
        assert n_attempts == 3
    finally:
        conn.close()


def test_bulk_seed_refuses_when_already_populated(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    # Pre-seed a problem
    import db
    conn = db.open_db()
    db.upsert_problem(conn, 99, 'Existing', 'Easy', 'algorithmic', '99.Existing')
    conn.commit()
    conn.close()

    src = _make_source_solution(tmp_path, 'two_sum.ts', 'x\n')
    manifest = {'problems': [_problem(solution_source=str(src))]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 1
    assert 'already has' in result.stderr


def test_bulk_seed_validates_missing_source_file(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    manifest = {'problems': [_problem(
        solution_source=str(tmp_path / 'nope.ts')
    )]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 1
    assert 'solution_source does not exist' in result.stderr


def test_bulk_seed_rejects_empty_problems_list(practice_repo):
    _apply_migration(practice_repo)
    result = _run(practice_repo, {'problems': []})
    assert result.returncode == 1
    assert 'non-empty list' in result.stderr


def test_bulk_seed_rejects_invalid_difficulty(practice_repo, tmp_path):
    _apply_migration(practice_repo)
    src = _make_source_solution(tmp_path, 'two_sum.ts', 'x\n')
    manifest = {'problems': [_problem(
        difficulty='Trivial', solution_source=str(src),
    )]}
    result = _run(practice_repo, manifest)
    assert result.returncode == 1
    assert 'difficulty' in result.stderr


def test_bulk_seed_exits_one_when_not_initialised(empty_repo, tmp_path):
    """No baseline applied — bulk_seed should report 'Not a leetcode-workflow repo'."""
    src = _make_source_solution(tmp_path, 'two_sum.ts', 'x\n')
    manifest = {'problems': [_problem(solution_source=str(src))]}
    result = _run(empty_repo, manifest)
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr
