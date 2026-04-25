#!/usr/bin/env python3
"""
Pick an algorithmic problem to revisit. Read-only — no DB writes, no file
writes. Caller (SKILL.md) reads the solution file, asks the model to
strip it to a signature-only template, then pipes the stripped body to
apply_solution_template.py.

Args:
  no positional arg → random pick from retry_flags WHERE stale = 1
                      (cooldown elapsed; configurable via
                      config.review_cooldown_days)
  <number>          → explicit pick. Must be an algorithmic problem in
                      the DB. Cooldown is NOT enforced.

Stdout (JSON, one line on success):
  {"number": int,
   "title": str,
   "difficulty": "Easy"|"Medium"|"Hard",
   "solution_path": "src/...",
   "language_name": str,
   "reasons": ["timing"|"complexity"|"stale", ...]}

Exit codes:
  0  success
  1  empty pool (random mode) / unknown problem (explicit) /
     non-algorithmic / not initialised / glob collision / bad args
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402


def find_solution_file(folder_path: Path) -> Path | None:
    """Return the single solution.* file in folder_path. Returns None if
    the folder doesn't exist or has 0/multiple matches."""
    if not folder_path.exists():
        return None
    candidates = sorted(folder_path.glob('solution.*'))
    if len(candidates) != 1:
        return None
    return candidates[0]


def reasons_for(conn, number: int) -> list[str]:
    row = conn.execute(
        'SELECT timing_bad, complexity_bad, stale '
        'FROM retry_flags WHERE number = ?',
        (number,),
    ).fetchone() or (0, 0, 0)
    return [name for flag, name in zip(row, ('timing', 'complexity', 'stale'), strict=True) if flag]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('number', type=int, nargs='?', default=None,
                    help='explicit problem number; omit for random pick')
    args = ap.parse_args()

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        db.sync_config(conn)

        if args.number is not None:
            row = conn.execute(
                'SELECT number, title, difficulty, kind, folder '
                'FROM problems WHERE number = ?',
                (args.number,),
            ).fetchone()
            if row is None:
                print(f'ERROR: problem {args.number} not found in DB.', file=sys.stderr)
                return 1
            if row[3] != 'algorithmic':
                print(f'ERROR: problem {args.number} is {row[3]}, not algorithmic — '
                      f'/leetcode-workflow:retry only handles algorithmic problems.',
                      file=sys.stderr)
                return 1
            number, title, difficulty, _, folder = row
        else:
            rows = list(conn.execute(
                'SELECT number, title, difficulty, folder '
                'FROM retry_flags WHERE stale = 1 ORDER BY number'
            ))
            if not rows:
                print('No retry candidates outside the cooldown window.', file=sys.stderr)
                return 1
            number, title, difficulty, folder = random.choice(rows)

        folder_path = db.REPO / 'src' / difficulty / folder
        sfile = find_solution_file(folder_path)
        if sfile is None:
            print(f'ERROR: could not find a single solution file in '
                  f'{folder_path.relative_to(db.REPO)}', file=sys.stderr)
            return 1

        language_name = db.load_language()['name']
        reasons       = reasons_for(conn, number)

        print(json.dumps({
            'number':        number,
            'title':         title,
            'difficulty':    difficulty,
            'solution_path': str(sfile.relative_to(db.REPO)),
            'language_name': language_name,
            'reasons':       reasons,
        }))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
