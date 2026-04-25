#!/usr/bin/env python3
"""
Regenerate the five Markdown views and refresh practice.sql.

Called at the end of every mutating skill (done, new, retry, abort, pick).
Pure orchestration over db + render — no LLM, no DB writes beyond the
deterministic dump that follows render_all.

Exit codes:
  0 success
  1 not a leetcode-workflow repo
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import render  # noqa: E402


def main() -> int:
    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    try:
        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
