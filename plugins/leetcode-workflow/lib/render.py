"""
Render the five Markdown views from practice.db.

Views are derived purely from the database — no hand-edited content
survives a render. Output is deterministic regardless of the caller's
timezone (all dates are UTC).

Outputs (relative to repo root):
    progress.md
    timings.md
    retry.md
    patterns-coverage.md
    history.md

Usage as CLI:
    python render.py                              # write to repo root
    python render.py --db /tmp/scratch.db --out-dir /tmp/rendered
"""
from __future__ import annotations

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

import db


def link_path(difficulty: str | None, kind: str, folder: str) -> str:
    section = 'SQL' if kind == 'sql' else difficulty
    return f'src/{section}/{folder}'


def utc_date(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()


def utc_month(ts: int) -> tuple[int, int]:
    d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return d.year, d.month


MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


# ── progress.md ─────────────────────────────────────────────────────────────

def render_progress(conn: sqlite3.Connection) -> str:
    counts = {row[0]: row[1] for row in conn.execute(
        "SELECT COALESCE(difficulty, 'SQL'), COUNT(*) "
        "FROM problems GROUP BY difficulty"
    )}
    easy  = counts.get('Easy', 0)
    med   = counts.get('Medium', 0)
    hard  = counts.get('Hard', 0)
    sql   = counts.get('SQL', 0)
    total = easy + med + hard + sql

    out = [
        '# Progress',
        '',
        '| Difficulty | Solved |',
        '|------------|--------|',
        f'| Easy       | {easy:<6} |',
        f'| Medium     | {med:<6} |',
        f'| Hard       | {hard:<6} |',
        f'| SQL        | {sql:<6} |',
        f'| **Total**  | **{total}** |',
        '',
    ]

    for section in ('Easy', 'Medium', 'Hard', 'SQL'):
        diff_filter = 'p.difficulty IS NULL' if section == 'SQL' else 'p.difficulty = ?'
        params      = () if section == 'SQL' else (section,)
        rows = list(conn.execute(
            f'SELECT p.number, p.title, p.difficulty, p.kind, p.folder '
            f'FROM problems p WHERE {diff_filter} ORDER BY p.number',
            params,
        ))
        out.append(f'## {section}')
        for num, title, diff, kind, folder in rows:
            out.append(f'- [{num}. {title}]({link_path(diff, kind, folder)})')
        out.append('')

    return '\n'.join(out).rstrip() + '\n'


# ── timings.md ──────────────────────────────────────────────────────────────

def render_timings(conn: sqlite3.Connection) -> str:
    thresholds = dict(conn.execute('SELECT difficulty, minutes FROM thresholds'))
    threshold_line = ' · '.join(
        f'{k} ≥ {thresholds.get(k, "?")} min' for k in ('Easy', 'Medium', 'Hard')
    )
    header = [
        '# Solution Timings',
        '',
        'Time from `/leetcode-workflow:new` scaffold to `/leetcode-workflow:done` commit, in minutes.',
        f'Retry thresholds (configurable in `config.json`): {threshold_line}',
        '',
        '| # | Problem | Difficulty | Date | Minutes |',
        '|---|---------|------------|------|---------|',
    ]

    rows = list(conn.execute(
        'SELECT p.number, p.title, p.difficulty, p.kind, p.folder, '
        '       a.started_at, a.duration_minutes '
        'FROM attempts a JOIN problems p ON p.number = a.problem_number '
        'WHERE a.duration_minutes IS NOT NULL AND p.kind = ? '
        'ORDER BY p.number, a.started_at',
        ('algorithmic',),
    ))

    body = [
        f'| {num} | [{title}]({link_path(diff, kind, folder)}) | '
        f'{diff} | {utc_date(started_at)} | {duration} |'
        for num, title, diff, kind, folder, started_at, duration in rows
    ]

    return '\n'.join(header + body) + '\n'


# ── retry.md ────────────────────────────────────────────────────────────────

def render_retry(conn: sqlite3.Connection) -> str:
    header = [
        '# Retry List',
        '',
        'Algorithmic problems eligible for revisit, derived from the `retry_flags` view',
        'every render. `/leetcode-workflow:retry` picks a random entry from this list.',
        '',
        'Reason flags: `timing` — latest attempt exceeded the threshold · '
        '`complexity` — classifier flagged a better solution exists · '
        '`stale` — cooldown (see `config.json: review_cooldown_days`) has elapsed. '
        'Combinations are joined with `+`.',
        '',
        '| Date Added | # | Problem | Difficulty | Reason |',
        '|------------|---|---------|------------|--------|',
    ]

    rows = list(conn.execute(
        'SELECT number, title, difficulty, folder, flagged_at, '
        '       timing_bad, complexity_bad, stale '
        'FROM retry_flags '
        'WHERE timing_bad = 1 OR complexity_bad = 1 OR stale = 1 '
        'ORDER BY number'
    ))

    body = []
    for num, title, diff, folder, flagged_at, timing_bad, complexity_bad, stale in rows:
        reasons = []
        if timing_bad:     reasons.append('timing')
        if complexity_bad: reasons.append('complexity')
        if stale:          reasons.append('stale')
        body.append(
            f'| {utc_date(flagged_at)} | {num} | '
            f'[{title}]({link_path(diff, "algorithmic", folder)}) | '
            f'{diff} | {"+".join(reasons)} |'
        )

    return '\n'.join(header + body) + '\n'


# ── patterns-coverage.md ────────────────────────────────────────────────────

def render_patterns(conn: sqlite3.Connection) -> str:
    out = ['# Pattern Coverage', '']

    for pattern in db.load_patterns():
        rows = list(conn.execute(
            'SELECT DISTINCT p.number, p.title, p.difficulty, p.kind, p.folder '
            'FROM patterns pt JOIN problems p ON p.number = pt.problem_number '
            'WHERE pt.pattern = ? ORDER BY p.number',
            (pattern,),
        ))
        if not rows:
            continue
        out.append(f'## {pattern}')
        for num, title, diff, kind, folder in rows:
            out.append(f'- [{num}. {title}]({link_path(diff, kind, folder)})')
        out.append('')

    return '\n'.join(out).rstrip() + '\n'


# ── history.md ──────────────────────────────────────────────────────────────

def render_history(conn: sqlite3.Connection) -> str:
    # Earliest attempt per problem defines its history month.
    rows = list(conn.execute(
        'SELECT p.number, p.difficulty, p.kind, p.folder, MIN(a.started_at) '
        'FROM problems p JOIN attempts a ON a.problem_number = p.number '
        'GROUP BY p.number '
        'ORDER BY MIN(a.started_at)'
    ))

    by_month: dict[tuple[int, int], dict[str, list[str]]] = {}
    for num, diff, kind, folder, started in rows:
        y, m = utc_month(started)
        bucket = by_month.setdefault((y, m), {'algo': [], 'sql': []})
        entry  = f'[{num}]({link_path(diff, kind, folder)})'
        bucket['sql' if kind == 'sql' else 'algo'].append(entry)

    out = ['# History', '']
    # Newest month first.
    for (y, m) in sorted(by_month.keys(), reverse=True):
        bucket = by_month[(y, m)]
        out.append(f'## {MONTH_NAMES[m]} {y}')
        if bucket['algo']:
            out.append(', '.join(bucket['algo']))
        if bucket['sql']:
            out.append(f'SQL: {", ".join(bucket["sql"])}')
        out.append('')

    return '\n'.join(out).rstrip() + '\n'


# ── orchestration ───────────────────────────────────────────────────────────

VIEWS = {
    'progress.md':           render_progress,
    'timings.md':            render_timings,
    'retry.md':              render_retry,
    'patterns-coverage.md':  render_patterns,
    'history.md':            render_history,
}


def render_all(conn: sqlite3.Connection, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, fn in VIEWS.items():
        (out_dir / filename).write_text(fn(conn))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db',      default=str(db.DB_PATH))
    ap.add_argument('--out-dir', default=str(db.REPO))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        render_all(conn, Path(args.out_dir))
    finally:
        conn.close()

    for filename in VIEWS:
        print(f'  ✓ rendered {filename}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
