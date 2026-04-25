#!/usr/bin/env python3
"""
Fetch a LeetCode problem via the public GraphQL endpoint and write a
manifest file ready for scaffold_new.py / detect_reiteration.py.

Usage:
  fetch.py <url-or-slug> [--out <path>]

Accepts a full LeetCode problem URL (e.g.
https://leetcode.com/problems/two-sum/description/) or a bare slug
(e.g. two-sum).

Output:
  * Writes the manifest JSON to <path> (default
    /tmp/leetcode-workflow-manifest.json). Manifest fields:
      number, title, difficulty, type ("algorithmic"|"SQL"), statement.
  * Prints a one-line summary on stdout for orchestration:
      fetched: <N>. <Title> (<Difficulty>)
      manifest: <path>

The manifest is *not* dumped to stdout — that would leak the problem
statement and any LC topic tags into the conversation, undermining the
"never hint at the approach" rule. Topic tags are excluded from the
manifest entirely; the SQL-vs-algorithmic classification is computed
internally before they're discarded.

Exit codes:
   0 success
   1 problem not found (bad slug)
   2 premium problem (content empty / paywalled)
   3 network / HTTP failure
  64 invalid arguments
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
import db  # noqa: E402

DEFAULT_MANIFEST_PATH = '/tmp/leetcode-workflow-manifest.json'


QUERY = (
    'query q($s:String!){question(titleSlug:$s){'
    'questionFrontendId title difficulty content topicTags{slug}'
    ' codeSnippets{langSlug code}'
    '}}'
)


# LC's `langSlug` doesn't always match our `language.name`. Most do (typescript,
# java, cpp, javascript, rust, kotlin, swift, ruby), but a couple need mapping.
# Each entry is a fallback list — first match wins.
LANG_SLUG_ALIASES: dict[str, list[str]] = {
    'go':     ['golang'],            # LC: 'golang'
    'python': ['python3', 'python'], # prefer Python 3
}


def lookup_signature(
    snippets: list[dict],
    language_name: str,
    problem_type: str,
) -> str:
    """Pick the signature template for the user's language. Returns '' if no
    snippet matched (rare LC problem with no snippets, unusual language)."""
    if problem_type == 'SQL':
        candidates = ['mysql']
    else:
        candidates = LANG_SLUG_ALIASES.get(language_name, [language_name])
    by_slug = {
        (s.get('langSlug') or '').lower(): s.get('code') or ''
        for s in (snippets or [])
    }
    for slug in candidates:
        if slug in by_slug:
            return by_slug[slug]
    return ''


# ── slug / URL handling ────────────────────────────────────────────────────

def extract_slug(value: str) -> str | None:
    m = re.search(r'problems/([^/?\s]+)', value)
    if m:
        return m.group(1)
    if re.match(r'^[a-z0-9][a-z0-9-]*$', value):
        return value
    return None


# ── GraphQL fetch ──────────────────────────────────────────────────────────

def fetch(slug: str) -> dict:
    """Hit LC's GraphQL endpoint. Tests monkey-patch this to inject
    fixture responses without hitting the network."""
    req = urllib.request.Request(
        'https://leetcode.com/graphql',
        data=json.dumps({'query': QUERY, 'variables': {'s': slug}}).encode(),
        headers={
            'Content-Type': 'application/json',
            'User-Agent':   'Mozilla/5.0',
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        # LC returns raw tabs inside JSON strings; strict=False tolerates it.
        return json.loads(resp.read().decode(), strict=False)


# ── HTML → Markdown (LC's content field) ───────────────────────────────────

_TAG_RX = re.compile(r'<[^>]+>')


def html_to_markdown(content: str) -> str:
    """Crude HTML → markdown. LC's content uses <p>, <pre>, <code>, <strong>,
    <em>, <ul>/<ol>/<li>, <sup>, plus &nbsp; and entity-encoded math.
    Aim is plain readable markdown, not perfect fidelity."""
    if not content:
        return ''
    s = content
    # Code fences
    s = re.sub(r'<pre>\s*<code>(.*?)</code>\s*</pre>', r'```\n\1\n```', s, flags=re.DOTALL)
    s = re.sub(r'<pre>(.*?)</pre>',                    r'```\n\1\n```', s, flags=re.DOTALL)
    # Inline code
    s = re.sub(r'<code>(.*?)</code>',                  r'`\1`',         s, flags=re.DOTALL)
    # Bold / italic
    s = re.sub(r'<(?:strong|b)>(.*?)</(?:strong|b)>',  r'**\1**',       s, flags=re.DOTALL)
    s = re.sub(r'<(?:em|i)>(.*?)</(?:em|i)>',          r'*\1*',         s, flags=re.DOTALL)
    # Lists
    s = re.sub(r'<li>',  '- ',  s)
    s = re.sub(r'</li>', '',    s)
    s = re.sub(r'</?ul>|</?ol>', '\n', s)
    # Paragraphs / breaks
    s = re.sub(r'<br\s*/?>', '\n', s)
    s = re.sub(r'</p>',      '\n\n', s)
    s = re.sub(r'<p[^>]*>',  '',     s)
    # Strip remaining tags
    s = _TAG_RX.sub('', s)
    # Decode entities
    s = html.unescape(s)
    # Collapse 3+ blank lines
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip() + '\n'


# ── classification ─────────────────────────────────────────────────────────

def classify_type(tags: list[str]) -> str:
    """LC tag 'database' identifies SQL problems."""
    return 'SQL' if 'database' in tags else 'algorithmic'


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('url', nargs='?', default='',
                    help='LeetCode problem URL or bare slug')
    ap.add_argument('--out', default=DEFAULT_MANIFEST_PATH,
                    help=f'where to write the manifest JSON '
                         f'(default: {DEFAULT_MANIFEST_PATH})')
    args = ap.parse_args()

    if not args.url.strip():
        print('Usage: fetch.py <url-or-slug> [--out <path>]', file=sys.stderr)
        return 64

    slug = extract_slug(args.url.strip())
    if slug is None:
        print(f'ERROR: could not extract slug from {args.url!r}', file=sys.stderr)
        return 64

    try:
        data = fetch(slug)
    except urllib.error.HTTPError as e:
        print(f'ERROR: HTTP {e.code} from leetcode.com', file=sys.stderr)
        return 3
    except urllib.error.URLError as e:
        print(f'ERROR: network failure: {e}', file=sys.stderr)
        return 3
    except Exception as e:  # pragma: no cover — defensive
        print(f'ERROR: unexpected fetch failure: {e}', file=sys.stderr)
        return 3

    q = (data or {}).get('data', {}).get('question')
    if q is None:
        print(f'ERROR: problem not found for slug {slug!r}', file=sys.stderr)
        return 1

    if not q.get('content'):
        print(f'ERROR: {slug!r} appears to be a premium problem '
              f'(empty content from public API)', file=sys.stderr)
        return 2

    tags     = [t.get('slug', '') for t in (q.get('topicTags') or [])]
    snippets = q.get('codeSnippets') or []
    ptype    = classify_type(tags)

    language_name = db.load_language()['name']
    signature     = lookup_signature(snippets, language_name, ptype)

    manifest = {
        'number':     int(q['questionFrontendId']),
        'title':      q['title'],
        'difficulty': q.get('difficulty', ''),
        'type':       ptype,
        'statement':  html_to_markdown(q['content']),
        'signature':  signature,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest))

    print(f'fetched: {manifest["number"]}. {manifest["title"]} '
          f'({manifest["difficulty"] or "SQL"})')
    print(f'manifest: {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
