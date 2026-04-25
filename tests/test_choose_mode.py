"""
Subprocess tests for scripts/pick/choose_mode.py.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys

import pytest

from conftest import PLUGIN_ROOT, script_env


SCRIPT = PLUGIN_ROOT / 'scripts' / 'pick' / 'choose_mode.py'


def _run(repo, *, seed=None):
    env = script_env(repo)
    if seed is not None:
        env['LEETCODE_PICK_SEED'] = str(seed)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo, env=env, capture_output=True, text=True,
    )


def _set_ratio(repo, ratio):
    (repo / 'config.json').write_text(json.dumps({'pick_retry_ratio': ratio}))


# ── boundary ratios ────────────────────────────────────────────────────────

@pytest.mark.parametrize('seed', [None, 1, 42, 999])
def test_ratio_zero_always_picks_new(practice_repo, seed):
    _set_ratio(practice_repo, 0.0)
    result = _run(practice_repo, seed=seed)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'new'


@pytest.mark.parametrize('seed', [None, 1, 42, 999])
def test_ratio_one_always_picks_retry(practice_repo, seed):
    _set_ratio(practice_repo, 1.0)
    result = _run(practice_repo, seed=seed)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'retry'


def test_default_ratio_when_no_config_picks_new(practice_repo):
    """No config.json → ratio defaults to 0.0 → always 'new'."""
    result = _run(practice_repo, seed=42)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'new'


# ── seed determinism ───────────────────────────────────────────────────────

def test_same_seed_same_outcome(practice_repo):
    _set_ratio(practice_repo, 0.5)
    a = _run(practice_repo, seed=12345).stdout.strip()
    b = _run(practice_repo, seed=12345).stdout.strip()
    assert a == b


def test_seeded_outcome_matches_python_random(practice_repo):
    """Verify seeding actually drives the choice — compute expected with
    the same seed in-test, and compare."""
    _set_ratio(practice_repo, 0.5)
    seed = 7
    rng = random.Random(seed)
    expected = 'retry' if rng.random() < 0.5 else 'new'
    result = _run(practice_repo, seed=seed)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_different_seeds_can_diverge(practice_repo):
    """At ratio=0.5, scanning 50 different seeds should yield both outcomes
    at least once — confirming seeding has real effect."""
    _set_ratio(practice_repo, 0.5)
    outcomes = {_run(practice_repo, seed=s).stdout.strip() for s in range(50)}
    assert outcomes == {'retry', 'new'}


# ── input validation ───────────────────────────────────────────────────────

def test_malformed_seed_errors(practice_repo):
    _set_ratio(practice_repo, 0.5)
    result = _run(practice_repo, seed='nope')
    assert result.returncode == 1
    assert 'must be int' in result.stderr


def test_blank_seed_treated_as_unset(practice_repo):
    _set_ratio(practice_repo, 0.0)
    env = script_env(practice_repo)
    env['LEETCODE_PICK_SEED'] = '   '
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=practice_repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'new'


def test_clamps_out_of_range_ratio(practice_repo):
    """db.load_pick_retry_ratio clamps to [0, 1]; verify end-to-end."""
    _set_ratio(practice_repo, 2.5)  # clamps to 1.0 → always retry
    result = _run(practice_repo, seed=42)
    assert result.stdout.strip() == 'retry'

    _set_ratio(practice_repo, -0.5)  # clamps to 0.0 → always new
    result = _run(practice_repo, seed=42)
    assert result.stdout.strip() == 'new'
