"""
Subprocess tests for scripts/done/record_attempt.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest
from conftest import PLUGIN_ROOT, script_env

SCRIPT = PLUGIN_ROOT / 'scripts' / 'done' / 'record_attempt.py'


def _run(repo, payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(payload), capture_output=True, text=True,
    )


def _open(repo):
    import db
    return db.open_db()


def _start_attempt_for(repo, number, started_at_offset=0):
    """Open an in-progress attempt with started_at = now - offset seconds."""
    import db
    conn = db.open_db()
    db.upsert_problem(conn, number, 'placeholder', 'Easy', 'algorithmic', f'{number}.placeholder')
    aid = db.start_attempt(conn, number)
    if started_at_offset:
        conn.execute('UPDATE attempts SET started_at = ? WHERE id = ?',
                     (int(time.time()) - started_at_offset, aid))
    conn.commit()
    conn.close()
    return aid


def test_record_algorithmic_closes_attempt_within_threshold(practice_repo):
    _start_attempt_for(practice_repo, 1, started_at_offset=300)  # 5 min ago
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
        'classification': {'patterns': ['Hash Map / Hash Set'], 'revisit': False},
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr
    assert '✓ timing' in result.stdout
    assert 'within Easy threshold' in result.stdout
    assert '✓ patterns:   Hash Map / Hash Set' in result.stdout
    assert '✓ complexity: optimal' in result.stdout

    conn = _open(practice_repo)
    row = conn.execute('SELECT duration_minutes, revisit FROM attempts WHERE problem_number = 1').fetchone()
    assert row[0] == 5
    assert row[1] == 0
    patterns = [r[0] for r in conn.execute('SELECT pattern FROM patterns WHERE problem_number = 1')]
    assert patterns == ['Hash Map / Hash Set']
    conn.close()


def test_record_algorithmic_over_threshold_warns(practice_repo):
    _start_attempt_for(practice_repo, 1, started_at_offset=20 * 60)  # 20 min ago, default Easy=15
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
        'classification': {'patterns': ['Hash Map / Hash Set'], 'revisit': True},
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr
    assert '⚠ timing' in result.stdout
    assert 'over Easy threshold' in result.stdout
    assert '⚠ complexity: classifier flagged a better solution exists' in result.stdout


def test_record_algorithmic_filters_unknown_patterns(practice_repo):
    _start_attempt_for(practice_repo, 1, started_at_offset=60)
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
        'classification': {'patterns': ['Hash Map / Hash Set', 'Made Up Pattern'], 'revisit': False},
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr
    assert 'unknown patterns' in result.stdout
    assert "Made Up Pattern" in result.stdout

    import db
    conn = db.open_db()
    rows = [r[0] for r in conn.execute('SELECT pattern FROM patterns WHERE problem_number = 1')]
    assert rows == ['Hash Map / Hash Set']
    conn.close()


def test_record_algorithmic_no_open_attempt_recovers(practice_repo):
    """Edited a solution file without running /new first — script opens
    and closes a fresh attempt, recording min duration."""
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
        'classification': {'patterns': ['Hash Map / Hash Set'], 'revisit': False},
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr
    assert '⚠ no in-progress attempt' in result.stdout

    import db
    conn = db.open_db()
    row = conn.execute('SELECT duration_minutes FROM attempts WHERE problem_number = 1').fetchone()
    assert row[0] == 1  # min duration
    conn.close()


def test_record_sql_does_not_open_attempt(practice_repo):
    payload = {
        'number': 177, 'title': 'Nth Highest Salary', 'difficulty': None,
        'path': 'src/SQL/177.Nth_Highest_Salary/solution.sql', 'kind': 'sql',
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr

    import db
    conn = db.open_db()
    row = conn.execute('SELECT title, kind FROM problems WHERE number = 177').fetchone()
    assert row == ('Nth Highest Salary', 'sql')
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 177'))
    assert rows == []
    conn.close()


def test_record_skipped_classification_recorded_as_no_patterns(practice_repo):
    """If the model couldn't classify (offline, parse error etc.), SKILL.md
    omits classification. Attempt still closes; no patterns recorded."""
    _start_attempt_for(practice_repo, 1, started_at_offset=60)
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
    }
    result = _run(practice_repo, payload)
    assert result.returncode == 0, result.stderr

    import db
    conn = db.open_db()
    row = conn.execute('SELECT duration_minutes FROM attempts WHERE problem_number = 1').fetchone()
    assert row[0] == 1
    rows = list(conn.execute('SELECT pattern FROM patterns WHERE problem_number = 1'))
    assert rows == []
    conn.close()


def test_record_dumps_sql(practice_repo):
    _start_attempt_for(practice_repo, 1, started_at_offset=60)
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
        'classification': {'patterns': [], 'revisit': False},
    }
    _run(practice_repo, payload)
    sql = (practice_repo / '.claude' / 'practice.sql').read_text()
    assert 'Two Sum' in sql


@pytest.mark.parametrize('payload,err_match', [
    ({}, 'missing keys'),
    ({'number': 1, 'title': 't', 'difficulty': 'Easy', 'path': 'x', 'kind': 'bogus'}, 'invalid kind'),
    ({'number': 1, 'title': 't', 'difficulty': None, 'path': 'x', 'kind': 'algorithmic'},
     'algorithmic problem requires Easy'),
])
def test_record_rejects_malformed_payload(practice_repo, payload, err_match):
    result = _run(practice_repo, payload)
    assert result.returncode == 1
    assert err_match in result.stderr


def test_record_errors_when_not_initialized(empty_repo):
    payload = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'path': 'src/Easy/1.Two_Sum/solution.ts', 'kind': 'algorithmic',
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        input=json.dumps(payload), capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr
