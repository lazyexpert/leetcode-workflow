#!/usr/bin/env python3
"""
Emit pattern coverage data so the model can suggest a LeetCode problem
URL that targets an under-covered pattern and avoids duplicates of
problems already in the user's DB.

Stdout (JSON, one line):
  {
    "gaps": [
      {"pattern": "Trie", "count": 0},
      {"pattern": "Bit Manipulation", "count": 1},
      ...
    ],
    "solved_numbers": [1, 2, 3, 19, 20, ...]
  }

`gaps` lists every config-defined pattern with its distinct-problem
count, sorted ascending by count then by the configured render order.
Zero-count patterns surface first — those are the strongest gaps for
the model to target.

`solved_numbers` is every distinct problem number in the DB (including
SQL problems, since /pick's new-path scaffolds via fetch+scaffold and
should never propose an existing number even if it's SQL).

Exit codes:
  0 success
  1 not initialised
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import db    # noqa: E402


def main() -> int:
    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        patterns = db.load_patterns()
        # COUNT distinct problem_numbers per pattern label.
        counts = dict(conn.execute(
            'SELECT pattern, COUNT(DISTINCT problem_number) FROM patterns GROUP BY pattern'
        ))
        # Preserve config render order as a stable tiebreaker.
        gaps = [
            {'pattern': p, 'count': int(counts.get(p, 0))}
            for p in patterns
        ]
        gaps.sort(key=lambda g: (g['count'], patterns.index(g['pattern'])))

        solved_numbers = [
            row[0] for row in conn.execute('SELECT number FROM problems ORDER BY number')
        ]
    finally:
        conn.close()

    print(json.dumps({'gaps': gaps, 'solved_numbers': solved_numbers}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
