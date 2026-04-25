#!/usr/bin/env python3
"""
Detect the problem currently being completed from working-tree changes.

Looks for exactly one non-empty modified or untracked solution file under
src/ matching the configured language extension (or solution.sql under
src/SQL/<folder>/).

Stdout (JSON, on success):
  {"number": int,
   "title": str,
   "difficulty": "Easy"|"Medium"|"Hard"|null,
   "path": "src/...",
   "kind": "algorithmic"|"sql"}

Exit codes:
  0 found exactly one candidate
  1 no candidate / multiple candidates / git error / not initialised
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db    # noqa: E402


def working_tree_changes(repo: Path) -> list[str]:
    """Return paths of all files modified/staged/untracked vs HEAD."""
    # -uall expands untracked dirs so newly-scaffolded folders surface as
    # individual files (README.md, solution.<ext>) rather than a bare entry.
    result = subprocess.run(
        ['git', 'status', '--porcelain', '-uall'],
        capture_output=True, text=True, cwd=repo,
    )
    if result.returncode != 0:
        return []
    paths = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        paths.append(path.strip('"'))
    return paths


def build_solution_rx(extension: str) -> re.Pattern[str]:
    """Match src/<Easy|Medium|Hard>/<folder>/solution.<configured-ext>
    and src/SQL/<folder>/solution.sql."""
    ext = re.escape(extension)
    return re.compile(
        rf'^src/(?:(?:Easy|Medium|Hard)/[^/]+/solution\.{ext}'
        rf'|SQL/[^/]+/solution\.sql)$'
    )


def main() -> int:
    repo = db.REPO
    if not (repo / '.claude' / 'practice.sql').exists() and not (repo / '.claude' / 'practice.db').exists():
        print('ERROR: Not a leetcode-workflow repo. '
              'Run /leetcode-workflow:init or cd into one.', file=sys.stderr)
        return 1

    language = db.load_language()
    rx       = build_solution_rx(language['extension'])
    changed  = working_tree_changes(repo)

    candidates = []
    for p in changed:
        if not rx.match(p):
            continue
        abs_path = repo / p
        if abs_path.exists() and abs_path.stat().st_size > 0:
            candidates.append(p)

    if not candidates:
        print('ERROR: no problem detected — no non-empty solution file has changes.',
              file=sys.stderr)
        print('Run /leetcode-workflow:new first, write your solution, then try again.',
              file=sys.stderr)
        return 1
    if len(candidates) > 1:
        print('ERROR: multiple solution files have changes:', file=sys.stderr)
        for c in candidates:
            print(f'  {c}', file=sys.stderr)
        print('Commit them separately or revert the extras.', file=sys.stderr)
        return 1

    path    = candidates[0]
    parts   = path.split('/')
    section = parts[1]
    folder  = parts[2]
    number  = int(folder.split('.')[0])
    title   = folder.split('.', 1)[1].replace('_', ' ')
    is_sql  = section == 'SQL'

    print(json.dumps({
        'number':     number,
        'title':      title,
        'difficulty': None if is_sql else section,
        'path':       path,
        'kind':       'sql' if is_sql else 'algorithmic',
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
