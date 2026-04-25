---
name: done
description: >
  Complete the in-progress LeetCode problem — finalise its timing, classify
  its pattern(s), update the retry queue, regenerate views, and commit.
  Push is left to the user. Invoked as /leetcode-workflow:done.
allowed-tools: Bash, Read
---

# done

Closes the lifecycle for whichever problem currently has a modified or
untracked non-empty solution file under `src/`.

**Critical constraint: never produce solution code, never hint at an
algorithm, approach, or complexity. The classifier prompt below receives
the user's already-written code; you do not write or modify it.**

---

## Step 1 — Detect the problem

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/done/scripts/detect_problem.py
```

Interpret the exit code:

- **0** — stdout is a single JSON object: `{number, title, difficulty, path, kind}`. Capture this; you'll need every field.
- **1** — stderr explains (no candidate, multiple candidates, not initialised). Relay the message and stop.

---

## Step 2 — Classify the solution (algorithmic only)

Skip this step entirely when `kind == "sql"`.

For algorithmic problems, read the file at `path` (use the Read tool), then construct the classification yourself. **Output ONLY a single JSON object on its own line — no markdown fences, no commentary, no leading/trailing prose:**

```
{"patterns": ["Pattern1", "Pattern2"], "revisit": false}
```

Rules:
- `patterns` must be an array of strings drawn **only** from this exact closed enum. Anything else will be filtered out and warned on:
  ```
  Two Pointers, Sliding Window, Binary Search, Stack / Monotonic Stack,
  BFS / DFS, Dynamic Programming, Greedy, Hash Map / Hash Set,
  Linked List, Tree Traversal, Backtracking, Bit Manipulation,
  Heap / Priority Queue, Trie, Prefix Sum, Math, Sorting,
  Design / Simulation
  ```
  (If the user's `config.json` overrides `patterns`, prefer that list — read it from `<repo>/config.json` if you're unsure.)
- `revisit` is `true` only if a genuinely better time- or space-complexity solution exists using a standard pattern. Otherwise `false`.

Hold this JSON in memory; you'll embed it in Step 3's input.

---

## Step 3 — Record the attempt

Build the input payload by combining the Step-1 JSON with the Step-2 classification (or omit `classification` for SQL problems), then pipe it into:

```bash
echo '<payload-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/done/scripts/record_attempt.py
```

Payload shape (algorithmic):
```json
{
  "number": 1, "title": "Two Sum", "difficulty": "Easy",
  "path": "src/Easy/1.Two_Sum/solution.ts", "kind": "algorithmic",
  "classification": {"patterns": ["Hash Map / Hash Set"], "revisit": false}
}
```

Payload shape (SQL):
```json
{
  "number": 177, "title": "Nth Highest Salary", "difficulty": null,
  "path": "src/SQL/177.Nth_Highest_Salary/solution.sql", "kind": "sql"
}
```

Interpret the exit code:

- **0** — verdict lines printed on stdout (timing, patterns, complexity). Relay them verbatim.
- **1** — malformed payload or not initialised; surface stderr and stop.

---

## Step 4 — Regenerate views and dump SQL

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/render_and_dump.py
```

---

## Step 5 — Commit

`tag` is `Easy`, `Medium`, `Hard`, or `SQL` (use `SQL` when `kind == "sql"`).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/done/scripts/commit.py \
  --number <N> --tag <Easy|Medium|Hard|SQL> --title "<title>"
```

Exit code mirrors `git commit`'s. On success the script prints `committed: {N}. {tag}. {title}`.

---

## Step 6 — Report

Print one line — the committed subject (e.g. `Committed 3. Medium. Longest Substring Without Repeating Characters.`).

Do not summarise the solution. Do not suggest approaches. Do not mention complexity.
