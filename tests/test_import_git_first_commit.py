"""
Subprocess tests for scripts/import_repo/git_first_commit.py.

Three paths under test:
  * file inside a git repo → first-commit timestamp
  * file outside any git repo → mtime fallback
  * missing path → exit 1
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'
SCRIPT      = PLUGIN_ROOT / 'scripts' / 'import_repo' / 'git_first_commit.py'


def _git(cwd: Path, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_init(cwd: Path):
    _git(cwd, 'init', '-q', '--initial-branch=main')
    _git(cwd, 'config', 'user.email', 'test@example.com')
    _git(cwd, 'config', 'user.name',  'Test')
    _git(cwd, 'config', 'commit.gpgsign', 'false')


def _run(path: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True, text=True,
    )


def test_returns_first_commit_ts(tmp_path):
    """File added in commit 1, modified in commit 2 — should return the
    earlier (commit 1) timestamp."""
    _git_init(tmp_path)
    target = tmp_path / 'solution.py'
    target.write_text('# v1\n')
    _git(tmp_path, 'add', 'solution.py')
    _git(tmp_path, '-c', 'commit.gpgsign=false',
         'commit', '-q', '-m', 'add solution', '--date', '@1700000000')
    # Force GIT_COMMITTER_DATE on the commit too — `--date` only sets author.
    env = dict(os.environ)
    env['GIT_AUTHOR_DATE']    = '@1700000000'
    env['GIT_COMMITTER_DATE'] = '@1700000000'
    # Second commit at a later time
    target.write_text('# v2\n')
    subprocess.run(
        ['git', 'commit', '-q', '-am', 'update', '--date', '@1800000000'],
        cwd=tmp_path, env={**env, 'GIT_AUTHOR_DATE': '@1800000000',
                           'GIT_COMMITTER_DATE': '@1800000000'},
        check=True, capture_output=True, text=True,
    )

    result = _run(target)
    assert result.returncode == 0, result.stderr
    ts = int(result.stdout.strip())
    # Earlier commit (or close) — at minimum, before the 1800000000 update.
    assert ts < 1_800_000_000


def test_falls_back_to_mtime_when_not_in_git(tmp_path):
    target = tmp_path / 'solo.py'
    target.write_text('print(1)\n')
    expected_mtime = int(target.stat().st_mtime)

    result = _run(target)
    assert result.returncode == 0, result.stderr
    ts = int(result.stdout.strip())
    # Allow ±1 second slack for filesystems that store sub-second mtimes
    # the script truncates via int().
    assert abs(ts - expected_mtime) <= 1


def test_exits_one_when_path_missing(tmp_path):
    result = _run(tmp_path / 'does-not-exist.py')
    assert result.returncode == 1
    assert 'does not exist' in result.stderr


def test_untracked_file_in_git_repo_falls_back_to_mtime(tmp_path):
    """File lives inside a git repo but was never committed — the helper
    should report mtime, not 1970."""
    _git_init(tmp_path)
    # An initial commit so the repo isn't empty (otherwise rev-parse may fail).
    (tmp_path / 'README.md').write_text('# repo\n')
    _git(tmp_path, 'add', 'README.md')
    _git(tmp_path, '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'init')

    target = tmp_path / 'untracked.py'
    target.write_text('x = 1\n')

    result = _run(target)
    assert result.returncode == 0, result.stderr
    ts = int(result.stdout.strip())
    assert ts >= int(target.stat().st_mtime) - 1
