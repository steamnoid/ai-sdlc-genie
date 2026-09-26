"""The real-dependency tiers must stay out of the default pytest run.

§22: "Normal `pytest` must remain fast and deterministic" and integration
tests "must be opt-in". These tests encode that as an executable
expectation rather than as prose, so a future edit to pyproject.toml that
accidentally re-admits a network tier fails the suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

#: Repository root, so the nested pytest runs below resolve this project's
#: pyproject.toml and import path no matter where pytest was invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Tiers that need a real model, a real network, or real infrastructure.
REAL_DEPENDENCY_MARKERS = ("e2e_smoke", "e2e", "integration")


def _run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    """Run pytest in a subprocess so the assertion is about real config.

    Asserting against this process's own already-parsed configuration
    would hide the very misconfiguration these tests exist to catch.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


@pytest.mark.parametrize("marker", REAL_DEPENDENCY_MARKERS)
def test_real_dependency_marker_is_registered(marker: str) -> None:
    """Arrange/Act/Assert: every real tier has a declared marker.

    Without registration, `-m e2e` silently selects nothing, which would
    make a green e2e run indistinguishable from an e2e run that never
    happened.
    """
    # Act
    result = _run_pytest("--markers")

    # Assert
    assert result.returncode == 0, result.stderr
    assert f"@pytest.mark.{marker}" in result.stdout


def test_default_run_deselects_every_real_dependency_tier() -> None:
    """Arrange/Act/Assert: a bare `pytest` executes no real-dependency test.

    This is the §22 guarantee. It is measured from an actual verbose run
    rather than from `--collect-only`, because pytest's collection listing
    includes deselected items and therefore cannot distinguish them from
    executed ones.

    The test deselects itself from the nested run. Without that, the
    nested default run would collect this test, which would spawn another
    nested run, without end.
    """
    # Act
    result = _run_pytest(
        "-v",
        "--tb=no",
        "-k",
        "not test_default_run_deselects_every_real_dependency_tier",
    )

    # Assert
    assert result.returncode == 0, result.stdout + result.stderr

    outcomes = ("PASSED", "FAILED", "SKIPPED", "XFAIL", "XPASS", "ERROR")
    executed = {
        node_id
        for line in result.stdout.splitlines()
        if "::" in line
        for node_id, outcome in (line.split(" ", 1),)
        if outcome.split(" ")[0] in outcomes
    }

    # The run must be non-vacuous: something really did execute.
    assert executed, "the nested run executed nothing, so the check proves nothing"

    real_tier_files = {
        path
        for path in executed
        if path.startswith(("tests/e2e", "tests/integration"))
    }
    assert not real_tier_files, (
        f"the default run executed real-dependency tests: {sorted(real_tier_files)}"
    )
