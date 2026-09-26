"""RED — the Discovery agent has never been observed against a real model.

Rule 0.8: "An agent is not implemented until it has been observed producing
validated output against a real model on a real repository." Every existing
test patches get_llm and list_files, so the plumbing is proven and the agent
is not. This is that observation, and it is the first e2e test in the
project that touches neither a mock nor a fake.

The assertions are contracts, never exact content. Real output varies per
run, so this file checks:

- the raw model output validates into DiscoveryReport without repair
- required fields are non-empty
- no placeholder text survives, which is the rule nodes.py:130-134 currently
  begs for in prompt text instead of asserting
- the report is grounded in the real inventory, not invented
- the stage advanced to the human-approval boundary

Run it with: uv run pytest -m e2e_smoke
"""

from __future__ import annotations

import pytest

from aisdlc.domain.models import DiscoveryReport, Stage
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState
from aisdlc.tools.repository import list_files

#: Cheap real-agent gate: one repository, one provider (§0.8, §29).
pytestmark = [pytest.mark.e2e_smoke, pytest.mark.asyncio]

#: Phrases that mean the model refused to answer. nodes.py:130-134 asks for
#: these in prose; here they are asserted, per the Rule 0.8 corollary.
PLACEHOLDER_PHRASES = (
    "no summary provided",
    "not available",
    "n/a",
    "none provided",
    "cannot determine",
    "unable to determine",
    "as an ai",
    "i cannot",
    "sorry",
    "```",
)


def _assert_grounded(report: DiscoveryReport, inventory: tuple[str, ...]) -> None:
    """Assert the report only claims paths that exist in the real inventory.

    Rule 0.8 requires groundedness: a real agent describing a real
    repository must not cite files that are not there.

    A cited entry is grounded when it is a known file, or when it is a
    directory prefix of a known file. The inventory lists regular files
    only, so ``src/click`` is legitimate even though no such file exists:
    it names the directory that holds ``src/click/core.py``.

    Args:
        report: The report produced by the real model.
        inventory: Repository-relative paths fetched from real GitHub.

    Raises:
        AssertionError: If the report cites a path that is neither a known
            file nor a directory containing one.
    """
    cited = set(report.identified_files) | set(report.key_components)
    # Only judge entries that look like paths; a bare component name such as
    # "parser" or "dispatcher" is a concept, not a claim about a location.
    path_like = {entry for entry in cited if "/" in entry or "." in entry}
    known = set(inventory)

    def is_grounded(entry: str) -> bool:
        if entry in known:
            return True
        return any(
            path.startswith(f"{entry}/") for path in known
        )

    invented = {entry for entry in path_like if not is_grounded(entry)}
    assert not invented, (
        f"report cites paths that are not in the real inventory: {sorted(invented)}"
    )


async def test_discovery_agent_produces_a_grounded_report_against_a_real_model(
    e2e_repository_id: str,
) -> None:
    """Arrange/Act/Assert: a real model analyses a real repository.

    Arrange: fetch the real inventory so groundedness can be checked.
    Act: run the Discovery node with no patched tool and no patched model.
    Assert: the report validates, is complete, is placeholder-free, is
        grounded, and the work item advanced to the approval boundary.
    """
    # Arrange
    listing = await list_files(e2e_repository_id)
    assert listing.files, f"real inventory for {e2e_repository_id} is empty"

    state: AgentState = {
        "repository_id": e2e_repository_id,
        "stage": Stage.IN_PROGRESS_BY_AGENT,
        "discovery_report": None,
        "messages": [],
    }

    # Act
    update = await discover(state)

    # Assert: the stage advanced to the human-approval boundary
    assert update["stage"] == Stage.AWAITING_HUMAN_APPROVAL

    report = update.get("discovery_report")
    assert isinstance(report, DiscoveryReport), (
        f"real model did not yield a DiscoveryReport, got {type(report).__name__}"
    )
    assert report.repository_id == e2e_repository_id

    # Assert: required fields carry real content
    summary = report.architecture_summary.strip()
    assert len(summary) > 80, f"architecture_summary is too thin to be real: {summary!r}"

    # Assert: the report names concrete components, otherwise groundedness
    # below would have nothing to check and the whole e2e test would be
    # vacuous. A real model reading a real repository can always name files.
    assert report.identified_files or report.key_components, (
        "the report names no files and no components, so groundedness cannot "
        "be verified; a real repository always has identifiable structure"
    )

    # Assert: no placeholder text survived the prompt's plea for content
    haystack = " ".join(
        [summary, *(entry for entry in report.key_components if entry)]
    ).lower()
    for phrase in PLACEHOLDER_PHRASES:
        assert phrase not in haystack, (
            f"report contains the placeholder {phrase!r}; the prompt asks for "
            "content but nothing verified it until now"
        )

    # Assert: the report is grounded in the repository that was actually read
    _assert_grounded(report, listing.files)
