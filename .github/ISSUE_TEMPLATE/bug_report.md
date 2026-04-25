---
name: Bug report
about: Something the plugin does wrong, crashes, or claims to do but doesn't
title: ''
labels: bug
assignees: ''
---

## What happened

A clear, terse description. One paragraph is plenty.

## Reproduction steps

```
1. /leetcode-workflow:init in a fresh empty dir
2. /leetcode-workflow:new https://leetcode.com/problems/...
3. ...
```

If the bug is environmental (e.g. only on a specific OS or shell), say so.

## Expected behavior

What you thought would happen.

## Actual behavior

What actually happened. Paste error output if any:

```
<full error message + traceback if available>
```

## Environment

- **Plugin version:** (from `cat plugins/leetcode-workflow/.claude-plugin/plugin.json | grep version` in the marketplace repo, or `sqlite3 .claude/practice.db "SELECT value FROM settings WHERE key='plugin_version_seen'"` in your practice repo)
- **OS:** (e.g. macOS 14.4, Ubuntu 22.04)
- **Python:** (`python3 --version`)
- **Claude Code version:** (`claude --version` if relevant)

## Anything else

Optional: hypothesis on the cause, a workaround you found, related issues, etc.
