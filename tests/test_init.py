"""
Subprocess tests for scripts/init/init.py.

The skill's interactive prompts (Steps 1-2 in init/SKILL.md) live in
prose for the model. Tests here cover the deterministic script side
only — payload validation, side effects, error paths.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

import pytest
from conftest import PLUGIN_ROOT, script_env

SCRIPT = PLUGIN_ROOT / 'scripts' / 'init' / 'init.py'


def _run(repo, payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=script_env(repo),
        input=json.dumps(payload), capture_output=True, text=True,
    )


def _default_payload(**over):
    base = {
        'language': {'extension': 'ts', 'name': 'typescript'},
        'retry_thresholds_minutes': {'Easy': 15, 'Medium': 30, 'Hard': 60},
    }
    base.update(over)
    return base


# ── happy path ─────────────────────────────────────────────────────────────

def test_init_succeeds_in_empty_dir(empty_repo):
    result = _run(empty_repo, _default_payload())
    assert result.returncode == 0, result.stderr
    assert 'init: created leetcode-workflow practice repo' in result.stdout
    assert 'schema_version = 0' in result.stdout


def test_init_creates_full_layout(empty_repo):
    _run(empty_repo, _default_payload())
    # .claude
    assert (empty_repo / '.claude' / 'practice.db').exists()
    assert (empty_repo / '.claude' / 'practice.sql').exists()
    # config + gitignore + readme
    assert (empty_repo / 'config.json').exists()
    assert (empty_repo / '.gitignore').exists()
    assert (empty_repo / 'README.md').exists()
    # src subdirs with .gitkeep
    for section in ('Easy', 'Medium', 'Hard', 'SQL'):
        assert (empty_repo / 'src' / section).is_dir()
        assert (empty_repo / 'src' / section / '.gitkeep').exists()
    # views
    for name in ('progress.md', 'timings.md', 'retry.md',
                 'patterns-coverage.md', 'history.md'):
        assert (empty_repo / name).exists()


def test_init_readme_links_to_plugin_repo_and_uses_language_ext(empty_repo):
    payload = _default_payload(language={'extension': 'py', 'name': 'python'})
    _run(empty_repo, payload)
    readme = (empty_repo / 'README.md').read_text()
    # Workflow refers to the user's chosen extension.
    assert 'solution.py' in readme
    assert '__EXT__' not in readme
    # Orchestration link present.
    assert 'https://github.com/lazyexpert/leetcode-workflow' in readme
    # Header is at the top.
    assert readme.startswith('# LeetCode Practice')
    # Orchestration section is at the bottom (after the config table).
    config_idx = readme.index('## Configuration')
    orch_idx   = readme.index('## Orchestration workflow')
    assert orch_idx > config_idx


def test_init_runs_git_init_when_no_dot_git(empty_repo):
    _run(empty_repo, _default_payload())
    assert (empty_repo / '.git').is_dir()


def test_init_skips_git_init_when_dot_git_present(empty_repo):
    """Pre-existing .git is allowed (and untouched)."""
    subprocess.run(['git', 'init', '-q'], cwd=empty_repo, check=True)
    head_before = (empty_repo / '.git' / 'HEAD').read_text()
    result = _run(empty_repo, _default_payload())
    assert result.returncode == 0, result.stderr
    assert (empty_repo / '.git' / 'HEAD').read_text() == head_before


def test_init_writes_config_with_user_input_and_defaults(empty_repo):
    payload = _default_payload(
        language={'extension': 'py', 'name': 'python'},
        retry_thresholds_minutes={'Easy': 10, 'Medium': 25, 'Hard': 50},
    )
    _run(empty_repo, payload)
    cfg = json.loads((empty_repo / 'config.json').read_text())
    assert cfg['language'] == {'extension': 'py', 'name': 'python'}
    assert cfg['retry_thresholds_minutes'] == {'Easy': 10, 'Medium': 25, 'Hard': 50}
    # Defaults
    assert cfg['review_cooldown_days'] == 7
    assert cfg['pick_retry_ratio']     == 0.0
    assert isinstance(cfg['patterns'], list) and len(cfg['patterns']) == 18


def test_init_normalises_language_input(empty_repo):
    """Extension stripped of leading dot, both fields lowercased."""
    payload = _default_payload(language={'extension': '.PY', 'name': 'Python'})
    _run(empty_repo, payload)
    cfg = json.loads((empty_repo / 'config.json').read_text())
    assert cfg['language'] == {'extension': 'py', 'name': 'python'}


def test_init_db_has_baseline_schema(empty_repo):
    _run(empty_repo, _default_payload())
    conn = sqlite3.connect(empty_repo / '.claude' / 'practice.db')
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert {'problems', 'attempts', 'patterns', 'thresholds', 'settings'} <= tables
        views = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view'"
        )}
        assert 'retry_flags' in views
        # schema_version seeded
        ver = conn.execute(
            "SELECT value FROM settings WHERE key = 'schema_version'"
        ).fetchone()
        assert ver == ('0',)
        # plugin_version_seen bumped to current plugin version (so the
        # update-nudge stays quiet until the next marketplace update).
        seen = conn.execute(
            "SELECT value FROM settings WHERE key = 'plugin_version_seen'"
        ).fetchone()
        import plugin_meta
        assert seen == (plugin_meta.plugin_version(),)
    finally:
        conn.close()


def test_init_mirrors_thresholds_to_db(empty_repo):
    payload = _default_payload(
        retry_thresholds_minutes={'Easy': 8, 'Medium': 22, 'Hard': 44},
    )
    _run(empty_repo, payload)
    conn = sqlite3.connect(empty_repo / '.claude' / 'practice.db')
    try:
        rows = dict(conn.execute('SELECT difficulty, minutes FROM thresholds'))
        assert rows == {'Easy': 8, 'Medium': 22, 'Hard': 44}
    finally:
        conn.close()


def test_init_writes_gitignore_with_practice_db(empty_repo):
    _run(empty_repo, _default_payload())
    gi = (empty_repo / '.gitignore').read_text()
    assert '.claude/practice.db' in gi
    # practice.sql must NOT be ignored — it's the git-tracked snapshot.
    assert 'practice.sql' not in gi


def test_init_renders_empty_views(empty_repo):
    _run(empty_repo, _default_payload())
    progress = (empty_repo / 'progress.md').read_text()
    assert progress.startswith('# Progress')
    assert '| **Total**  | **0** |' in progress
    timings = (empty_repo / 'timings.md').read_text()
    assert 'Easy ≥ 15 min · Medium ≥ 30 min · Hard ≥ 60 min' in timings


def test_init_dumps_sql(empty_repo):
    _run(empty_repo, _default_payload())
    sql = (empty_repo / '.claude' / 'practice.sql').read_text()
    assert 'CREATE TABLE' in sql
    assert "INSERT INTO settings" in sql
    assert "'schema_version','0'" in sql or "'schema_version', '0'" in sql


# ── refusal: non-empty cwd ─────────────────────────────────────────────────

def test_init_refuses_when_extra_file_present(empty_repo):
    (empty_repo / 'README.md').write_text('# pre-existing')
    result = _run(empty_repo, _default_payload())
    assert result.returncode == 1
    assert 'not empty' in result.stderr
    assert 'README.md' in result.stderr


def test_init_refuses_when_extra_subdir_present(empty_repo):
    (empty_repo / 'docs').mkdir()
    result = _run(empty_repo, _default_payload())
    assert result.returncode == 1
    assert 'not empty' in result.stderr


def test_init_allows_only_dot_git(empty_repo):
    """A pre-existing .git dir should not block init."""
    (empty_repo / '.git').mkdir()
    # Don't run actual git init — just verify presence of .git alone is OK.
    # (Real .git contents are unnecessary for the empty-cwd check.)
    (empty_repo / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
    result = _run(empty_repo, _default_payload())
    assert result.returncode == 0, result.stderr


# ── refusal: malformed input ───────────────────────────────────────────────

@pytest.mark.parametrize('payload,err_match', [
    ({}, 'language must be'),
    ({'language': {'extension': 'ts'}}, 'language must be'),
    ({'language': {'extension': 'ts', 'name': ''}}, 'language must be'),
    ({'language': {'extension': 'ts', 'name': 'typescript'}}, 'retry_thresholds_minutes'),
    ({'language': {'extension': 'ts', 'name': 'typescript'},
      'retry_thresholds_minutes': {'Easy': 15}}, 'retry_thresholds_minutes'),
    ({'language': {'extension': 'ts', 'name': 'typescript'},
      'retry_thresholds_minutes': {'Easy': 15, 'Medium': 30, 'Hard': -1}}, 'int>0'),
    ({'language': {'extension': 'ts', 'name': 'typescript'},
      'retry_thresholds_minutes': {'Easy': 15, 'Medium': 30, 'Hard': 'sixty'}}, 'int>0'),
])
def test_init_rejects_malformed_payload(empty_repo, payload, err_match):
    result = _run(empty_repo, payload)
    assert result.returncode == 1
    assert err_match in result.stderr


def test_init_rejects_malformed_json(empty_repo):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=empty_repo, env=script_env(empty_repo),
        input='not json', capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'malformed input JSON' in result.stderr


# ── end-to-end smoke ───────────────────────────────────────────────────────

def test_init_then_scaffold_new_works(empty_repo):
    """After init, scaffold_new.py should be able to land a problem
    against the freshly-created practice DB without further setup."""
    rc = _run(empty_repo, _default_payload()).returncode
    assert rc == 0

    scaffold = (PLUGIN_ROOT / 'scripts' / 'new' / 'scaffold_new.py')
    manifest = {
        'number': 1, 'title': 'Two Sum', 'difficulty': 'Easy',
        'type': 'algorithmic', 'statement': 'Given an array...\n',
    }
    result = subprocess.run(
        [sys.executable, str(scaffold)],
        cwd=empty_repo, env=script_env(empty_repo),
        input=json.dumps(manifest), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (empty_repo / 'src' / 'Easy' / '1.Two_Sum' / 'README.md').exists()
    progress = (empty_repo / 'progress.md').read_text()
    assert '1. Two Sum' in progress
