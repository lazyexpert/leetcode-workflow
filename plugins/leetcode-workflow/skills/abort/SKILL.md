---
name: abort
description: >
  Abort the latest in-progress LeetCode attempt — drop the attempt row
  and restore the solution file to HEAD. If the attempt was the only
  one for the problem (e.g. an aborted /new), drop the problem from
  the DB and remove its folder. Invoked as /leetcode-workflow:abort.
allowed-tools: Bash
---

# abort

Use when you've started a `/leetcode-workflow:new` or
`/leetcode-workflow:retry` you no longer want recorded — wrong problem
scaffolded, you need to step away from a retry without the failed timing
entering the stats, etc.

The skill never commits. Your working tree state is up to you afterward.

⚠ **Destructive on uncommitted edits.** When the problem has prior
committed attempts, abort runs `git checkout HEAD -- <solution-file>`,
which overwrites whatever's currently in the file. If you have changes
worth keeping, `git stash` first.

---

## Step 1 — Run the script

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/abort/scripts/abort.py
```

Interpret the exit code:

- **0** — attempt aborted. stdout: `abort: {N}. {Title} ({Difficulty|SQL}) — {action}` where `{action}` is `restored <path>` (had prior attempts) or `problem and folder removed` (sole attempt).
- **1** — nothing to abort, or not initialised. stderr explains.

---

## Step 2 — Report

One short line — echo the script's output verbatim.

Then run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/nudge.py`. If it printed anything, append the output verbatim on a new line.

Do not summarise, suggest, or comment.
