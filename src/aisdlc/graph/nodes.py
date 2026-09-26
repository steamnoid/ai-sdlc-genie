import inspect
import json
import logging
import re
from typing import Any, Final, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from aisdlc.domain.models import DiscoveryReport, FrameworkInfo, LanguageInfo, Stage
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


def clean_json_output(text: str) -> str:
    """
    Removes markdown code blocks (e.g. ```json ... ```) from LLM output
    to ensure it can be parsed as pure JSON.
    """
    cleaned = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
    return cleaned.strip()

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
        "You are the Repository Discovery Agent. Analyze the repository context "
        "and provide a structured JSON response. IMPORTANT: Do NOT use markdown "
        "code blocks. Return ONLY the raw JSON object."
    )
    
    user_prompt = (
        f"Repository ID: {repo_id}\n\nContext:\n{context}\n\n"
        "Identify languages, frameworks, build system, and CI. "
        "CRITICAL: You MUST provide a detailed, professional technical analysis "
        "of the architecture in the architecture_summary field. "
        "Explain the folder structure and how components interact. "
        "IT IS FORBIDDEN to use placeholders like 'No summary provided' or 'Not available'. "
        "Failure to provide a detailed analysis will be considered a system failure."
    )
    
    try:
        llm = get_llm()
        try:
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
        finally:
            await _close_llm_client(llm)
        
        raw_content = response.content
        if not isinstance(raw_content, str):
            raise TypeError("Discovery model returned non-text content.")
        cleaned_content = clean_json_output(raw_content)
        
        try:
            report = DiscoveryReport.model_validate_json(cleaned_content)
        except ValueError:
            logger.warning("Direct discovery-report validation failed; normalizing model output.")
            data = json.loads(cleaned_content)
            if not isinstance(data, dict):
                raise TypeError("Discovery model response must be a JSON object.")
            
            def extract_name(value: Any) -> str:
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    name = value.get("name") or value.get("language") or value.get("framework")
                    if not isinstance(name, str) or not name:
                        raise ValueError("Discovery language/framework entry requires a name.")
                    return name
                raise TypeError("Discovery language/framework entries must be strings or objects.")

            def extract_val(value: Any) -> str | None:
                if value is None or isinstance(value, str):
                    return value
                if isinstance(value, dict) and len(value) == 1:
                    extracted = next(iter(value.values()))
                    return extracted if isinstance(extracted, str) else None
                raise ValueError("Discovery scalar fields must be strings.")

            architecture_summary = extract_val(data.get("architecture_summary"))
            if not architecture_summary:
                raise ValueError("Discovery report requires a non-empty architecture summary.")

            report = DiscoveryReport(
                repository_id=data.get("repository_id", repo_id),
                languages=[LanguageInfo(name=extract_name(language)) for language in data.get("languages", [])],
                frameworks=[FrameworkInfo(name=extract_name(framework)) for framework in data.get("frameworks", [])],
                build_system=extract_val(data.get("build_system")),
                ci_system=extract_val(data.get("ci_system")),
                architecture_summary=architecture_summary,
                key_components=data.get("key_components", []),
                identified_files=data.get("identified_files", []),
                suggested_changes=data.get("suggested_changes", [])
            )
        
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