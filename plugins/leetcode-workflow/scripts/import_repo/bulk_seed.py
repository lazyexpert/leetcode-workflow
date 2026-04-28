#!/usr/bin/env python3
"""
Bulk-seed problems from a manifest into the practice DB. Used by
/leetcode-workflow:import after the orchestrator has walked the source
repo, fetched LC metadata for each candidate, recovered started_at via
git_first_commit.py, and (optionally) classified patterns.

Preconditions (re-checked here, even though preflight.py already ran):
  * cwd is an initialised practice repo (db.open_db succeeds)
  * the problems table is empty

Manifest schema (read from --input or stdin):
  {
    "problems": [
      {
        "number":          int,
        "title":           str,
        "difficulty":      "Easy" | "Medium" | "Hard" | "" (SQL),
        "type":            "algorithmic" | "SQL",
        "statement":       str,           # markdown body for README.md
        "started_at":      int,           # unix seconds
        "patterns":        [str, ...],    # may be empty
        "solution_source": str            # absolute path on local disk
      },
      ...
    ]
  }

For each entry:
  * upserts the problem
  * inserts a completed-but-imported attempt (NULL duration, imported=1)
  * replaces patterns with the manifest list
  * copies the source solution file to
    src/<Section>/<N>.<Title>/solution.<ext>
    (ext = config.json language.extension for algorithmic, 'sql' for SQL)
  * writes the per-problem README.md from the statement

After all problems: regenerates the five MD views, writes practice.sql.
Does NOT git commit — the orchestrator stops short so the user can
review with `git diff` before locking in.

Stdout: one-line summary on success.
Stderr: validation errors / per-problem warnings.

Exit codes:
  0 success
  1 not initialised / non-empty practice DB / malformed manifest /
    missing source file / I/O failure
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402
import render  # noqa: E402


def folder_name(number: int, title: str) -> str:
    return f'{number}.{title.replace(" ", "_")}'


def section_for(ptype: str, difficulty: str) -> str:
    return 'SQL' if ptype == 'SQL' else difficulty


def _validate_problem(p: dict, idx: int) -> str | None:
    """Return None if valid, an error string otherwise."""
    required = ('number', 'title', 'type', 'statement', 'started_at',
                'solution_source')
    for k in required:
        if k not in p:
            return f'problem #{idx}: missing key {k!r}'
    if not isinstance(p['number'], int) or p['number'] <= 0:
        return f'problem #{idx}: number must be a positive int'
    if p['type'] not in ('algorithmic', 'SQL'):
        return f'problem #{idx}: invalid type {p["type"]!r}'
    if p['type'] == 'algorithmic' and p.get('difficulty') not in (
        'Easy', 'Medium', 'Hard'
    ):
        return (f'problem #{idx}: algorithmic problems require difficulty '
                f'in {{Easy, Medium, Hard}}, got {p.get("difficulty")!r}')
    if not isinstance(p['started_at'], int) or p['started_at'] <= 0:
        return f'problem #{idx}: started_at must be a positive int'
    src = Path(p['solution_source'])
    if not src.is_file():
        return f'problem #{idx}: solution_source does not exist: {src}'
    patterns = p.get('patterns', [])
    if not isinstance(patterns, list) or not all(isinstance(x, str) for x in patterns):
        return f'problem #{idx}: patterns must be a list of strings'
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', help='manifest path; default reads stdin')
    args = ap.parse_args()

    raw = Path(args.input).read_text() if args.input else sys.stdin.read()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f'ERROR: malformed manifest JSON: {e}', file=sys.stderr)
        return 1

    problems = manifest.get('problems')
    if not isinstance(problems, list) or not problems:
        print('ERROR: manifest.problems must be a non-empty list', file=sys.stderr)
        return 1
    for i, p in enumerate(problems):
        err = _validate_problem(p, i)
        if err:
            print(f'ERROR: {err}', file=sys.stderr)
            return 1

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        existing = conn.execute('SELECT COUNT(*) FROM problems').fetchone()[0]
        if existing:
            print(f'ERROR: practice DB already has {existing} problem(s); '
                  f'/import refuses to merge into a populated repo.',
                  file=sys.stderr)
            return 1

        db.sync_config(conn)
        language = db.load_language()

        for p in problems:
            number     = int(p['number'])
            title      = str(p['title'])
            difficulty = str(p.get('difficulty') or '')
            ptype      = p['type']
            statement  = str(p['statement'])
            started_at = int(p['started_at'])
            patterns   = list(p.get('patterns') or [])
            src        = Path(p['solution_source'])

            kind   = 'sql' if ptype == 'SQL' else 'algorithmic'
            ext    = 'sql' if ptype == 'SQL' else language['extension']
            fold   = folder_name(number, title)
            sub    = section_for(ptype, difficulty)
            tdir   = db.REPO / 'src' / sub / fold
            tdir.mkdir(parents=True, exist_ok=True)

            (tdir / f'solution.{ext}').write_bytes(src.read_bytes())
            (tdir / 'README.md').write_text(
                f'# {number}. {title}\n'
                + (statement if statement.endswith('\n') else statement + '\n')
            )

            db.upsert_problem(
                conn, number, title,
                difficulty=None if kind == 'sql' else difficulty,
                kind=kind, folder=fold,
            )
            db.import_attempt(conn, number, started_at)
            if patterns:
                db.replace_patterns(conn, number, patterns)

        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()

    print(f'imported: {len(problems)} problems. Review with `git diff`, '
          f'commit when ready.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
