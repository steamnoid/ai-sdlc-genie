"""The real-dependency tiers must stay out of the default pytest run.

§22: "Normal `pytest` must remain fast and deterministic" and integration
tests "must be opt-in". These tests encode that as an executable
expectation rather than as prose, so a future edit to pyproject.toml that
accidentally re-admits a network tier fails the suite.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

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
    """Arrange/Act/Assert: a bare `pytest` collects no real-dependency test.

    This is the §22 guarantee. It is asserted by collecting the suite
    exactly as a developer would run it and checking that no e2e or
    integration path is among the collected items.
    """
    # Act
    result = _run_pytest("--collect-only", "-q")

    # Assert
    assert result.returncode == 0, result.stdout + result.stderr
    collected = {
        line.split("::", 1)[0]
        for line in result.stdout.splitlines()
        if "::" in line
    }
    real_tier_files = {
        path
        for path in collected
        if path.startswith("tests/e2e") or path.startswith("tests/integration")
    }
    assert not real_tier_files, (
        f"the default run collected real-dependency tests: {sorted(real_tier_files)}"
    )
