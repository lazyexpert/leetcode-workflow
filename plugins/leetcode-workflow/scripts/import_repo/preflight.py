#!/usr/bin/env python3
"""
Preflight check for /leetcode-workflow:import.

Validates that cwd is ready to receive imported data:
  * is an initialised practice repo (.claude/practice.db or .sql exists)
  * the problems table is empty (no prior data)

Run before the orchestrator does any heavy lifting (source-repo walk,
LC fetches, classification) so the user finds out about config problems
before tokens are spent.

Stdout: 'preflight: ready' on success.
Exit codes:
   0 ready
   1 not initialised
   2 already populated
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402


def main() -> int:
    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    try:
        n = conn.execute('SELECT COUNT(*) FROM problems').fetchone()[0]
        if n:
            print(f'ERROR: practice DB already has {n} problem(s); '
                  f'/import refuses to merge into a populated repo. '
                  f'Run /import inside a fresh /leetcode-workflow:init repo.',
                  file=sys.stderr)
            return 2
    finally:
        conn.close()
    print('preflight: ready')
    return 0


if __name__ == '__main__':
    sys.exit(main())
