"""
Subprocess tests for scripts/new/detect_reiteration.py.
"""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'scripts' / 'new' / 'detect_reiteration.py'


def _run(repo, manifest):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(manifest), capture_output=True, text=True,
    )


def _manifest(number=1, title='Two Sum', difficulty='Easy',
              ptype='algorithmic', statement='## stub'):
    return {
        'number':     number,
        'title':      title,
        'difficulty': difficulty,
        'type':       ptype,
        'statement':  statement,
    }


def test_returns_new_when_folder_missing(practice_repo):
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['mode'] == 'new'
    assert out['manifest']['number'] == 1


def test_returns_new_when_solution_empty(practice_repo):
    d = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    d.mkdir(parents=True)
    (d / 'solution.ts').write_text('')
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['mode'] == 'new'


def test_returns_reiterate_when_solution_has_content(practice_repo):
    d = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    d.mkdir(parents=True)
    (d / 'solution.ts').write_text('let x = 1;')
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == {
        'mode':          'reiterate',
        'number':        1,
        'solution_path': 'src/Easy/1.Two_Sum/solution.ts',
        'language_name': 'typescript',
    }


def test_uses_configured_language(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'language': {'extension': 'py', 'name': 'python'},
    }))
    d = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    d.mkdir(parents=True)
    (d / 'solution.py').write_text('def two_sum(): pass')
    result = _run(practice_repo, _manifest())
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['mode'] == 'reiterate'
    assert out['solution_path'].endswith('solution.py')
    assert out['language_name'] == 'python'


def test_sql_reiteration_signaled(practice_repo):
    d = practice_repo / 'src' / 'SQL' / '177.Nth_Highest_Salary'
    d.mkdir(parents=True)
    (d / 'solution.sql').write_text('SELECT 1;')
    result = _run(practice_repo, _manifest(
        number=177, title='Nth Highest Salary', difficulty='', ptype='SQL',
    ))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['mode'] == 'reiterate'
    assert out['solution_path'].endswith('solution.sql')


def test_rejects_invalid_type(practice_repo):
    result = _run(practice_repo, _manifest(ptype='bogus'))
    assert result.returncode == 1
    assert 'invalid type' in result.stderr


def test_rejects_invalid_difficulty(practice_repo):
    result = _run(practice_repo, _manifest(difficulty='Xtra'))
    assert result.returncode == 1
    assert 'invalid difficulty' in result.stderr


def test_rejects_missing_keys(practice_repo):
    result = _run(practice_repo, {'number': 1})
    assert result.returncode == 1
    assert 'missing keys' in result.stderr


def test_rejects_malformed_json(practice_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=practice_repo, env=script_env(practice_repo),
        input='not json', capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'malformed manifest JSON' in result.stderr
