"""Bootstrap subprocess coverage measurement.

Python automatically imports `sitecustomize` at startup if it sits on
sys.path. When tests/conftest.py prepends the repo root to PYTHONPATH,
every subprocess spawned by the test suite picks this file up before
any user code runs.

Gated on COVERAGE_PROCESS_START so this is a no-op outside coverage
runs. Bare `pytest` invocations never trigger measurement.
"""
import os

if os.environ.get('COVERAGE_PROCESS_START'):
    try:
        import coverage
        coverage.process_startup()
    except ImportError:
        pass
