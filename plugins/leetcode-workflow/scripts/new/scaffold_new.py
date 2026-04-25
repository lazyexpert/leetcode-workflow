#!/usr/bin/env python3
"""
Scaffold a fresh problem folder from a manifest.

Reads manifest JSON on stdin:
  {"number": int, "title": str,
   "difficulty": "Easy"|"Medium"|"Hard"|"" (SQL),
   "type": "algorithmic"|"SQL",
   "statement": "<markdown body>"}

Side effects:
  - creates src/<section>/<folder>/{README.md, solution.<ext|sql>}
  - upserts the problem in practice.db
  - opens a new in-progress attempt (algorithmic only)
  - regenerates the five MD views, dumps practice.sql

Stdout (one line on success):
  scaffold: created <relative-folder-path>

Exit codes:
  0 success
  1 malformed manifest / target solution already non-empty (caller
    should run detect_reiteration.py first to route reiteration)
  2 not initialised
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db        # noqa: E402
import render    # noqa: E402


def folder_name(number: int, title: str) -> str:
    return f'{number}.{title.replace(" ", "_")}'


def target_dir(repo: Path, number: int, title: str, difficulty: str, ptype: str) -> Path:
    sub = 'SQL' if ptype == 'SQL' else difficulty
    return repo / 'src' / sub / folder_name(number, title)


def main() -> int:
    try:
        manifest = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f'ERROR: malformed manifest JSON: {e}', file=sys.stderr)
        return 1

    required = ('number', 'title', 'type', 'statement')
    missing  = [k for k in required if k not in manifest]
    if missing:
        print(f'ERROR: manifest missing keys: {missing}', file=sys.stderr)
        return 1

    number     = int(manifest['number'])
    title      = manifest['title']
    difficulty = manifest.get('difficulty') or ''
    ptype      = manifest['type']
    statement  = manifest['statement']
    signature  = manifest.get('signature', '')

    if ptype not in ('algorithmic', 'SQL'):
        print(f'ERROR: invalid type {ptype!r}', file=sys.stderr)
        return 1
    if ptype == 'algorithmic' and difficulty not in ('Easy', 'Medium', 'Hard'):
        print(f'ERROR: invalid difficulty {difficulty!r}', file=sys.stderr)
        return 1

    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2

    try:
        db.sync_config(conn)

        language = db.load_language()
        kind     = 'sql' if ptype == 'SQL' else 'algorithmic'
        fold     = folder_name(number, title)
        tdir     = target_dir(db.REPO, number, title, difficulty, ptype)
        sfile    = tdir / ('solution.sql' if ptype == 'SQL' else f'solution.{language["extension"]}')

        if sfile.exists() and sfile.stat().st_size > 0:
            print(f'ERROR: {sfile.relative_to(db.REPO)} already has content. '
                  f'Run detect_reiteration.py first to route reiteration.',
                  file=sys.stderr)
            return 1

        tdir.mkdir(parents=True, exist_ok=True)
        readme = tdir / 'README.md'
        readme.write_text(
            f'# {number}. {title}\n'
            + (statement if statement.endswith('\n') else statement + '\n')
        )
        # Seed the solution file with LC's per-language signature template
        # (function/class declaration with empty body) so the user doesn't
        # have to copy-paste it from the LC web UI. Empty string when LC
        # doesn't have a snippet for this language — file stays empty.
        sfile.write_text(signature)

        db.upsert_problem(
            conn, number, title,
            difficulty=None if kind == 'sql' else difficulty,
            kind=kind, folder=fold,
        )
        if kind == 'algorithmic':
            db.start_attempt(conn, number)

        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()

    print(f'scaffold: created {tdir.relative_to(db.REPO)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
