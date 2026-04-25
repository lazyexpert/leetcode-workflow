---
name: retry
description: >
  Pick an algorithmic problem to revisit (random from the retry queue,
  respecting the cooldown window, or explicit by number) and prepare it
  for a fresh solve — strips the previous solution to a signature-only
  template, opens a new attempt. Invoked as /leetcode-workflow:retry.
allowed-tools: Bash, Read
---

# retry

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/retry/scripts/pick_problem.py $ARGUMENTS
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

Strip its body to a signature-only template. **Output ONLY the stripped code — no markdown fences, no commentary, no explanation:**

> Strip the implementation from this `<language_name>` LeetCode solution. Keep every function, class, method, and type declaration intact, but replace each body with an empty body. Preserve original indentation. Reply with ONLY the stripped code.

If you cannot meaningfully strip it (source is already empty, language unfamiliar), output the empty string `""` — `apply_solution_template.py` will treat that as a full wipe.

---

## Step 3 — Apply the template

```bash
echo '<payload-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/lib/apply_solution_template.py
```

Payload: `{"number": <number>, "body_text": "<stripped>"}`.

On exit 0, stdout prints `retry: cleared <path>`.

---

## Step 4 — Report

Print one short line — the prepared problem with its reason flags joined by `+`:

- `Ready to retry 19. Remove Nth Node From End of List (Medium) — timing+stale.`
- If `reasons` is empty (explicit pick of a fresh problem), drop the trailing ` — …`.

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise the problem, do not suggest approaches, do not mention complexity.
