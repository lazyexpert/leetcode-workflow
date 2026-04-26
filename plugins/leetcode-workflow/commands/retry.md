---
description: Pick a problem to revisit (random from retry queue, or explicit by number) and prepare it for a new attempt.
allowed-tools: Bash, Read
---

Pulls a problem from the retry queue and resets it for a new attempt.
The previous solution body is replaced with a signature-only template
(function/class declarations preserved) so you re-solve without
re-looking-up the LC judge signature.

Two modes, controlled by `$ARGUMENTS`:

- **no argument** — random pick where `stale = 1` (cooldown elapsed; tunable via `config.json: review_cooldown_days`).
- **`<number>`** — explicit pick of an algorithmic problem. Cooldown is **not** enforced; if you name it, you get it.

**Critical constraint: never write solution code, never hint at an
algorithm, approach, or complexity.**

---

## Step 1 — Pick

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/retry/pick_problem.py $ARGUMENTS
```

Capture stdout (one-line JSON) on success. Interpret exit codes:

- **0** — JSON: `{number, title, difficulty, solution_path, language_name, reasons}`. Continue.
- **1** — stderr explains. Possible causes:
  - random mode: retry list is empty, or every flagged problem is within cooldown
  - explicit mode: argument isn't a number, problem not in DB, or problem is SQL
  - fatal: not initialised, or solution-file glob collision
  Relay the message and stop.

---

## Step 2 — Strip the previous solution

Read the file at `solution_path` (use the Read tool).

Remove any stale body file from a prior `/retry` session before writing — the Write tool refuses to silently overwrite, and a stale file would otherwise be reused with the wrong content:

```bash
rm -f /tmp/leetcode-workflow-body.txt
```

Strip its body to a signature-only template. Use the **Write tool** to save ONLY the stripped code (no fences, no commentary) to `/tmp/leetcode-workflow-body.txt`:

> Strip the implementation from this `<language_name>` LeetCode solution. Keep every function, class, method, and type declaration intact, but replace each body with an empty body. Preserve original indentation. The file content must be exactly the stripped code — nothing else.

If you cannot meaningfully strip it (source is already empty, language unfamiliar), write an empty file instead — `apply_solution_template.py` treats an empty body as a full wipe.

---

## Step 3 — Apply the template

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/apply_solution_template.py \
    --number <number> --body-file /tmp/leetcode-workflow-body.txt
```

On exit 0, stdout prints `retry: cleared <path>`.

---

## Step 4 — Report

Print one short line — the prepared problem with its reason flags joined by `+`:

- `Ready to retry 19. Remove Nth Node From End of List (Medium) — timing+stale.`
- If `reasons` is empty (explicit pick of a fresh problem), drop the trailing ` — …`.

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise the problem, do not suggest approaches, do not mention complexity.
