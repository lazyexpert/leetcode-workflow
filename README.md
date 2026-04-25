# leetcode-workflow

A Claude Code-native LeetCode practice workflow. Scaffolds problems from a URL, classifies patterns automatically, tracks per-attempt solve times against configurable thresholds, and maintains a retry queue with spaced-repetition cooldown — all backed by a local SQLite database with five generated Markdown views.

This repository is a **Claude Code plugin marketplace**. Install the plugins here and they ship a set of slash commands you run inside your own LeetCode practice repo.

> **Status: pre-release v0.1.0.** API and schema may still change as the plugin gets exercised against real practice.

---

## What's in the box

Seven slash commands, each backed by deterministic Python scripts; orchestration prose lives in `commands/<name>.md`.

| Command | Purpose |
|---|---|
| `/leetcode-workflow:init` | Bootstrap a fresh practice repo at the current directory: schema, empty views, default config, `.gitignore`, initial commit. Asks two short questions (language, retry thresholds) — `yes` accepts defaults. |
| `/leetcode-workflow:new <url>` | Scaffold a problem from a LeetCode URL. Creates the folder, writes the README, seeds `solution.<ext>` with LC's per-language signature template, opens an attempt. |
| `/leetcode-workflow:pick` | "What should I solve next?" — picks a fresh problem targeting an under-covered pattern. With non-zero `pick_retry_ratio`, occasionally routes to a retry pick instead. |
| `/leetcode-workflow:done` | Close out the current attempt: timing verdict against your threshold, pattern classification, complexity flag, auto-commit. |
| `/leetcode-workflow:retry [N]` | Pick a problem to revisit — random from the cooldown-elapsed pool, or a specific number you name. Strips the previous body to a signature template. |
| `/leetcode-workflow:abort` | Drop the latest in-progress attempt, restore the solution file from `HEAD`. |
| `/leetcode-workflow:update` | Apply pending DB migrations after a plugin update; dismisses the update nudge. |

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

## Workflow

Three flows you'll spend most of your time in.

### Daily flow — solving a new problem

```mermaid
sequenceDiagram
    actor You
    participant Plugin as leetcode-workflow
    participant LC as LeetCode

    You->>Plugin: /leetcode-workflow:new <url>
    Plugin->>LC: fetch problem
    LC-->>Plugin: title, difficulty, signature
    Plugin-->>You: scaffolded folder + solution.<ext>
    Note over You: write solution<br/>ask Claude for hints, never the answer
    You->>Plugin: /leetcode-workflow:done
    Plugin-->>You: timing verdict, pattern classified, auto-commit
```

### Picking what's next

`/pick` is one-shot: it chooses a problem and gets you ready to solve. Default routing targets an under-covered pattern (and scaffolds it for you, like `/new` would); at your configured `pick_retry_ratio`, a share of invocations route to the retry pool instead.

```mermaid
sequenceDiagram
    actor You
    participant Plugin as leetcode-workflow
    participant LC as LeetCode

    You->>Plugin: /leetcode-workflow:pick
    alt fresh problem (default)
        Plugin->>Plugin: choose under-covered pattern + problem
        Plugin->>LC: fetch problem
        LC-->>Plugin: title, difficulty, signature
        Plugin-->>You: scaffolded folder + solution.<ext>
    else retry pool (configurable share)
        Plugin->>Plugin: pick stale problem from retry queue
        Plugin->>Plugin: strip body, leave signature template
        Plugin-->>You: problem ready, fresh attempt
    end
    Note over You: solve, then /leetcode-workflow:done
```

### Spaced repetition — `/retry`

Past attempts that ran slow, used a brittle approach, or have aged past their cooldown surface in the retry queue. `/retry` reseeds one of them.

```mermaid
sequenceDiagram
    actor You
    participant Plugin as leetcode-workflow

    Note over Plugin: Retry queue tracks problems flagged by:<br/>slow timing, brittle complexity, or stale (cooldown elapsed)
    You->>Plugin: /leetcode-workflow:retry
    Plugin->>Plugin: pick from cooldown-elapsed pool
    Plugin->>Plugin: strip body, leave signature template
    Plugin-->>You: problem ready, fresh attempt
    You->>Plugin: /leetcode-workflow:done
    Plugin-->>You: new timing recorded — flags re-evaluated
```

---

## Contributing

Bug reports, feature requests, and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing, and PR flow. If you're a coding agent, also read [AGENTS.md](AGENTS.md) — the agent-specific rules.

The architectural reference is [CLAUDE.md](CLAUDE.md). Worth a skim before filing an issue or proposing a feature.

---

## License

[MIT](LICENSE) © 2026 Khatskalev Oleksandr
