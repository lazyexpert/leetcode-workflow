"""
Function-level tests for scripts/new/fetch.py.

Network is mocked by monkey-patching fetch.fetch() on the imported module.
This is the only Phase 2 script tested as a Python function rather than a
subprocess — it does HTTP, and stubbing urllib in a child process is more
trouble than it's worth.

fetch.py writes the manifest to a file (default `/tmp/leetcode-workflow-manifest.json`,
overridable via `--out`) and prints only a one-line summary on stdout.
The manifest is intentionally kept off stdout so the tool output doesn't
leak the problem statement or LC topic tags.
"""
from __future__ import annotations

import importlib.util
import json
import sys

import pytest
from conftest import PLUGIN_ROOT


def _import_fetch():
    """Load fetch.py as a module without running its main()."""
    spec = importlib.util.spec_from_file_location(
        'fetch', PLUGIN_ROOT / 'scripts' / 'new' / 'fetch.py',
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fetch_mod():
    return _import_fetch()


# ── slug extraction ────────────────────────────────────────────────────────

def test_extract_slug_from_full_url(fetch_mod):
    assert fetch_mod.extract_slug(
        'https://leetcode.com/problems/two-sum/description/'
    ) == 'two-sum'


def test_extract_slug_from_bare_slug(fetch_mod):
    assert fetch_mod.extract_slug('two-sum') == 'two-sum'


def test_extract_slug_rejects_invalid(fetch_mod):
    assert fetch_mod.extract_slug('https://example.com/foo') is None
    assert fetch_mod.extract_slug('Two Sum') is None  # spaces / capitals


# ── HTML → markdown ────────────────────────────────────────────────────────

def test_html_to_markdown_paragraph(fetch_mod):
    out = fetch_mod.html_to_markdown('<p>Hello world.</p>')
    assert out.strip() == 'Hello world.'


def test_html_to_markdown_code_block(fetch_mod):
    out = fetch_mod.html_to_markdown(
        '<pre><code>nums = [2,7,11,15]\ntarget = 9\n</code></pre>'
    )
    assert '```' in out
    assert 'nums = [2,7,11,15]' in out


def test_html_to_markdown_decodes_entities(fetch_mod):
    out = fetch_mod.html_to_markdown('<p>a &lt; b &amp;&amp; c &gt; d</p>')
    assert 'a < b && c > d' in out


def test_html_to_markdown_empty(fetch_mod):
    assert fetch_mod.html_to_markdown('') == ''


# ── classify_type ──────────────────────────────────────────────────────────

def test_classify_type_sql(fetch_mod):
    assert fetch_mod.classify_type(['database']) == 'SQL'
    assert fetch_mod.classify_type(['hash-table', 'database']) == 'SQL'


def test_classify_type_algorithmic(fetch_mod):
    assert fetch_mod.classify_type(['hash-table']) == 'algorithmic'
    assert fetch_mod.classify_type([]) == 'algorithmic'


# ── lookup_signature ────────────────────────────────────────────────────────

def test_lookup_signature_direct_match(fetch_mod):
    snippets = [
        {'langSlug': 'typescript', 'code': 'ts code'},
        {'langSlug': 'java',       'code': 'java code'},
    ]
    assert fetch_mod.lookup_signature(snippets, 'typescript', 'algorithmic') == 'ts code'
    assert fetch_mod.lookup_signature(snippets, 'java', 'algorithmic')       == 'java code'


def test_lookup_signature_go_uses_golang_alias(fetch_mod):
    """LC's slug is 'golang', config's name is 'go'. Alias map bridges them."""
    snippets = [{'langSlug': 'golang', 'code': 'go code'}]
    assert fetch_mod.lookup_signature(snippets, 'go', 'algorithmic') == 'go code'


def test_lookup_signature_python_prefers_python3(fetch_mod):
    """LC has both 'python' (legacy) and 'python3'. Always prefer the modern one."""
    snippets = [
        {'langSlug': 'python',  'code': 'py2'},
        {'langSlug': 'python3', 'code': 'py3'},
    ]
    assert fetch_mod.lookup_signature(snippets, 'python', 'algorithmic') == 'py3'


def test_lookup_signature_python_falls_back_to_python(fetch_mod):
    """Old problems may only have 'python' snippets. Fall back gracefully."""
    snippets = [{'langSlug': 'python', 'code': 'py2'}]
    assert fetch_mod.lookup_signature(snippets, 'python', 'algorithmic') == 'py2'


def test_lookup_signature_sql_uses_mysql(fetch_mod):
    """SQL problems always pick the mysql snippet, regardless of config language."""
    snippets = [
        {'langSlug': 'mysql',      'code': 'select 1'},
        {'langSlug': 'typescript', 'code': 'ts'},
    ]
    assert fetch_mod.lookup_signature(snippets, 'typescript', 'SQL') == 'select 1'


def test_lookup_signature_no_match_returns_empty(fetch_mod):
    snippets = [{'langSlug': 'java', 'code': 'java'}]
    assert fetch_mod.lookup_signature(snippets, 'typescript', 'algorithmic') == ''


def test_lookup_signature_empty_inputs(fetch_mod):
    assert fetch_mod.lookup_signature([],   'typescript', 'algorithmic') == ''
    assert fetch_mod.lookup_signature(None, 'typescript', 'algorithmic') == ''


def test_lookup_signature_handles_missing_keys(fetch_mod):
    """A snippet entry without langSlug or code shouldn't crash the lookup."""
    snippets = [
        {'langSlug': None, 'code': None},
        {'langSlug': 'typescript', 'code': 'ts code'},
    ]
    assert fetch_mod.lookup_signature(snippets, 'typescript', 'algorithmic') == 'ts code'


# ── main() — covers each exit code ──────────────────────────────────────────

@pytest.fixture
def stub_fetch(fetch_mod, monkeypatch):
    def _stub(response):
        monkeypatch.setattr(fetch_mod, 'fetch', lambda slug: response)
    return _stub


def _run_main(fetch_mod, argv, capsys):
    monkey_argv = [sys.argv[0]] + argv
    old_argv = sys.argv
    sys.argv = monkey_argv
    try:
        rc = fetch_mod.main()
    finally:
        sys.argv = old_argv
    captured = capsys.readouterr()
    return rc, captured


def test_main_writes_manifest_to_file(fetch_mod, stub_fetch, tmp_path, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1',
        'title':               'Two Sum',
        'difficulty':          'Easy',
        'content':             '<p>Given an array...</p>',
        'topicTags':           [{'slug': 'array'}, {'slug': 'hash-table'}],
        'codeSnippets':        [{'langSlug': 'typescript',
                                 'code': 'function twoSum() {}'}],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, cap = _run_main(fetch_mod, ['two-sum', '--out', str(out_path)], capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload['number']     == 1
    assert payload['title']      == 'Two Sum'
    assert payload['difficulty'] == 'Easy'
    assert payload['type']       == 'algorithmic'
    assert 'Given an array' in payload['statement']
    assert payload['signature']  == 'function twoSum() {}'


def test_main_includes_signature_for_default_language(fetch_mod, stub_fetch,
                                                      tmp_path, capsys):
    """Default language (no config.json) is TypeScript — manifest signature
    should be the typescript snippet, picked from a multi-language list."""
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1',
        'title':               'Two Sum',
        'difficulty':          'Easy',
        'content':             '<p>...</p>',
        'topicTags':           [{'slug': 'array'}],
        'codeSnippets': [
            {'langSlug': 'cpp',        'code': '// cpp signature'},
            {'langSlug': 'typescript', 'code': 'function twoSum() {}'},
            {'langSlug': 'python3',    'code': 'def twoSum(self): ...'},
        ],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, _ = _run_main(fetch_mod, ['two-sum', '--out', str(out_path)], capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload['signature'] == 'function twoSum() {}'


def test_main_signature_empty_when_language_missing_from_snippets(
        fetch_mod, stub_fetch, tmp_path, capsys):
    """If LC has no snippet for the user's language, manifest.signature is ''
    and scaffold_new will write an empty solution file."""
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1',
        'title':               'Two Sum',
        'difficulty':          'Easy',
        'content':             '<p>...</p>',
        'topicTags':           [{'slug': 'array'}],
        'codeSnippets':        [{'langSlug': 'cpp', 'code': '// cpp only'}],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, _ = _run_main(fetch_mod, ['two-sum', '--out', str(out_path)], capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload['signature'] == ''


def test_main_signature_for_sql_uses_mysql(fetch_mod, stub_fetch, tmp_path, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '177',
        'title':               'Nth Highest Salary',
        'difficulty':          'Medium',
        'content':             '<p>...</p>',
        'topicTags':           [{'slug': 'database'}],
        'codeSnippets': [
            {'langSlug': 'mysql', 'code': 'CREATE FUNCTION ...'},
            {'langSlug': 'typescript', 'code': 'unused'},
        ],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, _ = _run_main(fetch_mod, ['nth-highest-salary', '--out', str(out_path)],
                      capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload['signature'] == 'CREATE FUNCTION ...'


def test_main_does_not_leak_tags_in_manifest(fetch_mod, stub_fetch, tmp_path, capsys):
    """Topic tags would hint at the problem's pattern (e.g. 'breadth-first-search').
    They MUST be excluded from the manifest output."""
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1654',
        'title':               'Minimum Jumps to Reach Home',
        'difficulty':          'Medium',
        'content':             '<p>...</p>',
        'topicTags':           [{'slug': 'array'},
                                {'slug': 'breadth-first-search'},
                                {'slug': 'hash-table'}],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, _ = _run_main(fetch_mod, ['minimum-jumps-to-reach-home',
                                  '--out', str(out_path)], capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert 'tags' not in payload
    assert 'breadth-first-search' not in out_path.read_text()


def test_main_stdout_is_summary_only(fetch_mod, stub_fetch, tmp_path, capsys):
    """Stdout must be a short summary — no manifest JSON. Otherwise the tool
    output leaks the problem statement back into the conversation."""
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1',
        'title':               'Two Sum',
        'difficulty':          'Easy',
        'content':             '<p>Given an array of integers, return indices...</p>',
        'topicTags':           [{'slug': 'array'}],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, cap = _run_main(fetch_mod, ['two-sum', '--out', str(out_path)], capsys)
    assert rc == 0
    assert 'Given an array' not in cap.out  # statement not on stdout
    assert 'fetched: 1. Two Sum (Easy)' in cap.out
    assert str(out_path) in cap.out


def test_main_classifies_sql(fetch_mod, stub_fetch, tmp_path, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '177',
        'title':               'Nth Highest Salary',
        'difficulty':          'Medium',
        'content':             '<p>Write a SQL query...</p>',
        'topicTags':           [{'slug': 'database'}],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, _ = _run_main(fetch_mod, ['nth-highest-salary',
                                  '--out', str(out_path)], capsys)
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload['type'] == 'SQL'


def test_main_not_found(fetch_mod, stub_fetch, tmp_path, capsys):
    stub_fetch({'data': {'question': None}})
    out_path = tmp_path / 'manifest.json'
    rc, cap = _run_main(fetch_mod, ['no-such-slug',
                                    '--out', str(out_path)], capsys)
    assert rc == 1
    assert 'not found' in cap.err
    assert not out_path.exists()  # no manifest written on failure


def test_main_premium(fetch_mod, stub_fetch, tmp_path, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '999',
        'title':               'Premium Problem',
        'difficulty':          'Hard',
        'content':             '',
        'topicTags':           [],
    }}})
    out_path = tmp_path / 'manifest.json'
    rc, cap = _run_main(fetch_mod, ['premium-problem',
                                    '--out', str(out_path)], capsys)
    assert rc == 2
    assert 'premium' in cap.err
    assert not out_path.exists()


def test_main_invalid_arg(fetch_mod, capsys):
    rc, _ = _run_main(fetch_mod, ['Nonsense Title!'], capsys)
    assert rc == 64


def test_main_no_arg(fetch_mod, capsys):
    rc, _ = _run_main(fetch_mod, [''], capsys)
    assert rc == 64


def test_main_network_failure(fetch_mod, monkeypatch, tmp_path, capsys):
    import urllib.error

    def _boom(slug):
        raise urllib.error.URLError('connection refused')
    monkeypatch.setattr(fetch_mod, 'fetch', _boom)
    out_path = tmp_path / 'manifest.json'
    rc, cap = _run_main(fetch_mod, ['two-sum', '--out', str(out_path)], capsys)
    assert rc == 3
    assert 'network failure' in cap.err
    assert not out_path.exists()


def test_main_default_out_path(fetch_mod):
    """The default --out path should be /tmp/leetcode-workflow-manifest.json
    so SKILL.md prose can refer to it by a stable name."""
    assert fetch_mod.DEFAULT_MANIFEST_PATH == '/tmp/leetcode-workflow-manifest.json'
