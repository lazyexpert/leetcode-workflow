# Extraction plan: `~/develop/leetcode` → `~/develop/leetcode-workflow`

Living plan for porting the prototype into marketplace shape. Updates as phases land.

## Goals

1. **Skills are thin orchestrators.** SKILL.md drives the lifecycle and contains every Claude prompt inline. Scripts do deterministic work only.
2. **Scripts are small, single-purpose CLIs.** stdin/stdout/exit codes; no LLM calls. Each one is unit-testable as a black box.
3. **Tests cover scripts only.** SKILL.md is prose for the model — no test surface.
4. **Migrations infra and `/update` shipped intentionally**, not bolted on later.

## What changes vs. the prototype

| Prototype | New shape |
|---|---|
| `done.py` (273 LOC, monolithic, embeds `claude -p` classify call) | Split into `detect_problem.py` + `record_attempt.py` + `render_and_dump.py` + `commit.py`. Classify prompt moves into `done/SKILL.md`. |
| `db.py:strip_solution_body` (subprocess `claude -p`) | Removed from lib. `prepare_retry` accepts "stripped code or empty" as input. Strip prompt moves into `retry/SKILL.md` and `new/SKILL.md` (reiteration path). |
| `scaffold.py` handles both new and reiteration modes (calls `prepare_retry` → strip) | Split: `scaffold_new.py` (folder + readme + empty file + DB rows) and `apply_solution_template.py` (writes stripped/empty solution + opens attempt). SKILL.md branches between them. |
| `retry.py` calls `prepare_retry` → strip internally | Split: `pick_problem.py` (prints JSON), then SKILL.md reads file, asks model to strip, pipes to `apply_solution_template.py`. |
| `abort.py` — fully deterministic | Port as-is. |
| `migrate.py` (one-shot prototype migration) | Repurposed only as reference. New `update.py` is a generic `migrations/000N_*.sql` runner driven by `settings.schema_version`. |
| Schema versioning absent in prototype | `schema-baseline.sql` seeds `settings.schema_version=0` and `plugin_version_seen`. |

## Phase 0 — Skeleton + manifests

- `.claude-plugin/marketplace.json` (lists the one plugin)
- `plugins/leetcode-workflow/.claude-plugin/plugin.json` (lists seven skills, `version: "0.0.1"`)
- Empty dirs: `skills/{init,new,pick,done,retry,abort,update}/`, `lib/`, `migrations/`
- Local install via `/plugin marketplace add ~/develop/leetcode-workflow` for dogfooding

> Note: the plan adds a seventh skill (`pick`) that the prototype doesn't have. Repo's `CLAUDE.md` still says "six skills" — fix as part of Phase 8.

## Phase 1 — Lib core + frozen baseline

- Port prototype `schema.sql` → `plugins/leetcode-workflow/schema-baseline.sql`. Add at the bottom: `INSERT INTO settings VALUES ('schema_version','0'), ('plugin_version_seen','');`. Freeze.
- Port `db.py` → `lib/db.py` minus `strip_solution_body`. `prepare_retry` becomes pure: takes `(conn, number, body_text)` — caller passes the stripped body (or `""` for wipe).
- Port `render.py` → `lib/render.py` unchanged.
- Path resolution: `git rev-parse --show-toplevel`, with `LEETCODE_REPO` env override (makes tests trivial).
- Tests: db helpers (upsert/start/complete/replace/sync), render golden-files against fixed DB fixtures.

## Phase 2 — Decompose `done` and `new`

`done/SKILL.md` orchestrates:

```
1. detect_problem.py        → {number, title, difficulty, path, kind} (or exit 1)
2. if kind=algorithmic: read the file, classify it inline using the prompt below
   (returns {patterns: [...], revisit: bool})
3. record_attempt.py < {problem + classification}   → prints timing/complexity verdict
4. render_and_dump.py
5. commit.py {number} {tag} {title}
```

The classifier prompt + closed pattern enum live in `done/SKILL.md`. The model parses the solution and emits JSON directly into the next script's stdin.

`new/SKILL.md` orchestrates:

```
1. fetch.py <url>           → manifest JSON
2. detect_reiteration.py    → "new" | "reiterate"
3a. new      → scaffold_new.py < manifest
3b. reiter   → read solution file, strip it inline using the prompt below,
               pipe stripped body to apply_solution_template.py
```

Tests: each new script invoked via subprocess with stdin fixtures; assertions on exit code + stdout JSON + DB state.

## Phase 3 — `retry` and `abort`

- `retry/SKILL.md`: `pick_problem.py [N]` → read file → strip via inline prompt → `apply_solution_template.py`
- `abort/SKILL.md`: just runs `abort.py` (no Claude needed). Port verbatim from prototype, swap import paths.
- Tests: `pick_problem.py` random/explicit modes, `apply_solution_template.py` writes file + opens attempt, `abort.py` sole-attempt vs prior-attempt branches.

## Phase 4 — `pick` (new skill, not in prototype)

The "what should I solve next" command. Removes the friction of finding a fresh problem URL on leetcode.com — pick suggests one targeting under-covered patterns, optionally mixing in retry-eligible old problems based on a configurable ratio.

`pick/SKILL.md` orchestrates:

```
1. choose_mode.py             → "retry" | "new"   (rolls against config.pick_retry_ratio)
2a. retry path  → same as /retry no-arg: pick_problem.py | strip via inline prompt
                  | apply_solution_template.py
2b. new path:
    - coverage_gaps.py        → JSON: {gaps: ["pattern", ...], solved_numbers: [...]}
    - model picks a LeetCode URL targeting one of `gaps`, whose problem number
      is NOT in `solved_numbers`, using the inline prompt
    - fetch.py <url> | scaffold_new.py
    - if fetch.py exits non-zero (bad slug / premium / network) → re-prompt the
      model up to 3 times, then surface the error
```

- `choose_mode.py`: reads `config.json: pick_retry_ratio` (float 0–1, default 0.0). Rolls a uniform random; emits `"retry"` if `roll < ratio`, else `"new"`. Honors `LEETCODE_PICK_SEED` env var for deterministic tests.
- `coverage_gaps.py`: queries DB for pattern counts, returns the bottom-N patterns (least solved) plus the full list of `problems.number` so the model can dedupe. Pure SQL, no LLM.
- New config key: `pick_retry_ratio: 0.0` — added to `lib/db.py` defaults and to the documented `config.json` shape.
- The retry path reuses Phase 3's `pick_problem.py` + `apply_solution_template.py` verbatim — no duplication.
- The new path reuses Phase 2's `fetch.py` + `scaffold_new.py` verbatim — pick is purely the picker layer.
- Tests: `choose_mode.py` with seeded RNG (ratio=0 always-new, ratio=1 always-retry, ratio=0.5 roughly even with deterministic seed); `coverage_gaps.py` against a fixture DB (low-count patterns surface first; solved-numbers list is complete). Pick's SKILL.md orchestration itself is not tested.

## Phase 5 — `init`

- New skill. Refuses if cwd has anything but `.git`. `git init` if needed.
- **Interactive setup** — `init/SKILL.md` asks the user two questions before scaffolding, so a fresh user gets a working `config.json` without hand-editing:
  1. **Language.** "Which language do you solve in? (default: TypeScript)" — accepts a free-form name; the model maps it to `{extension, name}` from a known list (TypeScript→ts/typescript, Python→py/python, Go→go/go, Java→java/java, C++→cpp/cpp, JavaScript→js/javascript, Rust→rs/rust, Kotlin→kt/kotlin, Swift→swift/swift, Ruby→rb/ruby). Unknown answer → ask again with the list shown.
  2. **Timing thresholds.** "Default retry thresholds are Easy 15 / Medium 30 / Hard 60 minutes. Press enter to accept, or type three numbers to override (e.g. `10 25 50`)." Empty input → defaults; otherwise validate three positive ints.
  3. **Patterns** and **`pick_retry_ratio`** stay default (the 18-item pattern list; `pick_retry_ratio: 0.0`). Mentioned in the final "you can edit `config.json` later" line, but not prompted for — advanced tuning, not first-run friction.
- After answers, `init.py` receives the resolved config as JSON on stdin (or args), writes `config.json`, creates `.claude/`, `src/{Easy,Medium,Hard,SQL}/`, applies `schema-baseline.sql` + every `migrations/000N_*.sql` in order, renders empty views, dumps SQL, writes `.gitignore`.
- Tests cover `init.py` only (script side), with the resolved config supplied directly — interactive prompting lives in SKILL.md and is out of test scope per the testing rule. Cases: empty cwd succeeds; non-empty cwd refuses; defaults config produces the documented `config.json`; custom config is honored verbatim; baseline + all migrations applied; `settings.schema_version` matches highest migration number.

## Phase 6 — Migrations infra + `update`

- `update.py` reads `settings.schema_version`, applies pending `migrations/000N_*.sql` in order (each wrapped `BEGIN;…COMMIT;`, last statement bumps `schema_version`). Renders views. Dumps SQL. Bumps `plugin_version_seen` to the plugin manifest's current version.
- `init` and `update` share the migration runner — single function in `lib/migrate.py`.
- Add a deliberate test migration (`migrations/0001_test_noop.sql` or use a real first one when the schema first changes) to exercise the runner end-to-end. Until then, tests stub it with a fixture migration in a tmp dir.
- Tests: from-baseline upgrade, partial-state upgrade (skip already-applied), idempotency, version stamping, atomicity (failed migration leaves DB unchanged).

## Phase 7 — Update nudge

- `lib/nudge.py:print_if_outdated()` — reads plugin.json `version`, compares to `settings.plugin_version_seen`, prints `ⓘ leetcode-workflow updated to vN — run /leetcode-workflow:update to apply migrations` if different.
- Last line of every SKILL.md (except `init` and `update`) calls it.
- `update.py` is the only writer of `plugin_version_seen`.
- Tests: nudge fires when versions differ, silent when equal, silent on empty (fresh init).

## Phase 8 — Manifests filled in + README

- Fill `plugin.json` with all seven skill entries, `version: "0.1.0"` for first tagged release.
- Update root `README.md` install instructions to match `/plugin marketplace add lazyexpert/leetcode-workflow` flow.
- Update `CLAUDE.md`: bump "six skills" → "seven skills" (everywhere), document `pick` in the skills table, add `pick_retry_ratio` to the config table, remove the "Porting tasks" section (that's done) and replace with a maintenance section.

## Phase 9 — Dogfood

Manual validation in a throwaway directory: install the marketplace from local path, run the full lifecycle (`init` → `new <url>` → solve → `done` → `pick` (default new path) → solve → `done` → `pick` with `pick_retry_ratio: 1.0` (force retry path) → `abort` → `retry`), and verify the views/DB/git state look right at each step. Not automated; SKILL.md isn't unit-testable.

## Test layout

```
tests/
  conftest.py                     # tmp practice repo fixture, baseline applied
  test_db.py
  test_render.py                  # golden-file MD diffs
  test_migrate.py
  test_init.py
  test_fetch.py
  test_scaffold_new.py
  test_apply_solution_template.py
  test_detect_problem.py
  test_record_attempt.py
  test_pick_problem.py
  test_choose_mode.py
  test_coverage_gaps.py
  test_abort.py
  test_nudge.py
fixtures/
  problem-graphql-twosum.json     # captured GraphQL response for fetch tests
  practice-baseline.sql           # tiny pre-seeded DB for view tests
  golden/                         # expected MD output snapshots
```

pytest only, stdlib only (`subprocess`, `sqlite3`, `pathlib`, `tmp_path`). No conftest pollution beyond a single `practice_repo` fixture that returns a `Path` with `.claude/practice.db` baselined.

## Order of operations

Phases 0–3 are the bulk of the port and unblock dogfooding the lifecycle that already works in the prototype. Phase 4 (`pick`) is the only fully net-new behavior in the v0.1.0 surface — leans on Phase 2 + 3 primitives, so it slots in cheaply once those land. Phase 5 (`init`) is needed before anyone else can use the plugin. Phases 6–7 are the "update story" (migrations + nudge) before the v0.1.0 tag. Phase 8 is manifest cleanup; Phase 9 is the final hands-on smoke test.

## Risks

- Inline strip/classify prompts depend on the model returning strict JSON. The prototype was already filtering hallucinated patterns and JSON failures; SKILL.md needs the same defensive prose ("respond with ONLY this exact JSON shape, no fences, no commentary"). Worth lifting verbatim from `done.py` lines 124-134.
- `prepare_retry` taking pre-stripped body changes the lib's API surface. Worth keeping the function name + signature stable from the start, since it's the core lifecycle primitive.
