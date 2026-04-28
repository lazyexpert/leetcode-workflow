"""
Shared pytest fixtures.

Every test that touches the lib gets a fresh practice repo at a tmp path:
LEETCODE_REPO env var set, .claude/ created, baseline + all shipped
migrations applied — i.e. the real schema state of an init'd repo.
The db module is reloaded so its module-level paths re-resolve.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / 'plugins' / 'leetcode-workflow'


# Subprocess coverage: when COVERAGE_PROCESS_START is set (by `coverage run`
# or by CI), ensure repo root is on PYTHONPATH so subprocess Python loads
# sitecustomize.py and starts measurement before any user code runs. Also
# pin COVERAGE_FILE to an absolute path so subprocess data files land in
# the repo root regardless of the subprocess's cwd. No-op outside coverage.
if os.environ.get('COVERAGE_PROCESS_START'):
    _pp = os.environ.get('PYTHONPATH', '')
    _parts = _pp.split(os.pathsep) if _pp else []
    if str(REPO_ROOT) not in _parts:
        os.environ['PYTHONPATH'] = os.pathsep.join([str(REPO_ROOT), *_parts]) if _parts else str(REPO_ROOT)
    os.environ.setdefault('COVERAGE_FILE', str(REPO_ROOT / '.coverage'))


@pytest.fixture
def practice_repo(tmp_path, monkeypatch):
    """Yield a freshly-initialised practice repo path.

    The repo has .claude/practice.db created with the v0 baseline +
    every shipped migration applied — i.e. the real schema state of an
    init'd practice repo. config.json is absent; load_* helpers fall
    back to defaults unless a test writes a config.json itself.

    Tests that specifically need baseline-only state (e.g. migration
    runner tests verifying an upgrade path) should set that up inline
    rather than relying on this fixture.
    """
    monkeypatch.setenv('LEETCODE_REPO', str(tmp_path))
    import db
    importlib.reload(db)
    import migrate
    importlib.reload(migrate)

    (tmp_path / '.claude').mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH)
    db.apply_baseline(conn)
    migrate.apply_pending(conn)
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
def baseline_repo(tmp_path, monkeypatch):
    """Yield a practice repo with ONLY the v0 baseline applied (no
    migrations). Use this for migration-runner tests that need to start
    at schema_version = 0 and apply fixture migrations of their own.
    Most tests should prefer `practice_repo` instead."""
    monkeypatch.setenv('LEETCODE_REPO', str(tmp_path))
    import db
    importlib.reload(db)

    (tmp_path / '.claude').mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH)
    db.apply_baseline(conn)
    conn.close()
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
