-- Migration 0002 — portable retry_flags VIEW
--
-- Replaces `unixepoch()` (SQLite 3.38+, released Feb 2022) in
-- retry_flags with `CAST(strftime('%s', 'now') AS INTEGER)`, which
-- works on every SQLite version from 3.0 onward.
--
-- Why this matters: SQLite resolves function names when expanding a
-- VIEW into the planning stage of any query against it — even when
-- the WHERE clause would return zero rows. On runners shipping
-- SQLite < 3.38 (notably the GHA macos-latest + Python 3.9 cell),
-- ANY query against retry_flags errored out with
--   sqlite3.OperationalError: no such function: unixepoch
-- which cascaded through every render call (init, update, done,
-- import, scaffold_new, …).
--
-- `strftime('%s', 'now')` returns the current unix timestamp as text
-- in every supported SQLite. CAST to INTEGER preserves the integer
-- arithmetic semantics the cooldown comparison relies on.
--
-- The VIEW body is otherwise byte-identical to baseline.

BEGIN;

DROP VIEW IF EXISTS retry_flags;

CREATE VIEW retry_flags AS
WITH
cooldown_sec AS (
  SELECT COALESCE(
    (SELECT CAST(value AS INTEGER) FROM settings WHERE key = 'review_cooldown_days'),
    7
  ) * 86400 AS secs
),
latest AS (
  SELECT a.problem_number, a.started_at, a.duration_minutes, a.revisit
  FROM attempts a
  JOIN (
    SELECT problem_number, MAX(started_at) AS latest_started
    FROM attempts
    GROUP BY problem_number
  ) m
    ON m.problem_number = a.problem_number
   AND m.latest_started = a.started_at
)
SELECT
  p.number,
  p.title,
  p.difficulty,
  p.folder,
  latest.started_at AS flagged_at,
  CASE WHEN latest.duration_minutes IS NOT NULL
            AND latest.duration_minutes >= t.minutes
       THEN 1 ELSE 0 END AS timing_bad,
  CASE WHEN latest.revisit = 1
       THEN 1 ELSE 0 END AS complexity_bad,
  CASE WHEN latest.started_at IS NOT NULL
            AND (CAST(strftime('%s', 'now') AS INTEGER) - latest.started_at)
                  >= (SELECT secs FROM cooldown_sec)
       THEN 1 ELSE 0 END AS stale
FROM problems p
LEFT JOIN thresholds t ON t.difficulty = p.difficulty
LEFT JOIN latest       ON latest.problem_number = p.number
WHERE p.kind = 'algorithmic';

INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '2');

COMMIT;
