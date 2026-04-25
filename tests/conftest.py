"""
Shared pytest fixtures.

Every test that touches the lib gets a fresh practice repo at a tmp path:
LEETCODE_REPO env var set, .claude/ created, schema-baseline.sql applied.
The db module is reloaded so its module-level paths re-resolve.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parent.parent / 'plugins' / 'leetcode-workflow'


@pytest.fixture
def practice_repo(tmp_path, monkeypatch):
    """Yield a freshly-initialised practice repo path.

    The repo has .claude/practice.db created with the v0 baseline schema
    applied. config.json is absent — load_* helpers fall back to defaults
    unless a test writes a config.json itself.
    """
    monkeypatch.setenv('LEETCODE_REPO', str(tmp_path))
    import db
    importlib.reload(db)

    (tmp_path / '.claude').mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH)
    db.apply_baseline(conn)
    conn.close()
    return tmp_path


@pytest.fixture
def empty_repo(tmp_path, monkeypatch):
    """Yield a path with LEETCODE_REPO set but NO .claude/ — for testing
    the "not a leetcode-workflow repo" error path."""
    monkeypatch.setenv('LEETCODE_REPO', str(tmp_path))
    import db
    importlib.reload(db)
    return tmp_path


@pytest.fixture
def git_repo(practice_repo):
    """practice_repo + git init + initial commit so commit.py has a base
    to commit against. Author config is local to the test repo."""
    subprocess.run(['git', 'init', '-q', '--initial-branch=main'],
                   cwd=practice_repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                   cwd=practice_repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'],
                   cwd=practice_repo, check=True)
    subprocess.run(['git', 'config', 'commit.gpgsign', 'false'],
                   cwd=practice_repo, check=True)
    subprocess.run(['git', 'add', '.'], cwd=practice_repo, check=True)
    subprocess.run(['git', 'commit', '-q', '-m', 'initial'],
                   cwd=practice_repo, check=True)
    return practice_repo


def script_env(repo: Path) -> dict:
    """Env dict for invoking scripts as subprocesses — propagates the
    fixture's LEETCODE_REPO so lib/db.py resolves to the tmp dir."""
    env = dict(os.environ)
    env['LEETCODE_REPO'] = str(repo)
    return env
