"""
Unit tests for lib/db.py.

Every test pulls a fresh practice repo from the `practice_repo` fixture
(tmp dir with the v0 baseline applied) and exercises one helper.
"""
from __future__ import annotations

import json
import time

import db
import pytest

# ── config loaders ──────────────────────────────────────────────────────────

def test_load_thresholds_defaults(practice_repo):
    assert db.load_thresholds() == {'Easy': 15, 'Medium': 30, 'Hard': 60}


def test_load_thresholds_overrides(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'retry_thresholds_minutes': {'Easy': 10, 'Medium': 25, 'Hard': 50},
    }))
    assert db.load_thresholds() == {'Easy': 10, 'Medium': 25, 'Hard': 50}


def test_load_thresholds_partial_override_merges_with_defaults(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'retry_thresholds_minutes': {'Easy': 5},
    }))
    assert db.load_thresholds() == {'Easy': 5, 'Medium': 30, 'Hard': 60}


def test_load_language_defaults(practice_repo):
    assert db.load_language() == {'extension': 'ts', 'name': 'typescript'}


def test_load_language_overrides_normalises(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'language': {'extension': '.PY', 'name': 'Python'},
    }))
    assert db.load_language() == {'extension': 'py', 'name': 'python'}


def test_load_cooldown_days_default(practice_repo):
    assert db.load_cooldown_days() == 7


def test_load_cooldown_days_override(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'review_cooldown_days': 14,
    }))
    assert db.load_cooldown_days() == 14


def test_load_cooldown_days_negative_clamps_to_zero(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'review_cooldown_days': -3,
    }))
    assert db.load_cooldown_days() == 0


def test_load_cooldown_days_garbage_falls_back_to_default(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'review_cooldown_days': 'lots',
    }))
    assert db.load_cooldown_days() == 7


def test_load_pick_retry_ratio_default(practice_repo):
    assert db.load_pick_retry_ratio() == 0.0


def test_load_pick_retry_ratio_clamps(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({'pick_retry_ratio': 1.5}))
    assert db.load_pick_retry_ratio() == 1.0
    (practice_repo / 'config.json').write_text(json.dumps({'pick_retry_ratio': -0.2}))
    assert db.load_pick_retry_ratio() == 0.0


def test_load_pick_retry_ratio_garbage_falls_back(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({'pick_retry_ratio': 'half'}))
    assert db.load_pick_retry_ratio() == 0.0


def test_load_patterns_defaults(practice_repo):
    patterns = db.load_patterns()
    assert len(patterns) == 18
    assert 'Two Pointers' in patterns
    assert patterns[0] == 'Two Pointers'  # render order


def test_load_patterns_custom_dedupes_and_strips(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'patterns': ['  Foo  ', 'Bar', 'Foo', '', 'Baz'],
    }))
    assert db.load_patterns() == ['Foo', 'Bar', 'Baz']


def test_load_patterns_malformed_falls_back(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({'patterns': 'nope'}))
    assert db.load_patterns() == db.DEFAULT_PATTERNS


def test_malformed_config_warns_and_falls_back(practice_repo, capsys):
    (practice_repo / 'config.json').write_text('{not valid json')
    assert db.load_thresholds() == {'Easy': 15, 'Medium': 30, 'Hard': 60}
    err = capsys.readouterr().err
    assert 'malformed' in err


# ── open_db ─────────────────────────────────────────────────────────────────

def test_open_db_returns_working_connection(practice_repo):
    conn = db.open_db()
    try:
        # practice_repo applies baseline + all shipped migrations; the
        # current latest is 2.
        assert conn.execute('SELECT value FROM settings WHERE key = ?', ('schema_version',)).fetchone() == ('2',)
    finally:
        conn.close()


def test_open_db_rebuilds_from_sql_when_db_missing(practice_repo):
    # Seed the dump first.
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.dump_sql(conn)
    conn.close()

    # Nuke the .db; .sql remains.
    db.DB_PATH.unlink()
    assert not db.DB_PATH.exists()
    assert db.SQL_DUMP.exists()

    conn = db.open_db()
    try:
        row = conn.execute('SELECT title FROM problems WHERE number = 1').fetchone()
        assert row == ('Two Sum',)
    finally:
        conn.close()


def test_open_db_raises_when_uninitialized(empty_repo):
    with pytest.raises(db.NotInitialized):
        db.open_db()


# ── problems ────────────────────────────────────────────────────────────────

def test_upsert_problem_inserts(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    row = conn.execute(
        'SELECT number, title, difficulty, kind, folder FROM problems WHERE number = 1'
    ).fetchone()
    assert row == (1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    conn.close()


def test_upsert_problem_conflict_updates_metadata_keeps_created_at(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    original_created = conn.execute(
        'SELECT created_at FROM problems WHERE number = 1'
    ).fetchone()[0]

    # Force a different timestamp on the second call.
    time.sleep(1.05)
    db.upsert_problem(conn, 1, 'Two Sum II', 'Medium', 'algorithmic', '1.Two_Sum_II')
    row = conn.execute(
        'SELECT title, difficulty, folder, created_at FROM problems WHERE number = 1'
    ).fetchone()
    assert row[0:3] == ('Two Sum II', 'Medium', '1.Two_Sum_II')
    assert row[3] == original_created  # created_at preserved
    conn.close()


# ── attempts ────────────────────────────────────────────────────────────────

def test_start_attempt_opens_in_progress_row(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    aid = db.start_attempt(conn, 1)
    row = conn.execute(
        'SELECT problem_number, duration_minutes, revisit FROM attempts WHERE id = ?',
        (aid,),
    ).fetchone()
    assert row == (1, None, 0)
    conn.close()


def test_start_attempt_collision_bumps_started_at(practice_repo):
    """Two attempts opened in the same wall-clock second must both succeed."""
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    a1 = db.start_attempt(conn, 1)
    a2 = db.start_attempt(conn, 1)
    assert a1 != a2
    rows = conn.execute(
        'SELECT id, started_at FROM attempts WHERE problem_number = 1 ORDER BY started_at'
    ).fetchall()
    assert len(rows) == 2
    assert rows[1][1] == rows[0][1] + 1  # bumped by 1 second
    conn.close()


def test_latest_open_attempt_returns_most_recent(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.start_attempt(conn, 1)
    a2 = db.start_attempt(conn, 1)  # newer
    row = db.latest_open_attempt(conn, 1)
    assert row is not None
    assert row[0] == a2
    conn.close()


def test_latest_open_attempt_skips_closed(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    a1 = db.start_attempt(conn, 1)
    db.complete_attempt(conn, a1, revisit=False)
    assert db.latest_open_attempt(conn, 1) is None
    conn.close()


def test_complete_attempt_sets_duration_and_revisit(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    aid = db.start_attempt(conn, 1)
    # Backdate so duration is non-trivial.
    conn.execute('UPDATE attempts SET started_at = ? WHERE id = ?',
                 (int(time.time()) - 600, aid))
    duration = db.complete_attempt(conn, aid, revisit=True)
    assert 9 <= duration <= 11  # ~10 minutes, allow rounding
    row = conn.execute('SELECT duration_minutes, revisit FROM attempts WHERE id = ?',
                       (aid,)).fetchone()
    assert row == (duration, 1)
    conn.close()


def test_complete_attempt_min_one_minute(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    aid = db.start_attempt(conn, 1)
    duration = db.complete_attempt(conn, aid, revisit=False)
    assert duration == 1
    conn.close()


def test_complete_attempt_unknown_id_raises(practice_repo):
    conn = db.open_db()
    with pytest.raises(ValueError, match='attempt 999 not found'):
        db.complete_attempt(conn, 999, revisit=False)
    conn.close()


# ── patterns ────────────────────────────────────────────────────────────────

def test_replace_patterns_writes_rows(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.replace_patterns(conn, 1, ['Hash Map / Hash Set', 'Two Pointers'])
    rows = sorted(r[0] for r in conn.execute(
        'SELECT pattern FROM patterns WHERE problem_number = 1'
    ))
    assert rows == ['Hash Map / Hash Set', 'Two Pointers']
    conn.close()


def test_replace_patterns_clears_when_empty(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.replace_patterns(conn, 1, ['Hash Map / Hash Set'])
    db.replace_patterns(conn, 1, [])
    rows = list(conn.execute('SELECT pattern FROM patterns WHERE problem_number = 1'))
    assert rows == []
    conn.close()


def test_replace_patterns_replaces_not_appends(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.replace_patterns(conn, 1, ['Two Pointers'])
    db.replace_patterns(conn, 1, ['Hash Map / Hash Set'])
    rows = [r[0] for r in conn.execute(
        'SELECT pattern FROM patterns WHERE problem_number = 1'
    )]
    assert rows == ['Hash Map / Hash Set']
    conn.close()


# ── thresholds / settings / sync_config ─────────────────────────────────────

def test_upsert_thresholds_inserts_then_updates(practice_repo):
    conn = db.open_db()
    db.upsert_thresholds(conn, {'Easy': 15})
    assert conn.execute('SELECT minutes FROM thresholds WHERE difficulty = ?',
                        ('Easy',)).fetchone() == (15,)
    db.upsert_thresholds(conn, {'Easy': 10})
    assert conn.execute('SELECT minutes FROM thresholds WHERE difficulty = ?',
                        ('Easy',)).fetchone() == (10,)
    conn.close()


def test_upsert_setting_inserts_then_updates(practice_repo):
    conn = db.open_db()
    db.upsert_setting(conn, 'foo', 'bar')
    db.upsert_setting(conn, 'foo', 'baz')
    assert conn.execute('SELECT value FROM settings WHERE key = ?', ('foo',)).fetchone() == ('baz',)
    conn.close()


def test_sync_config_mirrors_thresholds_and_cooldown(practice_repo):
    (practice_repo / 'config.json').write_text(json.dumps({
        'retry_thresholds_minutes': {'Easy': 12, 'Medium': 33, 'Hard': 55},
        'review_cooldown_days': 21,
    }))
    conn = db.open_db()
    db.sync_config(conn)
    rows = dict(conn.execute('SELECT difficulty, minutes FROM thresholds'))
    assert rows == {'Easy': 12, 'Medium': 33, 'Hard': 55}
    cooldown = conn.execute('SELECT value FROM settings WHERE key = ?',
                            ('review_cooldown_days',)).fetchone()
    assert cooldown == ('21',)
    conn.close()


# ── prepare_retry ───────────────────────────────────────────────────────────

def _make_problem_folder(repo, section, folder, fname, body=''):
    d = repo / 'src' / section / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(body)
    return d / fname


def test_prepare_retry_algorithmic_writes_body_and_opens_attempt(practice_repo):
    sfile = _make_problem_folder(
        practice_repo, 'Easy', '1.Two_Sum', 'solution.ts',
        body='function twoSum() { return [0, 1]; }',
    )
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')

    returned = db.prepare_retry(conn, 1, body_text='function twoSum() {}')

    assert returned == sfile
    assert sfile.read_text() == 'function twoSum() {}'
    open_row = db.latest_open_attempt(conn, 1)
    assert open_row is not None  # new attempt was opened
    conn.close()


def test_prepare_retry_algorithmic_empty_body_wipes(practice_repo):
    sfile = _make_problem_folder(
        practice_repo, 'Easy', '1.Two_Sum', 'solution.ts', body='whatever',
    )
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.prepare_retry(conn, 1, body_text='')
    assert sfile.read_text() == ''
    conn.close()


def test_prepare_retry_sql_does_not_open_attempt(practice_repo):
    sfile = _make_problem_folder(
        practice_repo, 'SQL', '177.Nth_Highest_Salary', 'solution.sql',
        body='SELECT 1;',
    )
    conn = db.open_db()
    db.upsert_problem(conn, 177, 'Nth Highest Salary', None, 'sql',
                      '177.Nth_Highest_Salary')
    db.prepare_retry(conn, 177, body_text='')
    assert sfile.read_text() == ''
    # No attempt opened for SQL.
    rows = list(conn.execute('SELECT id FROM attempts WHERE problem_number = 177'))
    assert rows == []
    conn.close()


def test_prepare_retry_unknown_problem_raises(practice_repo):
    conn = db.open_db()
    with pytest.raises(ValueError, match='problem 999 not found'):
        db.prepare_retry(conn, 999, body_text='')
    conn.close()


def test_prepare_retry_glob_collision_raises(practice_repo):
    d = practice_repo / 'src' / 'Easy' / '1.Two_Sum'
    d.mkdir(parents=True)
    (d / 'solution.ts').write_text('a')
    (d / 'solution.py').write_text('b')   # ambiguous
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    with pytest.raises(RuntimeError, match='expected exactly one solution file'):
        db.prepare_retry(conn, 1, body_text='')
    conn.close()


def test_prepare_retry_no_solution_file_raises(practice_repo):
    (practice_repo / 'src' / 'Easy' / '1.Two_Sum').mkdir(parents=True)
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    with pytest.raises(RuntimeError, match='expected exactly one solution file'):
        db.prepare_retry(conn, 1, body_text='')
    conn.close()


# ── dump_sql ────────────────────────────────────────────────────────────────

def test_dump_sql_writes_dump(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.dump_sql(conn)
    text = db.SQL_DUMP.read_text()
    assert 'CREATE TABLE' in text
    assert 'Two Sum' in text
    conn.close()


def test_dump_sql_is_deterministic(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.dump_sql(conn)
    first = db.SQL_DUMP.read_text()
    db.dump_sql(conn)
    second = db.SQL_DUMP.read_text()
    assert first == second
    conn.close()


# ── retry_flags VIEW (smoke test — confirms baseline applied cleanly) ───────

def test_retry_flags_view_exists_and_filters_to_algorithmic(practice_repo):
    conn = db.open_db()
    db.upsert_problem(conn, 1, 'Two Sum', 'Easy', 'algorithmic', '1.Two_Sum')
    db.upsert_problem(conn, 177, 'Nth Highest Salary', None, 'sql',
                      '177.Nth_Highest_Salary')
    rows = list(conn.execute('SELECT number FROM retry_flags'))
    assert (1,) in rows
    assert (177,) not in rows  # SQL excluded
    conn.close()
