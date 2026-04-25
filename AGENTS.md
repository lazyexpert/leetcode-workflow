# AGENTS.md

Rules for coding agents (Claude Code, Cursor, Copilot, etc.) opening PRs against this repo. Humans should also read [CONTRIBUTING.md](CONTRIBUTING.md); this file augments it with the things agents most often get wrong.

If you are an agent working on this repo: read this file fully before editing anything beyond a typo. Read [CLAUDE.md](CLAUDE.md) for architecture before changing anything beyond a single function.

---

## Non-negotiables

These are hard rules. A PR that violates any of them will be rejected outright.

1. **Pedagogical contract.** The plugin is a coach, not a solver. No new code path may produce solution code, unless the user explicitly asks. This applies to: prompts in `commands/*.md`, signature templates in `scaffold_new.py`, classifier outputs, error messages, anywhere. If your change touches anything that displays content to the model, audit it for solution leakage. Tags from LeetCode are *also* suppressed (they leak pattern hints) — don't reintroduce them.

2. **No runtime Python dependencies.** The plugin scripts use stdlib + `sqlite3` only. Adding `requests`, `pydantic`, anything else — rejected. `requirements-dev.txt` is for the test/lint toolchain only and is not installed when the plugin runs in user repos.

3. **Scripts are deterministic. Prompts live in `commands/*.md`.** No LLM calls inside `scripts/`. If you need the model to classify, strip, summarize, suggest — that prompt belongs in `commands/<name>.md`, and the script consumes the model's output as structured input (JSON via stdin, or `--input <path>` for byte-exact data).

4. **Tests cover scripts only, not commands.** `commands/*.md` files are model-facing prose; we don't test them. Don't add `tests/test_<name>_command.py` or anything similar. Test the deterministic scripts that the command body invokes.

5. **Schema changes require a migration.** Don't edit `schema-baseline.sql` after v0 release. Add `migrations/000N_<short_desc>.sql` instead, wrapped in `BEGIN; ... COMMIT;`, ending with the `INSERT OR REPLACE INTO settings VALUES ('schema_version', '<N>')` advance. Bump `plugin.json: version` so the update nudge fires.

---

## Required pre-PR checks

Run all of these locally before opening a PR. CI will run them too, but discover failures locally — it's faster.

```bash
ruff check .                                            # lint
pytest -q                                               # 237 tests, all should pass
COVERAGE_PROCESS_START="$PWD/.coveragerc" \
  coverage run --rcfile=.coveragerc -m pytest \
  && coverage combine --rcfile=.coveragerc \
  && coverage report --rcfile=.coveragerc               # if you changed scripts
```

If any fail: do not open the PR. Fix them, or stop and ask the human for guidance.

---

## Working in this repo

### What you're allowed to touch freely

- `scripts/<name>/*.py` — deterministic logic, the bulk of behavior changes land here.
- `lib/*.py` — shared modules.
- `tests/*.py` — add tests for any behavior change.
- `commands/<name>.md` — orchestration prose. Edit carefully — this is what the user-facing model reads. Match the existing voice (terse, imperative, no emoji).
- `migrations/000N_*.sql` — additive only.
- Documentation (`README.md`, `CONTRIBUTING.md`, this file, `roadmap.md`).

### What requires a human decision first

- Adding a new command. Surface area is intentionally narrow. File an issue.
- Changing the seven-command list, command names, or the `/leetcode-workflow:<name>` invocation form.
- Anything in `.claude-plugin/marketplace.json` or `plugins/leetcode-workflow/.claude-plugin/plugin.json` beyond a version bump.
- `schema-baseline.sql` — frozen post-v0 release.
- Adding a CI workflow under `.github/workflows/` — the human is still designing the CI shape (see [roadmap.md](roadmap.md)).
- Bumping `plugin.json: version` outside of a migration PR.

### What you should never do

- Generate solution code that the user didn't ask for.
- Add LLM calls inside scripts (any `anthropic`, `openai`, etc. import in `scripts/` or `lib/` is wrong).
- Run `git push --force`, `git reset --hard`, or any destructive git operation against branches that aren't your own.
- Edit `.claude/practice.sql` or `.claude/practice.db` files in user practice repos — those are user data.
- Reformat files you're not otherwise changing. Style nits in unrelated diffs make review slow.
- Run `ruff format` repo-wide. The codebase uses intentional `=` alignment; the formatter would strip it. See CLAUDE.md "Linting".

---

## Conventions worth internalizing

- **Folder naming** in user repos: `src/<Easy|Medium|Hard|SQL>/<number>.<Title_With_Underscores>/`. Underscores, not spaces. Don't change this.
- **Cross-script imports**: `scripts/<name>/*.py` import from `lib/` via `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))`. Don't refactor this into a package — it works, and packaging adds install friction.
- **JSON over the wire**: scripts that take structured input read JSON from stdin or `--input <path>`. Multi-line / arbitrary-byte payloads (stripped solution bodies) use `--body-file <path>` to dodge shell-escaping fragility.
- **`from __future__ import annotations`** is at the top of every script and lib module. Keep it there even if the file targets 3.10+ — it's a defensive default.
- **`${CLAUDE_PLUGIN_ROOT}`** in `commands/*.md` — never hard-code paths there. The marketplace expands this at runtime.
- **`lib/nudge.py`** runs as the last step of every command body. If you add a command, add the nudge invocation. If you modify a command, don't delete the nudge.

---

## Commit and PR shape

- **Fork first if you don't have write access.** External contributors (and most agents acting on their behalf) need to fork `lazyexpert/leetcode-workflow`, push branches to the fork, and open PRs from `<fork>/branch` → `lazyexpert/leetcode-workflow:main`. See [CONTRIBUTING.md "Local setup"](CONTRIBUTING.md#local-setup) and ["Submitting a PR"](CONTRIBUTING.md#submitting-a-pr) for the full sequence — that's the canonical reference; don't reinvent the steps.
- One logical change per PR. If you find an unrelated bug while working, file an issue — don't bundle it.
- Imperative-mood commit subjects: `fix: detect_problem misses .sql`, `add: pick rolls against pick_retry_ratio`. Lower-case, terse, no period.
- PR description should explain *why*. The diff explains *what*. If you're using the PR template (you should), fill in the test plan honestly — "I ran pytest" is fine if you ran pytest; "I exercised /done in a scratch repo" if you did.
- If a human asks for changes, address them in new commits — don't force-push and rewrite history. The PR is squash-merged at the end anyway.

---

## When uncertain

Stop and ask. Open a comment on the issue, or push a draft PR with a question in the description. The plugin's shape is opinionated; getting alignment cheap is better than rewriting after review.

The human maintainer's primary architectural reference is [CLAUDE.md](CLAUDE.md). If your change requires updating CLAUDE.md, that's a strong signal it's a design-level change, not a routine fix — flag it explicitly in the PR description.
