-- Migration 0001 — imported attempts
--
-- Adds `imported` to the attempts table. Distinguishes a
-- *completed-but-timing-unknown* attempt (set by /leetcode-workflow:import)
-- from an *in-progress* attempt — both have duration_minutes IS NULL
-- otherwise. Without this column, the next /done would close an imported
-- attempt and compute multi-year durations from its (git-derived)
-- started_at timestamp.
--
-- retry_flags VIEW is unchanged: timing_bad already guards on
-- `duration_minutes IS NOT NULL`, so imported rows naturally won't fire
-- it. Imported rows will fire `stale` once the cooldown elapses since
-- their started_at — which is the desired behaviour (imported problems
-- enter the retry pool as candidates for revisit).
--
-- latest_open_attempt() in lib/db.py is updated to filter `imported = 0`
-- so /done's "find the open attempt to close" query ignores imports.

BEGIN;

ALTER TABLE attempts ADD COLUMN imported INTEGER NOT NULL DEFAULT 0;

INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '1');

COMMIT;
