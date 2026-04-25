"""
Read the plugin manifest. Single source of truth for plugin metadata so
update.py and nudge.py stay in sync.

The manifest lives at <plugin_root>/.claude-plugin/plugin.json — sibling
of skills/, lib/, and migrations/.
"""
from __future__ import annotations

import json
from pathlib import Path


PLUGIN_JSON = Path(__file__).resolve().parent.parent / '.claude-plugin' / 'plugin.json'


def plugin_version() -> str:
    """Return the version string from plugin.json. Raises if absent."""
    return json.loads(PLUGIN_JSON.read_text())['version']
