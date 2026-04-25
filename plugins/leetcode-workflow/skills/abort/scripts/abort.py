#!/usr/bin/env python3
"""
Abort the latest in-progress LeetCode attempt.

Behaviour
---------
1. Find the most recently started attempts row with duration_minutes IS NULL.
2. Delete that attempt.
3. If it was the ONLY attempt for that problem (sole-attempt case — typical
   for an aborted fresh /new):
     - delete the problem row (CASCADE wipes patterns)
     - remove the problem folder from disk (would have been untracked)
4. Otherwise (problem has prior committed attempts — typical for an
   aborted /retry or post-done reiteration):
     - restore the solution file from HEAD via `git checkout`
     - leave everything else alone
5. Regenerate the five MD views and refresh practice.sql.

Does not commit. The user is responsible for the working tree afterward.

Stdout (one line on success):
  abort: {N}. {Title} ({Difficulty|SQL}) — {action}
where {action} is `restored <path>`, `problem and folder removed`, or a
graceful "attempt dropped (...)" when restoration couldn't run.

Exit codes:
  0 success
  1 no in-progress attempt found / not initialised
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import db        # noqa: E402
import render    # noqa: E402


def main() -> int:
    try:
        conn = db.open_db()
    except db.NotInitialized as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    try:
        db.sync_config(conn)

        row = conn.execute(
            'SELECT a.id, a.problem_number, '
            '       p.title, p.difficulty, p.kind, p.folder, '
            '       (SELECT COUNT(*) FROM attempts '
            '         WHERE problem_number = a.problem_number) AS attempt_count '
            'FROM attempts a '
            'JOIN problems p ON p.number = a.problem_number '
            'WHERE a.duration_minutes IS NULL '
            'ORDER BY a.started_at DESC '
            'LIMIT 1'
        ).fetchone()

        if row is None:
            print('No in-progress attempt to abort.', file=sys.stderr)
            return 1

        attempt_id, number, title, difficulty, kind, folder, attempt_count = row
        section     = 'SQL' if kind == 'sql' else difficulty
        folder_path = db.REPO / 'src' / section / folder
        label       = 'SQL' if kind == 'sql' else difficulty

        conn.execute('DELETE FROM attempts WHERE id = ?', (attempt_id,))

        if attempt_count == 1:
            # Sole attempt → full rollback. CASCADE drops patterns.
            conn.execute('DELETE FROM problems WHERE number = ?', (number,))
            if folder_path.exists():
                shutil.rmtree(folder_path)
            action = 'problem and folder removed'
        else:
            # Prior committed attempts exist — restore solution from HEAD.
            sfile = next(iter(sorted(folder_path.glob('solution.*'))), None)
            if sfile is None:
                action = 'attempt dropped (no solution file present to restore)'
            else:
                rel    = sfile.relative_to(db.REPO)
                result = subprocess.run(
                    ['git', 'checkout', 'HEAD', '--', str(rel)],
                    cwd=db.REPO, capture_output=True, text=True,
                )
                if result.returncode == 0:
                    action = f'restored {rel}'
                else:
                    action = (
                        f'attempt dropped (could not restore {rel}: '
                        f'{result.stderr.strip() or "git checkout failed"})'
                    )

        render.render_all(conn, db.REPO)
        db.dump_sql(conn)
    finally:
        conn.close()

    print(f'abort: {number}. {title} ({label}) — {action}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
