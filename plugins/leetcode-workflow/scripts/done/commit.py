#!/usr/bin/env python3
"""
Stage all working-tree changes and commit with the canonical subject:

    {number}. {tag}. {title}

where tag is Easy | Medium | Hard | SQL.

Exit code mirrors `git commit`'s.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--number', type=int, required=True)
    ap.add_argument('--tag',    required=True, choices=('Easy', 'Medium', 'Hard', 'SQL'))
    ap.add_argument('--title',  required=True)
    args = ap.parse_args()

    msg = f'{args.number}. {args.tag}. {args.title}'

    add = subprocess.run(['git', 'add', '.'], cwd=db.REPO,
                         capture_output=True, text=True)
    if add.returncode != 0:
        sys.stderr.write(add.stderr)
        return add.returncode

    commit = subprocess.run(['git', 'commit', '-m', msg], cwd=db.REPO,
                            capture_output=True, text=True)
    if commit.returncode != 0:
        sys.stderr.write(commit.stderr)
        sys.stdout.write(commit.stdout)
        return commit.returncode

    print(f'committed: {msg}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
