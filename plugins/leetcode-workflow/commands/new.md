---
description: Scaffold a new LeetCode problem from a URL, or reset for reiteration if it already exists.
allowed-tools: Bash, Read
---

Pass a LeetCode problem URL. The skill fetches the manifest, decides
between fresh scaffolding and reiteration, and either creates the folder
or resets the existing solution to a signature-only template.

**Critical constraint: never write solution code, never hint at an
algorithm, approach, or complexity.**

---

## Step 0 — Guard

If `$ARGUMENTS` is empty or does not contain `leetcode.com/problems/<slug>`, stop and tell the user to pass a valid LeetCode problem URL (e.g. `https://leetcode.com/problems/two-sum/`). A bare slug (`two-sum`) is also acceptable.

---

## Step 1 — Fetch the manifest

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new/fetch.py "$ARGUMENTS"
```

The script writes the manifest to `/tmp/leetcode-workflow-manifest.json` and prints a one-line summary on stdout. Interpret exit codes:

- **0** — manifest written. Continue.
- **1** — slug not found. Tell the user the URL slug wasn't recognised; stop.
- **2** — premium problem. Tell the user it can't be fetched from the public API; stop.
- **3** — network failure. Surface stderr; stop.
- **64** — invalid argument. Re-read Step 0.

**Do not `cat` the manifest file or read the scaffolded `README.md`** — both contain the problem statement, and reading them will tempt you to summarise it, which violates the no-hint rule. The user reads the problem on their own.

---

## Step 2 — Decide: new or reiterate

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new/detect_reiteration.py < /tmp/leetcode-workflow-manifest.json
```

Stdout is one of:

- `{"mode": "new", "manifest": {...}}` → go to Step 3a.
- `{"mode": "reiterate", "number": N, "solution_path": "src/...", "language_name": "..."}` → go to Step 3b.

---

## Step 3a — Fresh scaffold

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/new/scaffold_new.py < /tmp/leetcode-workflow-manifest.json
```

On exit 0, stdout prints `scaffold: created <path>`. Go to Step 4 (Report).

---

## Step 3b — Reiteration

Read the existing solution file at `solution_path` (use the Read tool).

Strip its body to a signature-only template. Use the **Write tool** to save ONLY the stripped code (no fences, no commentary) to `/tmp/leetcode-workflow-body.txt`:

> Strip the implementation from this `<language_name>` LeetCode solution. Keep every function, class, method, and type declaration intact, but replace each body with an empty body. Preserve original indentation. The file content must be exactly the stripped code — nothing else.

If you cannot meaningfully strip it (e.g. the source is already empty, or the language is unfamiliar), write an empty file instead — `apply_solution_template.py` treats an empty body as a full wipe.

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/apply_solution_template.py \
    --number <N> --body-file /tmp/leetcode-workflow-body.txt
```

On exit 0, stdout prints `retry: cleared <path>`.

---

## Step 4 — Report

Print one short line:

- `Job's done.` after a fresh scaffold (Step 3a).
- `Ready to reiterate.` after reiteration (Step 3b).

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise the problem. Do not suggest approaches. Do not mention complexity.
