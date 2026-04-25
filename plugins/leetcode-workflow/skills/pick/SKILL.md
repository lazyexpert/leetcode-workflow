---
name: pick
description: >
  Decide what to solve next. By default suggests a fresh LeetCode problem
  targeting a pattern the user has under-covered; with non-zero
  pick_retry_ratio, occasionally routes to the retry pool instead.
  Either way, ends with the problem ready to solve. Invoked as
  /leetcode-workflow:pick.
allowed-tools: Bash, Read
---

# pick

The "what should I solve next" command. Removes the friction of finding a
fresh LeetCode URL — picks one targeting an under-covered pattern,
mixing in retry-eligible old problems based on `pick_retry_ratio`.

**Critical constraint: never write solution code, never hint at an
algorithm, approach, or complexity.**

---

## Step 1 — Decide the mode

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/pick/scripts/choose_mode.py
```

Stdout is a single word: `retry` or `new`. Branch accordingly.

---

## Step 2a — Retry path (`mode == "retry"`)

Run the same flow as `/leetcode-workflow:retry` with no argument. The
mechanics live in `${CLAUDE_PLUGIN_ROOT}/skills/retry/SKILL.md`; the
short version:

1. `python3 ${CLAUDE_PLUGIN_ROOT}/skills/retry/scripts/pick_problem.py` → JSON.
2. Read `solution_path`, ask the model to strip the body to a signature-only template (use the same prompt as `retry/SKILL.md`).
3. Pipe `{"number": N, "body_text": "<stripped>"}` into `${CLAUDE_PLUGIN_ROOT}/lib/apply_solution_template.py`.
4. Skip to Step 3.

If `pick_problem.py` exits 1 with "No retry candidates outside the cooldown window", fall through to the new path (Step 2b) instead — the user asked for `/pick`, an empty retry pool shouldn't leave them empty-handed.

---

## Step 2b — New path (`mode == "new"`)

### 2b.1 — Read coverage gaps

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/pick/scripts/coverage_gaps.py
```

Stdout: `{"gaps": [{"pattern": "...", "count": int}, ...], "solved_numbers": [...]}`.

### 2b.2 — Suggest a problem URL

Pick a LeetCode problem to solve. Constraints:

- Target one of the **lowest-count gaps** (prefer `count == 0` patterns when present).
- The problem's frontend number must **not** be in `solved_numbers`.
- Prefer well-known, non-premium problems — premium ones fail at fetch with exit 2.
- Output a single LeetCode problem URL on its own line, e.g. `https://leetcode.com/problems/two-sum/`.

### 2b.3 — Fetch and scaffold

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/new/scripts/fetch.py "<url>" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/skills/new/scripts/scaffold_new.py
```

Interpret `fetch.py`'s exit code:

- **0** — manifest flowed into `scaffold_new.py`. On its exit 0, stdout prints `scaffold: created <path>`. Continue.
- **1, 2, 3** — slug not found / premium / network. Pick a different problem from a different gap and retry. Give up after **3 attempts** and surface the latest stderr to the user.

If `scaffold_new.py` exits 1 with "already has content", you accidentally picked a duplicate (`solved_numbers` should have prevented this); pick again.

---

## Step 3 — Report

Print one short line:

- After retry path: `Ready to retry {N}. {Title} ({Difficulty}) — {reason+...}.` (drop the trailing ` — …` if reasons are empty).
- After new path: `Job's done. {N}. {Title} ({Difficulty}) — targets {pattern}.`

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise the problem. Do not suggest approaches. Do not mention complexity.
