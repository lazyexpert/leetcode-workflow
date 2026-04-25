---
description: Bootstrap a fresh leetcode-workflow practice repo in the current directory.
allowed-tools: Bash
---

Run this in an empty directory you want to make a practice repo. The skill
asks two short questions, accepts defaults on enter, and then scaffolds
everything: `.claude/practice.db`, `config.json`, `src/{Easy,Medium,Hard,SQL}/`, the five empty Markdown views, `.gitignore`, and a `git init` if the directory isn't already a git repo.

It refuses if the cwd contains anything other than `.git`.

---

## Step 1 — Ask: language

Ask the user:

> Which language do you solve LeetCode problems in? Type `ok` to use the **TypeScript** default, or reply with the name of one of: Python, Go, Java, C++, JavaScript, Rust, Kotlin, Swift, Ruby.

Map the answer (case-insensitive, trim whitespace) using this table:

| User says            | extension | name        |
|----------------------|-----------|-------------|
| ok / TypeScript / ts | ts        | typescript  |
| Python / py          | py        | python      |
| Go / golang          | go        | go          |
| Java                 | java      | java        |
| C++ / cpp            | cpp       | cpp         |
| JavaScript / js      | js        | javascript  |
| Rust / rs            | rs        | rust        |
| Kotlin / kt          | kt        | kotlin      |
| Swift                | swift     | swift       |
| Ruby / rb            | rb        | ruby        |

If the answer doesn't match any row, **show the table** and ask once more. After a second non-match, stop and tell the user to re-run `/leetcode-workflow:init` with one of the listed names.

Hold the resolved `{extension, name}` for Step 3.

---

## Step 2 — Ask: timing thresholds

Ask the user:

> Default retry thresholds are **Easy 15 / Medium 30 / Hard 60** minutes — solve times past these flag a problem for retry. Type `ok` for defaults, or provide your configuration in the form `{easy}/{medium}/{hard}` (e.g. `15/30/45`).

Parse the answer:
- `ok` (case-insensitive) → `{Easy: 15, Medium: 30, Hard: 60}`
- exactly three positive integers separated by `/` (e.g. `10/25/50`) → `{Easy: <1>, Medium: <2>, Hard: <3>}`
- anything else → re-ask once with the same prompt. After a second bad answer, stop with: "Run `/leetcode-workflow:init` again with valid input."

Hold the resolved thresholds for Step 3.

---

## Step 3 — Run init

Build the JSON payload from Steps 1 and 2:

```json
{
  "language": {"extension": "<ext>", "name": "<name>"},
  "retry_thresholds_minutes": {"Easy": <e>, "Medium": <m>, "Hard": <h>}
}
```

Pipe it in:

```bash
echo '<payload-json>' | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init/init.py
```

Interpret the exit code:

- **0** — practice repo created. stdout prints two lines (path + schema version).
- **1** — stderr explains. Common causes: target dir not empty, malformed payload, `git init` failure. Relay the message and stop.

---

## Step 4 — Report

Print one short paragraph:

> Practice repo ready at `<path>`. Solving in `<language-name>` with thresholds Easy `<e>` / Medium `<m>` / Hard `<h>` min. Patterns and `pick_retry_ratio` are at defaults — edit `config.json` later if you want to tune them. Try `/leetcode-workflow:new <leetcode-url>` to scaffold your first problem.

Do not summarise further. Do not suggest specific problems.
