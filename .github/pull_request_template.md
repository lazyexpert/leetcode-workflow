## What this changes

One paragraph. Lead with *why* — what gap does this close, what bug does this fix? The diff shows *what*.

Closes #<issue-number> *(or "Refs #N" / drop the line if no issue exists)*

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor (no behavior change)
- [ ] Schema migration *(if checked: bumped `plugin.json: version` and added `migrations/000N_*.sql`)*

## Test plan

How you verified this works. Bullets are fine:

- [ ] `pytest -q` is green
- [ ] `ruff check .` is clean
- [ ] Coverage didn't drop *(if scripts changed — see [CONTRIBUTING.md](../CONTRIBUTING.md#before-you-push))*
- [ ] Manually exercised in a scratch practice repo *(for command-level changes)*

Add anything specific you tested by hand: edge cases hit, environments tried, problems you scaffolded.

## Pedagogical contract

- [ ] This change does not introduce any code path that produces solution code without an explicit user request *(see CLAUDE.md "Pedagogical contract")*

## Anything reviewers should know

Optional: design tradeoffs, follow-ups left for a separate PR, things you'd like a second opinion on.
