"""
Subprocess tests for lib/apply_solution_template.py.

The script reads its inputs as command-line flags (--number,
--body-file). The body file is read verbatim — preserves any bytes,
including multi-line code, quotes, backslashes, etc.
"""
from __future__ import annotations

import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'lib' / 'apply_solution_template.py'


def _run(repo, *, number, body_path):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', str(number), '--body-file', str(body_path)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
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


def test_apply_writes_body_and_opens_attempt(practice_repo, tmp_path):
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts',
                          body='function twoSum() { return [0, 1]; }')
    body_file = tmp_path / 'body.txt'
    body_file.write_text('function twoSum() {}')

    result = _run(practice_repo, number=1, body_path=body_file)
    assert result.returncode == 0, result.stderr
    assert 'retry: cleared src/Easy/1.Two_Sum/solution.ts' in result.stdout
    assert sfile.read_text() == 'function twoSum() {}'

    import db
    conn = db.open_db()
    assert db.latest_open_attempt(conn, 1) is not None
    conn.close()


def test_apply_empty_body_wipes(practice_repo, tmp_path):
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='whatever')
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    result = _run(practice_repo, number=1, body_path=body_file)
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == ''


def test_apply_preserves_multiline_body(practice_repo, tmp_path):
    """Body content with newlines, quotes, backslashes — must round-trip
    exactly. This is the whole point of file-based input over JSON-on-stdin."""
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='old')
    body = (
        'function twoSum(nums: number[], target: number): number[] {\n'
        '    // body stripped\n'
        '    const map = new Map<number, number>();\n'
        '    return [];\n'
        '}\n'
    )
    body_file = tmp_path / 'body.txt'
    body_file.write_text(body)

    result = _run(practice_repo, number=1, body_path=body_file)
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == body


def test_apply_preserves_special_chars(practice_repo, tmp_path):
    """Quotes, backslashes, control chars in source. Common in TS/JS templates."""
    sfile = _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='old')
    body = 'const s = "hello\\nworld\\t\'quoted\'";\nreturn s;\n'
    body_file = tmp_path / 'body.txt'
    body_file.write_text(body)

    result = _run(practice_repo, number=1, body_path=body_file)
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == body


def test_apply_sql_no_attempt(practice_repo, tmp_path):
    sfile = _make_problem(practice_repo, 177, 'SQL', 'Nth Highest Salary', 'sql',
                          body='SELECT 1;')
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    result = _run(practice_repo, number=177, body_path=body_file)
    assert result.returncode == 0, result.stderr
    assert sfile.read_text() == ''

    import db
    conn = db.open_db()
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 177'))
    assert rows == []
    conn.close()


def test_apply_unknown_problem_errors(practice_repo, tmp_path):
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    result = _run(practice_repo, number=999, body_path=body_file)
    assert result.returncode == 1
    assert 'problem 999 not found' in result.stderr


def test_apply_dumps_sql(practice_repo, tmp_path):
    _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='x')
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    _run(practice_repo, number=1, body_path=body_file)
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'Two Sum' in sql


def test_apply_missing_body_file_errors(practice_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', '1', '--body-file', '/nonexistent/path.txt'],
        cwd=practice_repo, env=script_env(practice_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'body file not found' in result.stderr


def test_apply_renders_views(practice_repo, tmp_path):
    _make_problem(practice_repo, 1, 'Easy', 'Two Sum', 'ts', body='x')
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    _run(practice_repo, number=1, body_path=body_file)
    progress = (practice_repo / 'progress.md').read_text()
    assert 'Two Sum' in progress


def test_apply_requires_both_flags(practice_repo, tmp_path):
    body_file = tmp_path / 'body.txt'
    body_file.write_text('')

    # Missing --body-file
    r = subprocess.run(
        [sys.executable, str(SCRIPT), '--number', '1'],
        cwd=practice_repo, env=script_env(practice_repo),
        capture_output=True, text=True,
    )
    assert r.returncode != 0

    # Missing --number
    r = subprocess.run(
        [sys.executable, str(SCRIPT), '--body-file', str(body_file)],
        cwd=practice_repo, env=script_env(practice_repo),
        capture_output=True, text=True,
    )
    assert r.returncode != 0
