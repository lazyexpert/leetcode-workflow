#!/usr/bin/env python3
"""
Apply a solution template (stripped body or empty wipe) to a problem's
solution file, open a new in-progress attempt for algorithmic problems,
and regenerate views + practice.sql.

Used by both /leetcode-workflow:new (reiteration path) and
/leetcode-workflow:retry. The caller — SKILL.md — is responsible for
producing the body text (asks the model to strip the previous solution to
signature-only, or passes "" for a full wipe / for SQL problems).

Reads JSON on stdin:
  {"number": int, "body_text": str}

Stdout (single line on success):
  retry: cleared <relative-solution-path>

Exit codes:
  0 success
  1 not a leetcode-workflow repo / problem not in DB / glob collision /
    malformed input
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db        # noqa: E402
import render    # noqa: E402


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f'ERROR: malformed input JSON: {e}', file=sys.stderr)
        return 1

    number    = payload.get('number')
    body_text = payload.get('body_text', '')
    if not isinstance(number, int):
        print(f'ERROR: "number" must be int, got {number!r}', file=sys.stderr)
        return 1
    if not isinstance(body_text, str):
        print(f'ERROR: "body_text" must be str, got {type(body_text).__name__}', file=sys.stderr)
        return 1

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        db.sync_config(conn)
        try:
            cleared = db.prepare_retry(conn, number, body_text)
        except (ValueError, RuntimeError) as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 1
        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()

    print(f'retry: cleared {cleared.relative_to(db.REPO)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
