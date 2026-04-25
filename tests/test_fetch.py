"""
Function-level tests for skills/new/scripts/fetch.py.

Network is mocked by monkey-patching fetch.fetch() on the imported module.
This is the only Phase 2 script tested as a Python function rather than a
subprocess — it does HTTP, and stubbing urllib in a child process is more
trouble than it's worth.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import PLUGIN_ROOT


def _import_fetch():
    """Load fetch.py as a module without running its main()."""
    spec = importlib.util.spec_from_file_location(
        'fetch', PLUGIN_ROOT / 'skills' / 'new' / 'scripts' / 'fetch.py',
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


def test_main_emits_manifest(fetch_mod, stub_fetch, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '1',
        'title':               'Two Sum',
        'difficulty':          'Easy',
        'content':             '<p>Given an array...</p>',
        'topicTags':           [{'slug': 'array'}, {'slug': 'hash-table'}],
    }}})
    rc, cap = _run_main(fetch_mod, ['two-sum'], capsys)
    assert rc == 0
    payload = json.loads(cap.out)
    assert payload['number']     == 1
    assert payload['title']      == 'Two Sum'
    assert payload['difficulty'] == 'Easy'
    assert payload['type']       == 'algorithmic'
    assert payload['tags']       == ['array', 'hash-table']
    assert 'Given an array' in payload['statement']


def test_main_classifies_sql(fetch_mod, stub_fetch, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '177',
        'title':               'Nth Highest Salary',
        'difficulty':          'Medium',
        'content':             '<p>Write a SQL query...</p>',
        'topicTags':           [{'slug': 'database'}],
    }}})
    rc, cap = _run_main(fetch_mod, ['nth-highest-salary'], capsys)
    assert rc == 0
    assert json.loads(cap.out)['type'] == 'SQL'


def test_main_not_found(fetch_mod, stub_fetch, capsys):
    stub_fetch({'data': {'question': None}})
    rc, cap = _run_main(fetch_mod, ['no-such-slug'], capsys)
    assert rc == 1
    assert 'not found' in cap.err


def test_main_premium(fetch_mod, stub_fetch, capsys):
    stub_fetch({'data': {'question': {
        'questionFrontendId': '999',
        'title':               'Premium Problem',
        'difficulty':          'Hard',
        'content':             '',
        'topicTags':           [],
    }}})
    rc, cap = _run_main(fetch_mod, ['premium-problem'], capsys)
    assert rc == 2
    assert 'premium' in cap.err


def test_main_invalid_arg(fetch_mod, capsys):
    rc, cap = _run_main(fetch_mod, ['Nonsense Title!'], capsys)
    assert rc == 64


def test_main_no_arg(fetch_mod, capsys):
    rc, cap = _run_main(fetch_mod, [''], capsys)
    assert rc == 64


def test_main_network_failure(fetch_mod, monkeypatch, capsys):
    import urllib.error

    def _boom(slug):
        raise urllib.error.URLError('connection refused')
    monkeypatch.setattr(fetch_mod, 'fetch', _boom)
    rc, cap = _run_main(fetch_mod, ['two-sum'], capsys)
    assert rc == 3
    assert 'network failure' in cap.err
