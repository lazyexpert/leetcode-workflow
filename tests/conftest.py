"""
Shared pytest fixtures.

Every test that touches the lib gets a fresh practice repo at a tmp path:
LEETCODE_REPO env var set, .claude/ created, schema-baseline.sql applied.
The db module is reloaded so its module-level paths re-resolve.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest


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
