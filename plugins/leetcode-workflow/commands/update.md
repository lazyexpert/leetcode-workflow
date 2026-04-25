---
description: Apply pending DB migrations after a plugin update and dismiss the update nudge.
allowed-tools: Bash
---

After a plugin update, the user's `practice.db` may be on an older
schema than the plugin code expects. This skill applies any pending
`migrations/000N_*.sql` files in order and refreshes the deterministic
SQL dump, then marks the current plugin version as seen so the
update-nudge banner stops firing.

If there are no pending migrations, the skill still bumps
`plugin_version_seen` and re-renders views — running it after every
plugin update is safe and idempotent.

---

## Step 1 — Run the script

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/update/update.py
```

Interpret the exit code:

- **0** — success. stdout prints two lines: applied migrations (or "schema is up-to-date") + `plugin_version_seen`.
- **1** — not a leetcode-workflow repo, or a migration failed. stderr explains. Relay and stop.

---

## Step 2 — Report

Echo the script's stdout verbatim. One paragraph max.

Do not summarise, suggest next steps, or comment.
