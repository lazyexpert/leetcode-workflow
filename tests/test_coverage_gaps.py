"""
Subprocess tests for skills/pick/scripts/coverage_gaps.py.
"""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'pick' / 'scripts' / 'coverage_gaps.py'


def _run(repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        capture_output=True, text=True,
    )


def _seed_problem(repo, number, difficulty, title, patterns=()):
    import db
    conn = db.open_db()
    folder = f'{number}.{title.replace(" ", "_")}'
    kind = 'sql' if difficulty is None else 'algorithmic'
    db.upsert_problem(conn, number, title, difficulty, kind, folder)
    if patterns:
        db.replace_patterns(conn, number, list(patterns))
    conn.commit()
    conn.close()


# ── shape ──────────────────────────────────────────────────────────────────

def test_empty_db_all_gaps_zero(practice_repo):
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['solved_numbers'] == []
    # Every default pattern at count 0.
    assert all(g['count'] == 0 for g in payload['gaps'])
    import db
    assert {g['pattern'] for g in payload['gaps']} == set(db.DEFAULT_PATTERNS)


def test_solved_numbers_lists_every_problem_including_sql(practice_repo):
    _seed_problem(practice_repo, 1,   'Easy',   'Two Sum')
    _seed_problem(practice_repo, 19,  'Medium', 'Remove Nth Node From End of List')
    _seed_problem(practice_repo, 177, None,     'Nth Highest Salary')
    result = _run(practice_repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['solved_numbers'] == [1, 19, 177]


# ── ordering and counts ────────────────────────────────────────────────────

def test_gaps_sorted_by_count_ascending(practice_repo):
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum',
                  patterns=['Hash Map / Hash Set'])
    _seed_problem(practice_repo, 2, 'Easy', 'Add Two Numbers',
                  patterns=['Hash Map / Hash Set'])
    _seed_problem(practice_repo, 3, 'Medium', 'LSWR',
                  patterns=['Sliding Window'])

    result = _run(practice_repo)
    payload = json.loads(result.stdout)
    counts = {g['pattern']: g['count'] for g in payload['gaps']}
    assert counts['Hash Map / Hash Set'] == 2
    assert counts['Sliding Window']      == 1
    assert counts['Two Pointers']        == 0

    # First entry should be a count-0 pattern.
    assert payload['gaps'][0]['count'] == 0
    # Last non-zero must be the 2-counter (highest in this fixture).
    nonzero = [g for g in payload['gaps'] if g['count'] > 0]
    assert nonzero[-1] == {'pattern': 'Hash Map / Hash Set', 'count': 2}


def test_zero_count_tiebreaker_is_config_render_order(practice_repo):
    """When multiple patterns share count=0, they keep their config order."""
    result = _run(practice_repo)
    payload = json.loads(result.stdout)
    zero_patterns = [g['pattern'] for g in payload['gaps'] if g['count'] == 0]
    import db
    assert zero_patterns == db.DEFAULT_PATTERNS  # full default list, in order


def test_distinct_problem_count_not_row_count(practice_repo):
    """A pattern row is per (problem, pattern). If we re-classify a problem
    with the same pattern (replace_patterns), the count must stay 1."""
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum',
                  patterns=['Hash Map / Hash Set'])
    # Re-classify (replace_patterns deletes + reinserts)
    import db
    conn = db.open_db()
    db.replace_patterns(conn, 1, ['Hash Map / Hash Set'])
    conn.commit()
    conn.close()

    result = _run(practice_repo)
    payload = json.loads(result.stdout)
    counts = {g['pattern']: g['count'] for g in payload['gaps']}
    assert counts['Hash Map / Hash Set'] == 1


# ── custom patterns config ─────────────────────────────────────────────────

def test_honors_custom_patterns_config(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'patterns': ['Foo', 'Bar', 'Baz'],
    }))
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', patterns=['Foo'])
    result = _run(practice_repo)
    payload = json.loads(result.stdout)
    assert {g['pattern'] for g in payload['gaps']} == {'Foo', 'Bar', 'Baz'}
    counts = {g['pattern']: g['count'] for g in payload['gaps']}
    assert counts == {'Foo': 1, 'Bar': 0, 'Baz': 0}


def test_patterns_outside_config_excluded_from_gaps(practice_repo):
    """If somehow a pattern not in config exists in DB (e.g. user trimmed
    config.patterns after classifying), it shouldn't surface in gaps."""
    (practice_repo / 'config.json').write_text(json.dumps({
        'patterns': ['Foo', 'Bar'],
    }))
    # Insert a stray pattern row directly.
    import db
    _seed_problem(practice_repo, 1, 'Easy', 'Two Sum', patterns=['Stray'])
    result = _run(practice_repo)
    payload = json.loads(result.stdout)
    assert {g['pattern'] for g in payload['gaps']} == {'Foo', 'Bar'}


# ── error path ─────────────────────────────────────────────────────────────

def test_errors_when_not_initialized(empty_repo):
    result = _run(empty_repo)
    assert result.returncode == 1
    assert 'Not a leetcode-workflow repo' in result.stderr
