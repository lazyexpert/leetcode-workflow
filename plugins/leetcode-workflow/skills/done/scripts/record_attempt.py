#!/usr/bin/env python3
"""
Record a completed solve attempt — close the in-progress attempt, replace
patterns, sync config, print a verdict.

Reads JSON on stdin:
  {
    "number":     int,
    "title":      str,
    "difficulty": "Easy"|"Medium"|"Hard"|null,
    "path":       str,
    "kind":       "algorithmic"|"sql",
    "classification": {"patterns": ["..."], "revisit": bool}
       — present for algorithmic only; absent for SQL or when the model
         skipped classification. The script accepts a missing or null
         classification gracefully (no patterns recorded, revisit=false).
  }

Side effects:
  * upserts the problem
  * for algorithmic:
      - filters classification.patterns against config.patterns (the closed
        enum); warns about rejected labels
      - opens-then-closes an attempt if no in-progress attempt exists
        (covers the "edited a solution without running /new" case)
      - closes the in-progress attempt with revisit and computed duration
      - replaces patterns rows
  * for SQL: just records the upsert. No attempt, no patterns.

Stdout: human-readable verdict lines (timing, patterns, complexity).

Exit codes:
  0 success
  1 malformed input / not initialised
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import db    # noqa: E402


REQUIRED_KEYS = ('number', 'title', 'difficulty', 'path', 'kind')


def parse_payload(raw: str) -> dict:
    data = json.loads(raw)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f'missing keys: {missing}')
    if data['kind'] not in ('algorithmic', 'sql'):
        raise ValueError(f'invalid kind {data["kind"]!r}')
    if data['kind'] == 'algorithmic' and data['difficulty'] not in ('Easy', 'Medium', 'Hard'):
        raise ValueError(f'algorithmic problem requires Easy|Medium|Hard, got {data["difficulty"]!r}')
    return data


def main() -> int:
    try:
        payload = parse_payload(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as e:
        print(f'ERROR: malformed input: {e}', file=sys.stderr)
        return 1

    number     = payload['number']
    title      = payload['title']
    difficulty = payload['difficulty']
    kind       = payload['kind']
    folder     = Path(payload['path']).parent.name

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        db.sync_config(conn)
        db.upsert_problem(
            conn, number, title,
            difficulty=None if kind == 'sql' else difficulty,
            kind=kind, folder=folder,
        )

        if kind == 'sql':
            db.dump_sql(conn)
            return 0

        # Algorithmic: classify, close attempt, replace patterns.
        classification = payload.get('classification') or {}
        raw_patterns   = classification.get('patterns', []) or []
        revisit        = bool(classification.get('revisit', False))

        known    = set(db.load_patterns())
        accepted = [p for p in raw_patterns if p in known]
        rejected = [p for p in raw_patterns if p not in known]
        if rejected:
            print(f'  ⚠ classifier returned unknown patterns {rejected} — filtered out')

        open_row = db.latest_open_attempt(conn, number)
        if open_row is None:
            attempt_id = db.start_attempt(conn, number)
            print(f'  ⚠ no in-progress attempt for {number}. {title}; '
                  f'recording with min duration')
        else:
            attempt_id = open_row[0]

        duration = db.complete_attempt(conn, attempt_id, revisit=revisit)

        threshold_row = conn.execute(
            'SELECT minutes FROM thresholds WHERE difficulty = ?', (difficulty,)
        ).fetchone()
        threshold = threshold_row[0] if threshold_row else None
        if threshold is None:
            print(f'  ⏱ timing:     {duration} min')
        elif duration < threshold:
            print(f'  ✓ timing:     {duration} min  '
                  f'(within {difficulty} threshold of {threshold} min)')
        else:
            print(f'  ⚠ timing:     {duration} min  '
                  f'(over {difficulty} threshold of {threshold} min)')

        if accepted:
            db.replace_patterns(conn, number, accepted)
            print(f'  ✓ patterns:   {", ".join(accepted)}')
            if revisit:
                print('  ⚠ complexity: classifier flagged a better solution exists')
            else:
                print('  ✓ complexity: optimal')

        db.dump_sql(conn)
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
