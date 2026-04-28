---
description: Import problems from an existing LeetCode practice repo into the current (initialised) practice repo.
allowed-tools: Bash, Read, Write, WebSearch, WebFetch
---

Bring problems from a pre-existing LeetCode practice repo into the
current practice repo. The source repo is **read-only** — solution
files are copied verbatim, never modified, never deleted. The
destination is the current cwd, which must already be a fresh
`/leetcode-workflow:init` repo with no problems yet.

**Critical constraint: never write solution code, never hint at an
algorithm, approach, or complexity. Solution files are copied
verbatim from the source; you do not generate or alter their contents
at any point.**

---

## Step 0 — Guard

`$ARGUMENTS` must be a path to the source repo. If empty or the path
doesn't exist as a directory, stop and show:

> Usage: `/leetcode-workflow:import <path-to-source-repo>`

Resolve the path to absolute. Hold it as `<source>` for later steps.

---

## Step 1 — Preflight

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/import_repo/preflight.py
```

Exit codes:

- **0** — cwd is a fresh init'd practice repo, ready to import. Continue.
- **1** — not initialised. Tell the user to `/leetcode-workflow:init` in an empty directory first; stop.
- **2** — practice DB already has problems. /import is for empty practice repos. Tell the user to start fresh in another directory; stop.

---

## Step 2 — Walk the source

Walk `<source>` looking for solution files. Configured language
extension lives in `config.json: language.extension` (read it).

Common layouts to recognise (don't assume only these — work flexibly):

- `Easy/`, `Medium/`, `Hard/` directories with one folder per problem
- A flat list of `<N>.<Title>/solution.<ext>` folders
- Problems organised by pattern instead of difficulty
- Mixed: some folders have explicit numbers, some don't

A "candidate" is a folder containing a non-empty solution file. Empty
or whitespace-only solution files mean the problem was scaffolded but
never solved — **skip them silently**, but track the count.

### Languages

If the source contains solution files in **multiple languages** (e.g.
both `.py` and `.java`), pick the language to import:

1. Find the most recently modified solution file across the source.
   That language is the proposed default.
2. Tell the user:
   > Source has solutions in `<langs found>`. Most recent activity
   > is in `<lang>`. Import only `<lang>` solutions, or pick another?
3. Wait for the answer. Filter the candidate list to that language.

**If the chosen language does not match `config.json: language.extension`**,
stop and tell the user:

> Your practice repo is configured for `<configured>`, but you want to
> import `<chosen>` solutions. Edit `config.json: language` to match,
> then rerun `/leetcode-workflow:import`.

### Source plausibility

If after walking and language filtering you have **zero candidates**,
stop with:

> `<source>` does not look like a LeetCode practice repo (no
> `solution.<ext>` files found). Aborting.

Do not loop the user through "describe your structure" — if it doesn't
look like an LC repo, /import is the wrong tool.

---

## Step 3 — Recover problem numbers

For each candidate, try to parse a problem number from the folder name
(common patterns: `1.Two_Sum`, `001-two-sum`, `0001-two-sum`,
`two-sum-1`). Track which candidates have a confident number and which
don't.

**If any candidate has no parseable number**, stop and present the
list to the user with two options:

> Couldn't determine problem numbers for these folders:
>   - `<folder1>`
>   - `<folder2>`
>   ...
> Two options:
>   (A) Reply with explicit `<folder> = <number>` mappings
>   (B) Spend tokens to identify them — I'll match the title to LC's
>       problem index for each
> Which option, A or B?

On (A): wait for mappings, apply.
On (B): for each unnumbered folder, derive a slug from the folder name
(lowercase, hyphens for spaces) and run `fetch.py` (Step 4) on that
slug — the manifest's `number` field gives you the LC frontend ID.

Do not silently fall back to (B) — getting the number wrong would
import the wrong problem, which is worse than asking.

---

## Step 4 — Fetch metadata from LeetCode

For each numbered candidate, derive a slug (lowercase folder name,
hyphenated, leading number stripped) and run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new/fetch.py "<slug>" --out /tmp/leetcode-workflow-import-<slug>.json
```

Per-problem manifest path so concurrent calls don't collide.

Interpret exit codes:

- **0** — manifest written. Continue.
- **1** — slug not found. Mark as `failed-lookup` (the slug derivation
  was wrong). Try a small set of alternative slug forms (e.g. dropping
  trailing `-ii`/`-iii`, removing leading-number prefixes, the title
  with hyphens). After 3 attempts, mark `failed-lookup` and move on.
- **2** — premium problem. Go to **Step 4b** (web fallback).
- **3** — network failure. Retry up to **3 times** with a short
  pause. After the 3rd failure, mark as `failed-network` and move on.

After Step 4, you have:

- `succeeded`: list of (candidate, manifest path) pairs
- `premium`:   list of candidates whose LC manifest was paywalled
- `failed-lookup`, `failed-network`: lists of candidates we couldn't resolve

---

## Step 4b — Web fallback for premium problems

For each premium problem, attempt to recover the statement from the
public web (NeetCode, mirror sites, blog write-ups):

1. WebSearch with a query like `leetcode <number> <title> problem statement`.
2. Pick the most authoritative result (NeetCode, Reddit r/leetcode,
   well-known mirror sites). Avoid AI-generated summary blogs.
3. WebFetch it. Extract: title (canonical LC casing), difficulty,
   problem statement (markdown).
4. Build a manifest dict by hand:
   ```json
   {
     "number": <int>,
     "title": "<canonical>",
     "difficulty": "Easy" | "Medium" | "Hard",
     "type": "algorithmic",
     "statement": "<markdown>",
     "signature": ""
   }
   ```
   and write it to `/tmp/leetcode-workflow-import-<slug>.json`.

If WebSearch + WebFetch don't produce a usable statement after 2
attempts, mark the candidate as `failed-premium` and move on.

---

## Step 5 — Recover started_at per problem

For each successfully-resolved problem, run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/import_repo/git_first_commit.py "<absolute-path-to-source-solution-file>"
```

Stdout is a unix integer (commit time of first commit touching the
file, or file mtime if source isn't a git repo). Hold it as the
problem's `started_at`.

---

## Step 6 — Pattern decision

Ask the user:

> Classify patterns for all `<N>` imported problems? Costs roughly
> `<N>` model calls. Or skip — coverage shows up as a gap on
> `patterns-coverage.md`, fill via `/leetcode-workflow:retry` later.

If **skip**: every problem's `patterns` is `[]`.

If **classify**: read each problem's source solution file (use the
**Read** tool). Apply the pattern classifier prompt from
`commands/done.md` Step 3 (paste it inline — same prompt, same closed
enum from `config.json: patterns`). Validate each returned label
against the closed enum; drop labels not in the enum with a warning.
Record the resolved `patterns` list per problem.

---

## Step 7 — Build manifest, present plan

Assemble the bulk_seed manifest:

```json
{
  "problems": [
    {
      "number":          <int>,
      "title":           "<from LC or web fallback>",
      "difficulty":      "Easy" | "Medium" | "Hard",
      "type":            "algorithmic" | "SQL",
      "statement":       "<from LC or web>",
      "started_at":      <Step 5 ts>,
      "patterns":        [<Step 6 labels>],
      "solution_source": "<absolute path to source solution file>"
    },
    ...
  ]
}
```

Save to `/tmp/leetcode-workflow-import-manifest.json` (use the **Write** tool).

Present a short plan to the user:

> Importing `<N>` problems: `<E>` Easy / `<M>` Medium / `<H>` Hard / `<S>` SQL.
> Patterns: `<classified | skipped>`.
> `started_at` sourced from `<git log | file mtime>`.
> `duration_minutes` left NULL (no historical timing).
> Files copied to `src/<D>/<N>.<Title>/solution.<ext>`.
> Skipping `<K>` empty / unresolved candidates: `<list>`.
> No git commit — review with `git diff`, commit when ready.
> Proceed?

Wait for explicit confirmation. If the user wants changes, adjust and
present again.

---

## Step 8 — Run bulk_seed

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/import_repo/bulk_seed.py \
    --input /tmp/leetcode-workflow-import-manifest.json
```

Exit codes:

- **0** — imported. stdout reports the count.
- **1** — bulk_seed failed (validation error, I/O failure, or precondition
  drift). Surface stderr to the user verbatim.

---

## Step 9 — Report

Print one short paragraph:

> Imported `<N>` problems. Skipped `<K>`: `<short list of reasons>`.
> Run `git diff` to review the changes, then `git add . && git commit
> -m "import: existing practice repo (<N> problems)"` when ready.

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed
anything, append the output verbatim on a new line.

Do not summarise the imported problems by content. Do not suggest
approaches. Do not mention complexity.
