"""
Subprocess tests for lib/apply_solution_template.py.
"""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'lib' / 'apply_solution_template.py'


def _run(repo, payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(payload), capture_output=True, text=True,
    )


def _make_problem(repo, number, section, title, ext, body):
    folder = f'{number}.{title.replace(" ", "_")}'
    d = repo / 'src' / section / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f'solution.{ext}').write_text(body)
    import db
    conn = db.open_db()
    difficulty = None if section == 'SQL' else section
    kind = 'sql' if section == 'SQL' else 'algorithmic'
    db.upsert_problem(conn, number, title, difficulty, kind, folder)
    conn.commit()
    conn.close()
    return d / f'solution.{ext}'


def test_apply_writes_body_and_opens_attempt(practice_repo):
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts',
                          body='function twoSum() { return [0, 1]; }')
    result = _run(practice_repo, {'number': 1, 'body_text': 'function twoSum() {}'})
    assert result.returncode == 0, result.stderr
    assert 'retry: cleared src/Easy/1.Two_Sum/solution.ts' in result.stdout
    assert sfile.read_text() == 'function twoSum() {}'

    import db
    conn = db.open_db()
    open_row = db.latest_open_attempt(conn, 1)
    assert open_row is not None
    conn.close()


def test_apply_empty_body_wipes(practice_repo):
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='whatever')
    result = _run(practice_repo, {'number': 1, 'body_text': ''})
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == ''


def test_apply_sql_no_attempt(practice_repo):
    sfile = _make_problem(practice_repo, 177, 'SQL', 'Nth Highest Salary', 'sql',
                          body='SELECT 1;')
    result = _run(practice_repo, {'number': 177, 'body_text': ''})
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == ''

    import db
    conn = db.open_db()
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 177'))
    assert rows == []
    conn.close()


def test_apply_unknown_problem_errors(practice_repo):
    result = _run(practice_repo, {'number': 999, 'body_text': ''})
    assert result.returncode == 1
    assert 'problem 999 not found' in result.stderr


def test_apply_dumps_sql(practice_repo):
    _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='x')
    _run(practice_repo, {'number': 1, 'body_text': ''})
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'Two Sum' in sql


def test_apply_rejects_malformed_input(practice_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=practice_repo, env=script_env(practice_repo),
        input='{not valid json', capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'malformed input JSON' in result.stderr


def test_apply_rejects_non_int_number(practice_repo):
    result = _run(practice_repo, {'number': 'one', 'body_text': ''})
    assert result.returncode == 1
    assert '"number" must be int' in result.stderr


def test_apply_renders_views(practice_repo):
    _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='x')
    _run(practice_repo, {'number': 1, 'body_text': ''})
    progress = (practice_repo / 'progress.md').read_text()
    assert 'Two Sum' in progress
