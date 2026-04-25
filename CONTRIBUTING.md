# Contributing to leetcode-workflow

Thanks for considering a contribution. This guide covers the practical bits — what to install, how to run things locally, what we expect in a PR. Architectural context lives in [CLAUDE.md](CLAUDE.md); read that first if you're touching anything beyond a typo fix.

If you're a coding agent (Claude Code, Cursor, etc.), also read [AGENTS.md](AGENTS.md) — it has the agent-specific rules.

---

## What kind of contributions are welcome

- **Bug fixes.** Always welcome. File an issue first if the bug is non-obvious so we can confirm it's a bug before you sink time into a fix.
- **Documentation improvements.** README, CLAUDE.md, command help text, error messages. Low-friction PRs.
- **Test coverage.** The baseline is ~95%. PRs that lift uncovered branches without adding scope are great.
- **New features.** Open an issue first. The plugin's surface is intentionally small (seven commands); we add carefully. Look at [roadmap.md](roadmap.md) for things already on the radar.
- **New patterns in the default classifier list.** Small PR, just edit `lib/db.py: DEFAULT_PATTERNS` and add a regression test.

What we'll likely **decline**:

- Heavy abstractions or framework rewrites of working scripts.
- Adding runtime Python dependencies (the plugin is stdlib-only on purpose — install friction matters). Dev dependencies are fine.
- Generating solution code from the plugin. The pedagogical contract is non-negotiable: Claude is a coach, not a solver. See CLAUDE.md "Pedagogical contract".
- Cosmetic reformatting of files you're not otherwise changing.

---

## Local setup

You'll need Python 3.10+ and git. macOS and Linux are tested; Windows likely needs minor path tweaks.

```bash
git clone https://github.com/lazyexpert/leetcode-workflow
cd leetcode-workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

That installs `pytest`, `coverage`, and `ruff`. The plugin scripts themselves have no runtime Python deps — `requirements-dev.txt` is for the test/lint toolchain only.

### Running the suite

```bash
pytest -q                          # 237 tests, ~7s
pytest tests/test_db.py -v         # one file
pytest -k "atomicity"              # filter
ruff check .                       # lint
```

Coverage (run before opening a PR if you've changed scripts):

```bash
rm -f .coverage .coverage.*
COVERAGE_PROCESS_START="$PWD/.coveragerc" \
  coverage run --rcfile=.coveragerc -m pytest
coverage combine --rcfile=.coveragerc
coverage report --rcfile=.coveragerc
```

The coverage setup is subprocess-aware — most tests run scripts via `subprocess.run`. See CLAUDE.md "Coverage" for how the wiring works.

### Dogfooding the plugin

```
/plugin marketplace add /absolute/path/to/this/repo
/plugin install leetcode-workflow@leetcode-workflow
/plugin marketplace update leetcode-workflow   # after each local change
```

Then in a separate scratch directory: `mkdir scratch-practice && cd scratch-practice && claude` and run `/leetcode-workflow:init`.

---

## Filing an issue

We use GitHub Issues for both bugs and feature requests. Templates are provided — please use them. The bug template asks for:

- The command you ran (`/leetcode-workflow:done`, etc.)
- Expected vs actual behavior
- Plugin version (from `.claude-plugin/plugin.json` or `cat .claude/practice.sql | grep plugin_version`)
- Python version, OS
- Steps to reproduce on a fresh repo if possible

For feature requests, describe the problem first and the proposed solution second. We're more likely to accept "here's a workflow gap" than "here's a feature spec."

---

## Submitting a PR

### Branch

Branch from `main`. Name it descriptively: `fix/done-empty-solution-crash`, `feat/coverage-gaps-rendering`, `docs/init-prompt-clarity`. No strict convention, just be terse.

### Before you push

1. **Tests pass.** `pytest -q` should be green.
2. **Lint is clean.** `ruff check .` should report `All checks passed`. `ruff check . --fix` handles most things automatically.
3. **Coverage didn't drop.** Run the coverage block above. If you added a script, it should be exercised by at least one test.
4. **Schema changes have a migration.** If you touched anything in the DB shape, add `migrations/000N_<short_desc>.sql` and bump `plugin.json: version`. See "Adding a migration" in CLAUDE.md.
5. **Pedagogical contract preserved.** No new code path can produce solution code unless the user explicitly asks. If your change touches the model-facing prose in `commands/*.md`, double-check that.

### PR description

Use the template — it's short. Lead with *what problem this solves*, not *what code I changed* (the diff shows the latter). One paragraph for context, a checklist of what was tested, and a link to the issue if there is one.

### Commit messages

Imperative mood, lower-case, terse:

```
fix: detect_problem misses .sql files when language is python
add: pick command rolls against pick_retry_ratio for retry routing
docs: clarify init prompt for default thresholds
```

The `{N}. {Easy|Medium|Hard|SQL}. {Title}` format you see in user practice repos is generated by `/done` — that's for *user* commits in *their* practice repos, not for commits in this plugin repo.

We squash-merge PRs by default, so feel free to leave WIP commits — the merged commit will use your PR title.

### Review

One maintainer review is required. Expect feedback that pushes toward smaller, more orthogonal changes. The plugin's surface is intentionally narrow; "scope creep" is the most common reason a PR gets sent back.

---

## Adding a command (advanced)

This is rare — we have seven and don't expect to grow much. If you've thought it through and want to propose one:

1. Open an issue first. Describe the workflow gap and what command shape you have in mind.
2. If we agree on the shape, follow CLAUDE.md "Adding a command":
   - `commands/<name>.md` (orchestration prose, frontmatter with `description` + `allowed-tools`)
   - `scripts/<name>/` (deterministic Python, no LLM calls inside)
   - Tests under `tests/test_<name>_*.py`
   - The `nudge.py` invocation at the end of the command body
3. PR includes all of the above plus a one-line update to `commands/init.md` README template if the command is user-facing.

---

## Code of conduct

Be kind. Disagree on technical merits, never on people. We don't have a formal CoC document yet — open an issue if you'd like one drafted, or if you experience anything that warrants one.

---

## License

By contributing, you agree your contributions will be licensed under the [MIT License](LICENSE).
