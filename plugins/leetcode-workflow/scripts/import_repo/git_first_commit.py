#!/usr/bin/env python3
"""
Print the unix timestamp of the first commit that introduced a file in
a possibly-git source repo. Used by /leetcode-workflow:import to recover
a plausible `started_at` for each imported problem.

Resolution order:
  1. If the file lives inside a git repo, return the commit time of the
     first commit that added it. `--follow` traces renames so a file
     added under one name and later renamed still resolves to the
     original introduction date.
  2. Otherwise, fall back to the file's mtime.
  3. If the file does not exist, exit 1.

Usage:
  git_first_commit.py <abs-or-rel-path>

Stdout (success): a single integer (unix seconds).

Exit codes:
   0 success
   1 file does not exist
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def first_commit_ts(path: Path) -> int | None:
    """Return the unix ts of the first commit touching `path`, or None
    if the path isn't tracked / git isn't usable here."""
    parent = path.parent if path.is_file() else path
    top = subprocess.run(
        ['git', '-C', str(parent), 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True,
    )
    if top.returncode != 0:
        return None
    repo_root = Path(top.stdout.strip())
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    log = subprocess.run(
        ['git', '-C', str(repo_root), 'log',
         '--diff-filter=A', '--follow', '--format=%ct', '--', str(rel)],
        capture_output=True, text=True,
    )
    if log.returncode != 0:
        return None
    lines = [line.strip() for line in log.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    # --follow with --diff-filter=A may emit multiple lines (one per
    # rename-add); the introduction commit is the oldest, i.e. last line.
    try:
        return int(lines[-1])
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='file to inspect')
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f'ERROR: {p} does not exist', file=sys.stderr)
        return 1
    ts = first_commit_ts(p)
    if ts is None:
        ts = int(p.stat().st_mtime)
    print(ts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
