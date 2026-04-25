"""
Subprocess tests for skills/new/scripts/scaffold_new.py.
"""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'new' / 'scripts' / 'scaffold_new.py'


def _run(repo, manifest):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(manifest), capture_output=True, text=True,
    )


def _manifest(**over):
    base = {
        'number':     1,
        'title':      'Two Sum',
        'difficulty': 'Easy',
        'type':       'algorithmic',
        'statement':  'Given an array...\n',
    }
    base.update(over)
    return base


def test_scaffold_new_creates_folder_and_records_problem(practice_repo):
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    assert 'scaffold: created src/Easy/1.Two_Sum' in result.stdout

    folder = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    assert (folder / 'README.md').exists()
    assert (folder / 'README.md').read_text().startswith('# 1. Two Sum')
    assert (folder / 'solution.ts').exists()
    assert (folder / 'solution.ts').stat().st_size == 0

    import db
    conn = db.open_db()
    row = conn.execute(
        'SELECT title, difficulty, kind, folder FROM problems WHERE number = 1'
    ).fetchone()
    assert row == ('Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    open_attempt = db.latest_open_attempt(conn, 1)
    assert open_attempt is not None
    conn.close()


def test_scaffold_new_sql_uses_sql_section_no_attempt(practice_repo):
    result = _run(practice_repo, _manifest(
        number=177, title='Nth Highest Salary', difficulty='', type='SQL',
    ))
    assert result.returncode == 0, result.stderr
    folder = practice_repo / 'src' / 'SQL' / '177.Nth_Highest_Salary'
    assert (folder / 'solution.sql').exists()

    import db
    conn = db.open_db()
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 177'))
    assert rows == []
    conn.close()


def test_scaffold_new_honors_configured_language(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'language': {'extension': 'py', 'name': 'python'},
    }))
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    assert (practice_repo / 'src' / 'Easy' / '1.Two_Sum' / 'solution.py').exists()
    assert not (practice_repo / 'src' / 'Easy' / '1.Two_Sum' / 'solution.ts').exists()


def test_scaffold_new_refuses_non_empty_solution(practice_repo):
    folder = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    folder.mkdir(parents=True)
    (folder / 'solution.ts').write_text('let x = 1;')
    result = _run(practice_repo, _manifest())
    assert result.returncode == 1
    assert 'already has content' in result.stderr


def test_scaffold_new_renders_views_and_dumps(practice_repo):
    _run(practice_repo, _manifest())
    progress = (practice_repo / 'progress.md').read_text()
    assert '1. Two Sum' in progress
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'Two Sum' in sql


def test_scaffold_new_rejects_invalid_type(practice_repo):
    result = _run(practice_repo, _manifest(type='bogus'))
    assert result.returncode == 1
    assert 'invalid type' in result.stderr


def test_scaffold_new_rejects_invalid_difficulty(practice_repo):
    result = _run(practice_repo, _manifest(difficulty='Xtra'))
    assert result.returncode == 1
    assert 'invalid difficulty' in result.stderr


def test_scaffold_new_rejects_missing_keys(practice_repo):
    result = _run(practice_repo, {'number': 1, 'title': 't', 'type': 'algorithmic'})
    assert result.returncode == 1
    assert 'missing keys' in result.stderr


def test_scaffold_new_errors_when_not_initialized(empty_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        input=json.dumps(_manifest()), capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert 'Not a leetcode-workflow repo' in result.stderr
