#!/usr/bin/env python3
"""
Fetch a LeetCode problem via the public GraphQL endpoint and emit a
manifest ready to pipe into scaffold_new.py / detect_reiteration.py.

Usage: fetch.py <url-or-slug>

Accepts a full LeetCode problem URL (e.g.
https://leetcode.com/problems/two-sum/description/) or a bare slug
(e.g. two-sum). Outputs a JSON manifest on stdout with: number, title,
difficulty, type ("algorithmic"|"SQL"), tags, statement (markdown).

Exit codes:
   0 success
   1 problem not found (bad slug)
   2 premium problem (content empty / paywalled)
   3 network / HTTP failure
  64 invalid arguments
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request


QUERY = (
    'query q($s:String!){question(titleSlug:$s){'
    'questionFrontendId title difficulty content topicTags{slug}'
    '}}'
)


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
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print('Usage: fetch.py <url-or-slug>', file=sys.stderr)
        return 64

    slug = extract_slug(sys.argv[1].strip())
    if slug is None:
        print(f'ERROR: could not extract slug from {sys.argv[1]!r}', file=sys.stderr)
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

    tags = [t.get('slug', '') for t in (q.get('topicTags') or [])]
    manifest = {
        'number':     int(q['questionFrontendId']),
        'title':      q['title'],
        'difficulty': q.get('difficulty', ''),
        'type':       classify_type(tags),
        'tags':       tags,
        'statement':  html_to_markdown(q['content']),
    }

    print(json.dumps(manifest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
