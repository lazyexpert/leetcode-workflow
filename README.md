# leetcode-workflow

A Claude Code-native LeetCode practice workflow. Scaffolds problems from a URL, classifies patterns automatically, tracks per-attempt solve times against configurable thresholds, and maintains a retry queue with spaced-repetition cooldown — all backed by a local SQLite database with five generated Markdown views.

This repository is a **Claude Code plugin marketplace**. Install the plugins here and they ship a set of slash commands you run inside your own LeetCode practice repo.

> **Status: pre-release.** API and schema may change without notice until v0.1.0.

---

## What's in the box

| Skill | Purpose |
|---|---|
| `/leetcode-workflow:init` | Bootstrap a fresh practice repo at the current directory: schema, empty views, default config, `.gitignore`, initial commit. |
| `/leetcode-workflow:new <url>` | Scaffold a problem from a LeetCode URL. Creates the folder, writes the README, opens an attempt in the DB. |
| `/leetcode-workflow:done` | Close out the current attempt: timing verdict against your threshold, pattern classification, complexity flag, auto-commit. |
| `/leetcode-workflow:retry [N]` | Pick a problem to revisit — random from the cooldown-elapsed pool, or a specific number you name. Strips the previous body to a signature template. |
| `/leetcode-workflow:abort` | Drop the latest in-progress attempt, restore the solution file from `HEAD`. |
| `/leetcode-workflow:update` | Apply pending DB migrations after a plugin update. |

---

## Install (once published)

```bash
# In Claude Code:
/plugin marketplace add lazyexpert/leetcode-workflow
/plugin install leetcode-workflow@leetcode-workflow
```

Then in any directory:

```bash
mkdir my-lc-practice && cd my-lc-practice
# In Claude Code:
/leetcode-workflow:init
```

You're ready to solve.

---

## Why

Most LeetCode practice setups are scratch directories with a copy-pasted problem statement and a one-shot solution file. After 50 problems you've lost track of which patterns you've covered, which were slow, and which deserve a second pass. This workflow encodes that bookkeeping as durable state — your DB tracks every attempt, the retry queue surfaces what's worth revisiting, and the Markdown views give you a human-readable progress log without manual upkeep.

The pedagogical contract is enforced: Claude is configured as a coach, not a solution generator. You get hints, complexity analysis, pattern names — never the answer.

---

## License

[MIT](LICENSE) © 2026 Khatskalev Oleksandr
