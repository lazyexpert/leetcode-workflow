"""
Subprocess tests for skills/done/scripts/commit.py.
"""
from __future__ import annotations

import subprocess
import sys

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'skills' / 'done' / 'scripts' / 'commit.py'


def _git_log_subjects(repo):
    out = subprocess.run(
        ['git', 'log', '--format=%s'], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout
    return out.strip().splitlines()


def test_commit_creates_commit_with_canonical_subject(git_repo):
    (git_repo / 'src' / 'Easy' / '1.Two_Sum').mkdir(parents=True)
    (git_repo / 'src' / 'Easy' / '1.Two_Sum' / 'solution.ts').write_text('let x = 1;')
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', '1', '--tag', 'Easy', '--title', 'Two Sum'],
        cwd=git_repo, env=script_env(git_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert 'committed: 1. Easy. Two Sum' in result.stdout
    assert _git_log_subjects(git_repo)[0] == '1. Easy. Two Sum'


def test_commit_sql_uses_sql_tag(git_repo):
    (git_repo / 'src' / 'SQL' / '177.Nth_Highest_Salary').mkdir(parents=True)
    (git_repo / 'src' / 'SQL' / '177.Nth_Highest_Salary' / 'solution.sql').write_text('SELECT 1;')
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', '177', '--tag', 'SQL', '--title', 'Nth Highest Salary'],
        cwd=git_repo, env=script_env(git_repo),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert _git_log_subjects(git_repo)[0] == '177. SQL. Nth Highest Salary'


def test_commit_rejects_invalid_tag(git_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', '1', '--tag', 'Bogus', '--title', 'Two Sum'],
        cwd=git_repo, env=script_env(git_repo),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'invalid choice' in result.stderr.lower()


def test_commit_propagates_git_failure(git_repo):
    """No staged changes (and nothing untracked beyond what's already committed)
    → git commit exits non-zero."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         '--number', '1', '--tag', 'Easy', '--title', 'Two Sum'],
        cwd=git_repo, env=script_env(git_repo),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    # Subjects unchanged.
    assert _git_log_subjects(git_repo) == ['initial']
