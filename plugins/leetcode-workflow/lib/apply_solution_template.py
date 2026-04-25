#!/usr/bin/env python3
"""
Apply a solution template (stripped body or empty wipe) to a problem's
solution file, open a new in-progress attempt for algorithmic problems,
and regenerate views + practice.sql.

Used by both /leetcode-workflow:new (reiteration path) and
/leetcode-workflow:retry. The caller — SKILL.md — is responsible for
producing the body text (asks the model to strip the previous solution
to a signature-only template, then writes that text to a file via the
Write tool).

Args:
  --number N           problem number (algorithmic only)
  --body-file <path>   file whose contents become the new solution body.
                       Empty file → full wipe. Bytes are read verbatim
                       — no JSON encoding, no shell escaping.

Stdout (single line on success):
  retry: cleared <relative-solution-path>

Exit codes:
  0 success
  1 not a leetcode-workflow repo / problem not in DB / glob collision /
    body file missing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db        # noqa: E402
import render    # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--number', type=int, required=True,
                    help='problem number')
    ap.add_argument('--body-file', required=True,
                    help='path to a file containing the new solution body '
                         '(empty file → full wipe)')
    args = ap.parse_args()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f'ERROR: body file not found: {body_path}', file=sys.stderr)
        return 1
    body_text = body_path.read_text()

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        db.sync_config(conn)
        try:
            cleared = db.prepare_retry(conn, args.number, body_text)
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
