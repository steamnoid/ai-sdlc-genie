import inspect
import logging
from collections.abc import Sequence
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage

from aisdlc.domain.models import DiscoveryReport, Stage
from aisdlc.graph.state import AgentState
from aisdlc.llm.factory import get_llm
from aisdlc.tools.repository import RepositoryListing, list_files, read_file

logger = logging.getLogger(__name__)


def _repository_id(state: AgentState) -> str:
    """Return the repository identifier from the canonical work item or API state."""
    work_item = state.get("work_item")
    repository_id = work_item.repository_id if work_item is not None else state.get("repository_id")
    if not repository_id:
        raise ValueError("Discovery requires a repository identifier.")
    return repository_id


def _stage_update(state: AgentState, stage: Stage) -> dict[str, Any]:
    """Create a state update that preserves the WorkItem as the domain source of truth."""
    update: dict[str, Any] = {"stage": stage}
    work_item = state.get("work_item")
    if work_item is not None:
        update["work_item"] = work_item.model_copy(update={"stage": stage})
    return update


async def _close_llm_client(llm: Any) -> None:
    """Release the asynchronous client owned by a freshly created LLM model."""
    client = getattr(llm, "async_client", None)
    close = getattr(client, "aclose", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result

#: Files whose content is worth sending to the model, in priority order.
CONTEXT_FILE_NAMES: Final[tuple[str, ...]] = (
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "README.md",
)
#: Upper bounds keep the prompt small enough for local models.
MAX_CONTEXT_FILES: Final[int] = 4
MAX_INVENTORY_PATHS: Final[int] = 400
MAX_FILE_CHARS: Final[int] = 6_000

#: How the provider is asked for structured output.
#:
#: `function_calling` is used rather than `json_schema` because it is the only
#: method an OpenAI-compatible endpoint is obliged to honour. Against
#: https://ollama.com/v1, `json_schema` and `json_mode` both return prose that
#: fails Pydantic validation, while `function_calling` returns a validated
#: report. §29 requires the same graph to serve a cloud model and a local
#: Ollama model, so the widest-supported mechanism is the one to bind to.
STRUCTURED_OUTPUT_METHOD: Final[str] = "function_calling"


def select_context_files(files: Sequence[str]) -> tuple[str, ...]:
    """Choose the most informative files to read, deterministically.

    Args:
        files: Repository-relative paths.

    Returns:
        Up to :data:`MAX_CONTEXT_FILES` paths, ordered by :data:`CONTEXT_FILE_NAMES`.
    """
    by_name: dict[str, str] = {}
    for path in files:
        filename = path.rsplit("/", 1)[-1]
        by_name.setdefault(filename, path)
    return tuple(by_name[name] for name in CONTEXT_FILE_NAMES if name in by_name)[:MAX_CONTEXT_FILES]


async def build_repository_context(repository_id: str, listing: RepositoryListing) -> str:
    """Assemble the bounded textual context handed to the discovery model.

    Args:
        repository_id: Repository in ``owner/name`` format.
        listing: Inventory returned by :func:`aisdlc.tools.repository.list_files`.

    Returns:
        Inventory excerpt plus the content of the most informative files.

    Raises:
        RepositoryError: If a selected file cannot be read.
    """
    inventory = list(listing.files)[:MAX_INVENTORY_PATHS]
    sections = [f"Repository Structure ({len(listing.files)} files, showing {len(inventory)}):", *inventory]

    for path in select_context_files(listing.files):
        content = (await read_file(repository_id, path, ref=listing.ref)).strip()
        if len(content) > MAX_FILE_CHARS:
            content = f"{content[:MAX_FILE_CHARS]}\n... [truncated]"
        sections.append(f"\n--- {path} ---\n{content}")

    return "\n".join(sections)


async def discover(state: AgentState) -> dict[str, Any]:
    """
    Discovery Node: Analyzes the target repository using tools and LLM 
    to generate a structured DiscoveryReport.
    """
    repo_id = _repository_id(state)
    logger.info("Starting discovery for repository %s", repo_id)
    
    try:
        listing = await list_files(repo_id)
        context = await build_repository_context(repo_id, listing)
    except Exception as error:
        logger.exception("Failed to gather repository context for %s", repo_id)
        raise RuntimeError(f"Could not retrieve repository context for {repo_id}") from error

    system_prompt = (
        "You are the Repository Discovery Agent. You receive a file inventory "
        "and the contents of a few manifest files, and you describe what the "
        "repository is and how it is put together. Be concrete: name the paths "
        "you actually read."
    )

    user_prompt = (
        f"Repository ID: {repo_id}\n\nContext:\n{context}\n\n"
        "Identify the languages, frameworks, build system and CI system. "
        "In key_components, name the directories or modules that carry the "
        "design, exactly as they appear in the inventory. "
        "In identified_files, list the individual files that best characterise "
        "the repository, using the same paths as the inventory. "
        "In architecture_summary, explain how those parts fit together and how "
        "control flows between them."
    )

    try:
        llm = get_llm()
        try:
            structured = llm.with_structured_output(
                DiscoveryReport, method=STRUCTURED_OUTPUT_METHOD
            )
            report = await structured.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )
        finally:
            await _close_llm_client(llm)

        if not isinstance(report, DiscoveryReport):
            raise TypeError(
                f"Structured discovery output was {type(report).__name__}, "
                "not a DiscoveryReport."
            )
        if report.repository_id != repo_id:
            report = report.model_copy(update={"repository_id": repo_id})

        return {
            "discovery_report": report,
            "messages": [f"Discovery completed for {repo_id}."],
            **_stage_update(state, Stage.AWAITING_HUMAN_APPROVAL),
        }
    except Exception:
        logger.exception("Discovery failed for repository %s", repo_id)
        raise


async def human_approval(state: AgentState) -> dict[str, Any]:
    """
    Human Approval Node: Receives discovery report and awaits human decision.
    
    This is a placeholder node that represents a workflow pause point where
    human stakeholders review and approve the discovery report before proceeding
    to implementation phases.
    
    Returns:
        Dictionary with updated state: stage moved to READY upon approval.
    """
    repo_id = _repository_id(state)
    discovery_report = state.get("discovery_report")
    
    logger.info("Awaiting human approval for repository %s", repo_id)
    
    if not discovery_report:
        logger.warning("No discovery report found; cannot proceed with approval.")
        return {
            "messages": ["No discovery report available for approval."],
            **_stage_update(state, Stage.IDLE),
        }
    
    if state.get("approval_granted") is not True:
        return {
            "messages": [f"Discovery report for {repo_id} is awaiting human approval."],
            **_stage_update(state, Stage.AWAITING_HUMAN_APPROVAL),
        }

    logger.info("Human approval completed for %s. Moving to READY stage.", repo_id)
    
    return {
        "messages": [f"Discovery report approved for {repo_id}. Ready for implementation."],
        **_stage_update(state, Stage.READY),
        "discovery_report": discovery_report
    }