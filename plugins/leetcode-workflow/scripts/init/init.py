#!/usr/bin/env python3
"""
Initialise a fresh leetcode-workflow practice repo at the user's cwd.

Refuses if cwd contains anything other than .git. Runs `git init` if no
.git is present. Reads the resolved config on stdin so the SKILL.md can
prompt the user interactively before invoking the script — keeping all
prompting out of test scope.

Stdin (JSON):
  {
    "language": {"extension": "ts", "name": "typescript"},
    "retry_thresholds_minutes": {"Easy": 15, "Medium": 30, "Hard": 60}
  }

Both keys are required. Other config knobs (review_cooldown_days,
patterns, pick_retry_ratio) are written at their defaults — users tune
them later by editing config.json directly.

Side effects on the target repo:
  - git init (if .git absent)
  - .claude/practice.db created (baseline + migrations applied)
  - .claude/practice.sql dumped
  - config.json written
  - .gitignore written (practice.db ignored, practice.sql tracked)
  - src/{Easy,Medium,Hard,SQL}/ created with .gitkeep
  - five empty Markdown views rendered

Stdout: one or two lines on success.

Exit codes:
  0 success
  1 cwd not empty (excluding .git) / malformed input / I/O failure
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# Resolve target repo BEFORE importing db — db's module-level path
# resolution uses `git rev-parse` which would point at a parent git repo
# if the user happened to run init from a subdir of one. cwd is the
# right answer for init.
if 'LEETCODE_REPO' not in os.environ:
    os.environ['LEETCODE_REPO'] = str(Path.cwd().resolve())

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402
import migrate  # noqa: E402
import plugin_meta  # noqa: E402
import render  # noqa: E402


def _validate_input(data: dict) -> tuple[dict, dict] | None:
    lang = data.get('language')
    if (not isinstance(lang, dict)
            or not isinstance(lang.get('extension'), str)
            or not isinstance(lang.get('name'), str)
            or not lang['extension'].strip()
            or not lang['name'].strip()):
        print('ERROR: language must be {"extension": str, "name": str}',
              file=sys.stderr)
        return None
    lang = {
        'extension': lang['extension'].lstrip('.').lower(),
        'name':      lang['name'].lower(),
    }

    thr = data.get('retry_thresholds_minutes')
    if (not isinstance(thr, dict)
            or set(thr.keys()) != {'Easy', 'Medium', 'Hard'}
            or not all(isinstance(v, int) and v > 0 for v in thr.values())):
        print('ERROR: retry_thresholds_minutes must be '
              '{"Easy": int>0, "Medium": int>0, "Hard": int>0}',
              file=sys.stderr)
        return None
    return lang, thr


def _check_empty_cwd(repo: Path) -> bool:
    contents = sorted(p.name for p in repo.iterdir() if p.name != '.git')
    if contents:
        print(f'ERROR: target dir is not empty (found: {contents}). '
              f'/leetcode-workflow:init must run in an empty directory.',
              file=sys.stderr)
        return False
    return True


def _git_init_if_needed(repo: Path) -> bool:
    if (repo / '.git').exists():
        return True
    result = subprocess.run(
        ['git', 'init', '-q'], cwd=repo,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'ERROR: git init failed: {result.stderr.strip()}', file=sys.stderr)
        return False
    return True


def _initial_commit(repo: Path) -> bool:
    """Stage everything and create the scaffold commit. Soft-fails if git
    user config is missing — the practice repo is otherwise fully set up,
    the user just needs to commit manually after configuring git."""
    add = subprocess.run(
        ['git', 'add', '-A'], cwd=repo,
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        print(f'WARNING: git add failed: {add.stderr.strip()}', file=sys.stderr)
        return False
    commit = subprocess.run(
        ['git', 'commit', '-q', '-m', 'init: scaffold leetcode-workflow practice repo'],
        cwd=repo, capture_output=True, text=True,
    )
    if commit.returncode != 0:
        print(f'WARNING: git commit failed: {commit.stderr.strip()}', file=sys.stderr)
        print('         Files are staged but uncommitted. Configure git '
              '(git config --global user.email / user.name) then `git commit`.',
              file=sys.stderr)
        return False
    return True


GITIGNORE = """\
# leetcode-workflow
.claude/practice.db

# Python
__pycache__/

# OS
.DS_Store
"""


README_TEMPLATE = """\
# LeetCode Practice

A practice journal scaffolded by the
[leetcode-workflow](https://github.com/lazyexpert/leetcode-workflow) plugin.
SQLite (`.claude/practice.db`) is the source of truth; the five Markdown
views at the repo root are regenerated on every command.

## Workflow

1. `/leetcode-workflow:new <leetcode-url>` — scaffold a problem from a LeetCode URL.
2. Write your solution in `solution.__EXT__` (or `solution.sql` for database problems).
3. `/leetcode-workflow:done` — record timing, classify patterns, regenerate views, commit.

Other commands:

- `/leetcode-workflow:pick` — "what should I solve next?". Picks an under-covered pattern; with a non-zero `pick_retry_ratio`, sometimes routes to a retry instead.
- `/leetcode-workflow:retry [N]` — revisit a problem (random from the retry queue, or explicit by number).
- `/leetcode-workflow:abort` — drop the latest in-progress attempt.
- `/leetcode-workflow:update` — apply pending DB migrations after a plugin update.

## Generated views

| File | Shows |
|---|---|
| `progress.md` | Solved counts by difficulty + per-section problem lists. |
| `timings.md` | Per-attempt solve times against the configured thresholds. |
| `retry.md` | Algorithmic problems eligible for revisit + reason flags. |
| `patterns-coverage.md` | Coverage across algorithmic patterns. |
| `history.md` | Timeline of solves by month. |

Don't hand-edit these — the next command will overwrite them.

## Configuration

Edit `config.json` to tune:

| Key | Effect |
|---|---|
| `language` | Filename suffix and classifier code-fence hint. |
| `retry_thresholds_minutes` | Solve-time thresholds per difficulty. |
| `review_cooldown_days` | Staleness window for the retry queue. |
| `pick_retry_ratio` | Share of `/pick` invocations that route to retry instead of new (0..1). |
| `patterns` | Closed enum the pattern classifier picks from. |

---

## Orchestration workflow

This repo is managed by the
[leetcode-workflow](https://github.com/lazyexpert/leetcode-workflow) Claude Code plugin.
"""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f'ERROR: malformed input JSON: {e}', file=sys.stderr)
        return 1

    parsed = _validate_input(payload)
    if parsed is None:
        return 1
    language, thresholds = parsed

    repo = db.REPO
    if not _check_empty_cwd(repo):
        return 1
    if not _git_init_if_needed(repo):
        return 1

    # config.json — user's answers + defaults for everything else.
    config = {
        'language':                  language,
        'retry_thresholds_minutes':  thresholds,
        'review_cooldown_days':      db.DEFAULT_COOLDOWN_DAYS,
        'pick_retry_ratio':          db.DEFAULT_PICK_RETRY_RATIO,
        'patterns':                  list(db.DEFAULT_PATTERNS),
    }
    db.CONFIG.write_text(json.dumps(config, indent=2) + '\n')

    (repo / '.gitignore').write_text(GITIGNORE)
    (repo / 'README.md').write_text(
        README_TEMPLATE.replace('__EXT__', language['extension'])
    )

    for section in ('Easy', 'Medium', 'Hard', 'SQL'):
        d = repo / 'src' / section
        d.mkdir(parents=True, exist_ok=True)
        (d / '.gitkeep').write_text('')

    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        db.apply_baseline(conn)
        migrate.apply_pending(conn)
        db.sync_config(conn)
        # Mark current plugin version as seen so the nudge stays quiet
        # until the user's marketplace gets a real update.
        db.upsert_setting(conn, 'plugin_version_seen', plugin_meta.plugin_version())
        render.render_all(conn, repo)
        db.dump_sql(conn)
        final_version = migrate.current_version(conn)
    finally:
        conn.close()

    print(f'init: created leetcode-workflow practice repo at {repo}')
    print(f'      schema_version = {final_version}')
    if _initial_commit(repo):
        print('      initial commit created')
    return 0


if __name__ == '__main__':
    sys.exit(main())
