---
name: new
description: >
  Scaffold a new LeetCode problem from a LeetCode URL, or (when a non-empty
  solution already exists at the target path) reset the solution file and
  start a new attempt for reiteration. Invoked as /leetcode-workflow:new.
allowed-tools: Bash, Read
---

# new

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/new/scripts/fetch.py "$ARGUMENTS"
```

Capture stdout (manifest JSON) on success. Interpret exit codes:

- **0** — manifest on stdout. Continue.
- **1** — slug not found. Tell the user the URL slug wasn't recognised; stop.
- **2** — premium problem. Tell the user it can't be fetched from the public API; stop.
- **3** — network failure. Surface stderr; stop.
- **64** — invalid argument. Re-read Step 0.

---

## Step 2 — Decide: new or reiterate

```bash
echo '<manifest-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/new/scripts/detect_reiteration.py
```

Stdout is one of:

- `{"mode": "new", "manifest": {...}}` → go to Step 3a.
- `{"mode": "reiterate", "number": N, "solution_path": "src/...", "language_name": "..."}` → go to Step 3b.

---

## Step 3a — Fresh scaffold

```bash
echo '<manifest-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/new/scripts/scaffold_new.py
```

On exit 0, stdout prints `scaffold: created <path>`. Go to Step 4 (Report).

---

## Step 3b — Reiteration

Read the existing solution file at `solution_path` (use the Read tool).

Strip its body to a signature-only template. **Output ONLY the stripped code — no markdown fences, no commentary, no explanation:**

> Strip the implementation from this `<language_name>` LeetCode solution. Keep every function, class, method, and type declaration intact, but replace each body with an empty body. Preserve original indentation. Reply with ONLY the stripped code.

If you cannot meaningfully strip it (e.g. the source is already empty, or the language is unfamiliar), output the empty string `""` — `apply_solution_template.py` will treat that as a full wipe.

Then pipe `{"number": N, "body_text": "<stripped>"}` into:

```bash
echo '<payload-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/lib/apply_solution_template.py
```

On exit 0, stdout prints `retry: cleared <path>`.

---

## Step 4 — Report

Print one short line:

- `Job's done.` after a fresh scaffold (Step 3a).
- `Ready to reiterate.` after reiteration (Step 3b).

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise the problem. Do not suggest approaches. Do not mention complexity.
