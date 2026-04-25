"""
Shared SQLite helpers for the leetcode-workflow plugin.

The DB lives at <repo>/.claude/practice.db (gitignored). A deterministic .sql
dump is written to <repo>/.claude/practice.sql after every mutation — that's
the git-tracked form, so collaborators can rebuild the DB with:

    sqlite3 .claude/practice.db < .claude/practice.sql

This module is pure: no LLM calls. The classifier prompt and the
strip-solution-body prompt live in the relevant SKILL.md files; scripts
receive the model's output as input. Path resolution honors the
LEETCODE_REPO env var (used by tests) before falling back to
`git rev-parse --show-toplevel`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


class NotInitialized(Exception):
    """Raised by open_db() when neither practice.db nor practice.sql exists.
    Callers (skill scripts) should catch this and exit 1 with the canonical
    "Not a leetcode-workflow repo" message."""


def _resolve_repo() -> Path:
    """Return the practice repo root.

    Never raises — even outside a git repo, returns cwd. The canonical
    "is this initialized" check lives in open_db(), which raises
    NotInitialized if neither practice.db nor practice.sql exists.
    """
    env = os.environ.get('LEETCODE_REPO')
    if env:
        return Path(env).resolve()
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


REPO            = _resolve_repo()
DB_PATH         = REPO / '.claude' / 'practice.db'
SQL_DUMP        = REPO / '.claude' / 'practice.sql'
CONFIG          = REPO / 'config.json'
SCHEMA_BASELINE = Path(__file__).parent.parent / 'schema-baseline.sql'

DEFAULT_THRESHOLDS    = {'Easy': 15, 'Medium': 30, 'Hard': 60}
DEFAULT_LANGUAGE      = {'extension': 'ts', 'name': 'typescript'}
DEFAULT_COOLDOWN_DAYS = 7
DEFAULT_PICK_RETRY_RATIO = 0.0
DEFAULT_PATTERNS      = [
    'Two Pointers', 'Sliding Window', 'Binary Search', 'Stack / Monotonic Stack',
    'BFS / DFS', 'Dynamic Programming', 'Greedy', 'Hash Map / Hash Set',
    'Linked List', 'Tree Traversal', 'Backtracking', 'Bit Manipulation',
    'Heap / Priority Queue', 'Trie', 'Prefix Sum', 'Math', 'Sorting',
    'Design / Simulation',
]


# ── config.json loaders ─────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG.exists():
        return {}
    try:
        return json.loads(CONFIG.read_text())
    except json.JSONDecodeError as e:
        print(f'  ⚠ {CONFIG.name} malformed ({e}); using defaults', file=sys.stderr)
        return {}


def load_thresholds() -> dict[str, int]:
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update(_load_config().get('retry_thresholds_minutes', {}) or {})
    return {k: int(v) for k, v in merged.items()}


def load_language() -> dict[str, str]:
    """Return {'extension': str, 'name': str} for the active algorithmic language."""
    merged = dict(DEFAULT_LANGUAGE)
    merged.update(_load_config().get('language', {}) or {})
    return {
        'extension': str(merged['extension']).lstrip('.').lower(),
        'name':      str(merged['name']).lower(),
    }


def load_cooldown_days() -> int:
    """Days-since-last-attempt threshold for the `stale` retry flag and for
    the `/leetcode-workflow:retry` picker."""
    raw = _load_config().get('review_cooldown_days', DEFAULT_COOLDOWN_DAYS)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_DAYS


def load_pick_retry_ratio() -> float:
    """0..1 share of /leetcode-workflow:pick invocations that should route to
    the retry pool instead of suggesting a fresh problem. Out-of-range values
    clamp to [0, 1]; non-numeric values fall back to the default."""
    raw = _load_config().get('pick_retry_ratio', DEFAULT_PICK_RETRY_RATIO)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_PICK_RETRY_RATIO
    return max(0.0, min(1.0, v))


def load_patterns() -> list[str]:
    """The closed enum of classifier labels + the render order for
    patterns-coverage.md. Config-driven so users can add niche patterns
    (Union Find, Line Sweep, Segment Tree…) or trim to fewer buckets.
    Empty/malformed → falls back to DEFAULT_PATTERNS."""
    raw = _load_config().get('patterns')
    if not isinstance(raw, list):
        return list(DEFAULT_PATTERNS)
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        label = item.strip()
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result or list(DEFAULT_PATTERNS)


# ── connection ──────────────────────────────────────────────────────────────

def apply_baseline(conn: sqlite3.Connection) -> None:
    """Apply schema-baseline.sql to an open connection. Used by /init and
    by tests that want a fresh DB without going through the migration
    runner."""
    conn.executescript(SCHEMA_BASELINE.read_text())
    conn.commit()


def open_db() -> sqlite3.Connection:
    """Open practice.db.

    Behaviour:
      * .db exists                       → open it
      * .db missing, .sql dump present   → rebuild .db from .sql, open
      * neither exists                   → raise NotInitialized
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        if not SQL_DUMP.exists():
            raise NotInitialized(
                'Not a leetcode-workflow repo. Run /leetcode-workflow:init or cd into one.'
            )
        # Fresh-clone path: rebuild the binary DB from the deterministic dump.
        rebuild = sqlite3.connect(DB_PATH)
        rebuild.executescript(SQL_DUMP.read_text())
        rebuild.commit()
        rebuild.close()
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


# ── problems ────────────────────────────────────────────────────────────────

def upsert_problem(
    conn: sqlite3.Connection,
    number: int,
    title: str,
    difficulty: str | None,
    kind: str,
    folder: str,
) -> None:
    """Insert the problem; on conflict update mutable metadata but keep created_at."""
    now = int(time.time())
    conn.execute(
        'INSERT INTO problems (number, title, difficulty, kind, folder, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?) '
        'ON CONFLICT(number) DO UPDATE SET '
        '  title      = excluded.title, '
        '  difficulty = excluded.difficulty, '
        '  kind       = excluded.kind, '
        '  folder     = excluded.folder',
        (number, title, difficulty, kind, folder, now),
    )


# ── attempts ────────────────────────────────────────────────────────────────

def start_attempt(conn: sqlite3.Connection, number: int) -> int:
    """Open a new in-progress attempt for the problem. Returns attempt id.

    Real users put minutes between attempts, but tools and tests can fire
    scaffold→done→retry within the same wall-clock second — colliding with
    the (problem_number, started_at) UNIQUE constraint. On collision we bump
    started_at by a second and retry; the constraint stays meaningful (no two
    attempts at the literal same instant) without making the tools flaky.
    """
    now = int(time.time())
    while True:
        try:
            cur = conn.execute(
                'INSERT INTO attempts (problem_number, started_at, duration_minutes, revisit) '
                'VALUES (?, ?, NULL, 0)',
                (number, now),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            now += 1


def latest_open_attempt(conn: sqlite3.Connection, number: int) -> tuple[int, int] | None:
    """Return (attempt_id, started_at) of the latest in-progress attempt, or None."""
    return conn.execute(
        'SELECT id, started_at FROM attempts '
        'WHERE problem_number = ? AND duration_minutes IS NULL '
        'ORDER BY started_at DESC LIMIT 1',
        (number,),
    ).fetchone()


def complete_attempt(conn: sqlite3.Connection, attempt_id: int, revisit: bool) -> int:
    """Finalize an attempt: computes duration_minutes from (now - started_at)/60,
    sets revisit. Returns duration in minutes.

    Minimum is 1 minute — sub-minute solves bucket as "1 min" so timings.md
    stays readable.
    """
    row = conn.execute(
        'SELECT started_at FROM attempts WHERE id = ?', (attempt_id,)
    ).fetchone()
    if not row:
        raise ValueError(f'attempt {attempt_id} not found')
    started_at = row[0]
    now        = int(time.time())
    duration   = max(1, round((now - started_at) / 60))
    conn.execute(
        'UPDATE attempts SET duration_minutes = ?, revisit = ? WHERE id = ?',
        (duration, 1 if revisit else 0, attempt_id),
    )
    return duration


# ── patterns ────────────────────────────────────────────────────────────────

def replace_patterns(conn: sqlite3.Connection, number: int, patterns: list[str]) -> None:
    """Replace the problem's pattern rows with the given set. `created_at` is
    refreshed so the row mirrors when this classification happened."""
    conn.execute('DELETE FROM patterns WHERE problem_number = ?', (number,))
    if not patterns:
        return
    now = int(time.time())
    conn.executemany(
        'INSERT INTO patterns (problem_number, pattern, created_at) VALUES (?, ?, ?)',
        [(number, p, now) for p in patterns],
    )


# ── thresholds / settings ───────────────────────────────────────────────────

def upsert_thresholds(conn: sqlite3.Connection, thresholds: dict[str, int]) -> None:
    """Mirror config.json's retry_thresholds_minutes into the thresholds table
    so the retry_flags VIEW can reference them."""
    for diff, minutes in thresholds.items():
        conn.execute(
            'INSERT INTO thresholds (difficulty, minutes) VALUES (?, ?) '
            'ON CONFLICT(difficulty) DO UPDATE SET minutes = excluded.minutes',
            (diff, int(minutes)),
        )


def upsert_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, str(value)),
    )


def sync_config(conn: sqlite3.Connection) -> None:
    """Mirror all relevant config.json knobs into DB tables used by views.
    Called by every skill so the view always sees the user's current
    settings without needing to wait for a /update."""
    upsert_thresholds(conn, load_thresholds())
    upsert_setting(conn, 'review_cooldown_days', load_cooldown_days())


# ── reiteration (shared by /new and /retry) ─────────────────────────────────

def prepare_retry(conn: sqlite3.Connection, number: int, body_text: str) -> Path:
    """Reset the existing solution file for a fresh solve and (for algorithmic
    problems) open a new in-progress attempt. Returns the solution path.

    `body_text` is what gets written to the file. Skills compute it:
      * algorithmic + reiteration via /new or /retry — caller asks the model
        to strip the previous solution to a signature-only template, passes
        that text in. If stripping failed the caller passes "" (full wipe).
      * SQL — caller always passes "" (SQL has no signature to preserve).

    The solution file is discovered by globbing `solution.*` in the problem
    folder — keeps us correct even if the language extension changed in
    `config.json` since the last solve.

    Caller is responsible for rendering views and dumping SQL after this
    returns.
    """
    row = conn.execute(
        'SELECT difficulty, kind, folder FROM problems WHERE number = ?',
        (number,),
    ).fetchone()
    if not row:
        raise ValueError(f'problem {number} not found in DB')
    difficulty, kind, folder = row
    section = 'SQL' if kind == 'sql' else difficulty
    folder_path = REPO / 'src' / section / folder
    candidates  = sorted(folder_path.glob('solution.*'))
    if len(candidates) != 1:
        raise RuntimeError(
            f'expected exactly one solution file in {folder_path.relative_to(REPO)}, '
            f'found {[c.name for c in candidates]}'
        )
    sfile = candidates[0]

    sfile.write_text(body_text)
    if kind == 'algorithmic':
        start_attempt(conn, number)
    return sfile


# ── dump ────────────────────────────────────────────────────────────────────

def dump_sql(conn: sqlite3.Connection) -> None:
    """Commit the connection and write a deterministic .sql dump of practice.db."""
    conn.commit()
    result = subprocess.run(
        ['sqlite3', str(DB_PATH), '.dump'],
        capture_output=True, text=True, check=True,
    )
    SQL_DUMP.write_text(result.stdout)
