"""
Unit tests for lib/render.py.

The renderers are pure functions of (Connection, repo paths). Tests build
small fixture DBs in the practice_repo and assert on the returned strings
or written files.
"""
from __future__ import annotations

import datetime

import db
import render

# ── helpers ─────────────────────────────────────────────────────────────────

def _ts(year: int, month: int, day: int) -> int:
    return int(datetime.datetime(year, month, day, 12, 0, 0,
                                 tzinfo=datetime.timezone.utc).timestamp())


def _seed_simple(conn):
    """Two algorithmic problems and one SQL problem, all with closed attempts."""
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.upsert_problem(conn, 3, 'Longest Substring Without Repeating Characters',
                      'Medium', 'algorithmic',
                      '3.Longest_Substring_Without_Repeating_Characters')
    db.upsert_problem(conn, 177, 'Nth Highest Salary', None, 'sql',
                      '177.Nth_Highest_Salary')
    db.upsert_thresholds(conn, {'Easy': 15, 'Medium': 30, 'Hard': 60})

    # Closed algorithmic attempts.
    started_1 = _ts(2026, 1, 5)
    conn.execute('INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit) '
                 'VALUES (?, ?, ?, ?)', (1, started_1, 8, 0))
    started_3 = _ts(2026, 2, 10)
    conn.execute('INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit) '
                 'VALUES (?, ?, ?, ?)', (3, started_3, 45, 1))  # over threshold + revisit

    # SQL attempt
    started_sql = _ts(2026, 2, 12)
    conn.execute('INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit) '
                 'VALUES (?, ?, ?, ?)', (177, started_sql, 5, 0))

    db.replace_patterns(conn, 1, ['Hash Map / Hash Set', 'Two Pointers'])
    db.replace_patterns(conn, 3, ['Sliding Window'])


# ── progress.md ─────────────────────────────────────────────────────────────

def test_render_progress_empty(practice_repo):
    conn = db.open_db()
    out = render.render_progress(conn)
    assert out.startswith('# Progress')
    assert '| Easy       | 0      |' in out
    assert '| **Total**  | **0** |' in out
    # Sections are present even when empty.
    assert '## Easy' in out
    assert '## SQL' in out
    conn.close()


def test_render_progress_with_problems(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    out = render.render_progress(conn)
    assert '| Easy       | 1      |' in out
    assert '| Medium     | 1      |' in out
    assert '| SQL        | 1      |' in out
    assert '| **Total**  | **3** |' in out
    assert '- [1. Two Sum](src/Easy/1.Two_Sum)' in out
    assert ('- [3. Longest Substring Without Repeating Characters]'
            '(src/Medium/3.Longest_Substring_Without_Repeating_Characters)') in out
    assert '- [177. Nth Highest Salary](src/SQL/177.Nth_Highest_Salary)' in out
    conn.close()


# ── timings.md ──────────────────────────────────────────────────────────────

def test_render_timings_empty(practice_repo):
    conn = db.open_db()
    db.upsert_thresholds(conn, {'Easy': 15, 'Medium': 30, 'Hard': 60})
    out = render.render_timings(conn)
    assert 'Easy ≥ 15 min · Medium ≥ 30 min · Hard ≥ 60 min' in out
    # Header table present, no body rows.
    assert '| # | Problem | Difficulty | Date | Minutes |' in out
    body_after_header = out.split('|---|---------|------------|------|---------|')[1]
    assert body_after_header.strip() == ''
    conn.close()


def test_render_timings_with_attempts_excludes_sql_and_in_progress(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    # In-progress attempt for 1 should NOT show up.
    db.start_attempt(conn, 1)
    out = render.render_timings(conn)
    assert '| 1 | [Two Sum]' in out
    assert '| 3 | [Longest Substring' in out
    assert '177' not in out  # SQL excluded
    # Date format
    assert '2026-01-05' in out
    assert '2026-02-10' in out
    conn.close()


# ── retry.md ────────────────────────────────────────────────────────────────

def test_render_retry_empty(practice_repo):
    conn = db.open_db()
    out = render.render_retry(conn)
    assert out.startswith('# Retry List')
    body_after_header = out.split('|------------|---|---------|------------|--------|')[1]
    assert body_after_header.strip() == ''
    conn.close()


def test_render_retry_joins_flags_with_plus(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    # Force `stale = 1` for problem 3 by setting cooldown to 0 days.
    db.upsert_setting(conn, 'review_cooldown_days', 0)
    out = render.render_retry(conn)
    # Problem 3 has timing_bad (45 ≥ 30), complexity_bad (revisit=1), stale (cooldown=0)
    assert 'timing+complexity+stale' in out
    # Problem 1: 8 min < 15 min, no revisit, but stale=1 → just 'stale'
    assert '| 1 | [Two Sum]' in out
    conn.close()


# ── patterns-coverage.md ────────────────────────────────────────────────────

def test_render_patterns_empty(practice_repo):
    conn = db.open_db()
    out = render.render_patterns(conn)
    assert out == '# Pattern Coverage\n'
    conn.close()


def test_render_patterns_uses_config_order(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    out = render.render_patterns(conn)
    # Default render order: Two Pointers, Sliding Window, ..., Hash Map / Hash Set
    # Confirm Two Pointers appears before Sliding Window before Hash Map.
    tp_idx = out.index('## Two Pointers')
    sw_idx = out.index('## Sliding Window')
    hm_idx = out.index('## Hash Map / Hash Set')
    assert tp_idx < sw_idx < hm_idx
    # Each pattern lists its problems
    assert '- [1. Two Sum](src/Easy/1.Two_Sum)' in out
    conn.close()


def test_render_patterns_skips_unused(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    out = render.render_patterns(conn)
    # 'Backtracking' is in DEFAULT_PATTERNS but has no rows -> no header.
    assert '## Backtracking' not in out
    conn.close()


# ── history.md ──────────────────────────────────────────────────────────────

def test_render_history_groups_by_month_newest_first(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    out = render.render_history(conn)
    feb_idx = out.index('## February 2026')
    jan_idx = out.index('## January 2026')
    assert feb_idx < jan_idx  # newest first
    # Algorithmic line for Jan
    assert '[1](src/Easy/1.Two_Sum)' in out
    # SQL line for Feb
    assert 'SQL: [177](src/SQL/177.Nth_Highest_Salary)' in out
    conn.close()


def test_render_history_skips_problems_without_attempts(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    out = render.render_history(conn)
    assert out.strip() == '# History'
    conn.close()


# ── render_all ──────────────────────────────────────────────────────────────

def test_render_all_writes_five_files(practice_repo):
    conn = db.open_db()
    _seed_simple(conn)
    render.render_all(conn, practice_repo)
    for name in ('progress.md', 'timings.md', 'retry.md',
                 'patterns-coverage.md', 'history.md'):
        path = practice_repo / name
        assert path.exists(), f'{name} missing'
        assert path.stat().st_size > 0
    conn.close()
