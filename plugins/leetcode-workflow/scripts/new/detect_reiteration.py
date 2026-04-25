#!/usr/bin/env python3
"""
Decide whether a manifest scaffolds a fresh problem or signals reiteration.

Reads manifest JSON on stdin (output of fetch.py).

Stdout (JSON, one line):
  {"mode": "new", "manifest": {...}}
    — folder doesn't exist, OR exists but solution file is empty/missing.
    Caller should pipe the manifest into scaffold_new.py.

  {"mode": "reiterate",
   "number": int,
   "solution_path": "src/...",
   "language_name": str}
    — folder exists with a non-empty solution. Caller should read the
    solution file, ask the model to strip it to a signature-only
    template (use the language_name as the code-fence hint), and pipe
    the stripped body into apply_solution_template.py.

Exit codes:
  0 success
  1 malformed manifest / not initialised
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db    # noqa: E402


def folder_name(number: int, title: str) -> str:
    return f'{number}.{title.replace(" ", "_")}'


def target_dir(repo: Path, number: int, title: str, difficulty: str, ptype: str) -> Path:
    sub = 'SQL' if ptype == 'SQL' else difficulty
    return repo / 'src' / sub / folder_name(number, title)


def solution_filename(ptype: str, ext: str) -> str:
    return 'solution.sql' if ptype == 'SQL' else f'solution.{ext}'


def main() -> int:
    try:
        manifest = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f'ERROR: malformed manifest JSON: {e}', file=sys.stderr)
        return 1

    required = ('number', 'title', 'type')
    missing  = [k for k in required if k not in manifest]
    if missing:
        print(f'ERROR: manifest missing keys: {missing}', file=sys.stderr)
        return 1

    number     = int(manifest['number'])
    title      = manifest['title']
    difficulty = manifest.get('difficulty') or ''
    ptype      = manifest['type']

    if ptype not in ('algorithmic', 'SQL'):
        print(f'ERROR: invalid type {ptype!r}', file=sys.stderr)
        return 1
    if ptype == 'algorithmic' and difficulty not in ('Easy', 'Medium', 'Hard'):
        print(f'ERROR: invalid difficulty {difficulty!r}', file=sys.stderr)
        return 1

    language = db.load_language()
    tdir     = target_dir(db.REPO, number, title, difficulty, ptype)
    sfile    = tdir / solution_filename(ptype, language['extension'])

    has_content = sfile.exists() and sfile.stat().st_size > 0

    if has_content:
        print(json.dumps({
            'mode':          'reiterate',
            'number':        number,
            'solution_path': str(sfile.relative_to(db.REPO)),
            'language_name': language['name'],
        }))
    else:
        print(json.dumps({'mode': 'new', 'manifest': manifest}))

    return 0


if __name__ == '__main__':
    sys.exit(main())
