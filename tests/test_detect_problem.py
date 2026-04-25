"""
Subprocess tests for skills/done/scripts/detect_problem.py.

The script needs git visibility into the working tree, so all tests use
the git_repo fixture (practice_repo + git init).
"""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'done' / 'scripts' / 'detect_problem.py'


def _run(repo, **kw):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
        **kw,
    )


def _make_solution(repo, section, folder, fname, body='let x = 1;'):
    d = repo / 'src' / section / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(body)


def test_detect_finds_single_algorithmic_solution(git_repo):
    _make_solution(git_repo, 'Easy', '1.Two_Sum', 'solution.ts')
    result = _run(git_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        'number':     1,
        'title':      'Two Sum',
        'difficulty': 'Easy',
        'path':       'src/Easy/1.Two_Sum/solution.ts',
        'kind':       'algorithmic',
    }


def test_detect_finds_sql_solution(git_repo):
    _make_solution(git_repo, 'SQL', '177.Nth_Highest_Salary', 'solution.sql', body='SELECT 1;')
    result = _run(git_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['kind'] == 'sql'
    assert payload['difficulty'] is None
    assert payload['number'] == 177


def test_detect_ignores_empty_solution_file(git_repo):
    _make_solution(git_repo, 'Easy', '1.Two_Sum', 'solution.ts', body='')
    result = _run(git_repo)
    assert result.returncode == 1
    assert 'no problem detected' in result.stderr


def test_detect_ignores_wrong_extension(git_repo):
    # Default ext is 'ts'; a .py file should not match.
    _make_solution(git_repo, 'Easy', '1.Two_Sum', 'solution.py')
    result = _run(git_repo)
    assert result.returncode == 1


def test_detect_honors_config_extension(git_repo):
    (git_repo / 'config.json').write_text(json.dumps({
        'language': {'extension': 'py', 'name': 'python'},
    }))
    _make_solution(git_repo, 'Easy', '1.Two_Sum', 'solution.py')
    result = _run(git_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['path'].endswith('solution.py')


def test_detect_errors_on_multiple_candidates(git_repo):
    _make_solution(git_repo, 'Easy', '1.Two_Sum', 'solution.ts')
    _make_solution(git_repo, 'Medium', '3.Longest_Substring', 'solution.ts')
    result = _run(git_repo)
    assert result.returncode == 1
    assert 'multiple solution files have changes' in result.stderr


def test_detect_errors_when_no_changes(git_repo):
    result = _run(git_repo)
    assert result.returncode == 1
    assert 'no problem detected' in result.stderr


def test_detect_errors_when_not_initialized(empty_repo):
    """No .claude/ — script bails before touching git."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr
