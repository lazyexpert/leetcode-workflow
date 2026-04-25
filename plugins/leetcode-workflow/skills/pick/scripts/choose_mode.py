#!/usr/bin/env python3
"""
Decide whether /leetcode-workflow:pick routes to the retry pool or
suggests a fresh problem.

Reads config.pick_retry_ratio (float 0..1, default 0.0). Rolls a uniform
random; emits "retry" if roll < ratio, else "new".

Environment:
  LEETCODE_PICK_SEED  optional integer; if set, seeds random for
                      deterministic tests.

Stdout: a single word — "retry" or "new" — followed by a newline.
Exit code: 0 (always; failures from this picker would propagate from
           later pipeline stages, not here).
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import db    # noqa: E402


def main() -> int:
    seed = os.environ.get('LEETCODE_PICK_SEED')
    if seed is not None and seed.strip():
        try:
            random.seed(int(seed))
        except ValueError:
            print(f'ERROR: LEETCODE_PICK_SEED must be int, got {seed!r}',
                  file=sys.stderr)
            return 1

    ratio = db.load_pick_retry_ratio()
    print('retry' if random.random() < ratio else 'new')
    return 0


if __name__ == '__main__':
    sys.exit(main())
