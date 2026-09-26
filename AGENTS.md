# AGENTS.md — AI SDLC (`aisdlc`)

AI-native Application Lifecycle Management: a stateful multi-agent system that onboards an
arbitrary public GitHub repository, reasons about it through a LangGraph workflow with
human approval gates, and produces a traceable Pull Request.

Normative spec lives in `.github/instructions/ai-sdlc-genie.md.instructions` (§N references
throughout point there). This file is the operational manual for working *in this repository*:
what is true today, which rules are binding, and how to change the code.

---

# RULE 0 — Strict TDD is the only sanctioned way to change this codebase

Every behaviour change follows **RED → GREEN → REFACTOR → GATE**, in that order, without exception.

**0.1 The cycle**

1. **RED** — write the failing test first. It must fail for the *right* reason: an assertion
   about behaviour. Never `ImportError`, `NameError`, or `AttributeError`. Paste the failure output.
2. **GREEN** — write the smallest implementation that passes. No speculative parameters, no
   unrequested dependencies, no abstraction without a caller.
3. **REFACTOR** — improve with the suite green. Re-run after every step.
4. **GATE** — `uv run pytest -q && uv run ruff check . && uv run mypy src` all clean, or the work
   is not done.

**0.2 Variant A — deterministic code (Layer A)**

Domain, persistence, graph routing, tools, API/CLI wiring. Classic strict TDD: the test always
precedes the implementation. These tests run with **no network, no API keys, no Docker**.
Names follow §20, e.g. `test_illegal_transition_is_rejected`, `test_only_assigned_agent_can_mutate`,
`test_done_state_has_no_agent`, `test_duplicate_orchestrator_run_is_idempotent`.

**0.3 Variant B — agentic code (Layer B)**

You cannot TDD reasoning, so you TDD the **contract and the plumbing** (§40):

1. Define the Pydantic output model.
2. Write the test against a **fake model** (stubbed `ainvoke` returning fixed text) asserting that
   the node maps raw text → validated model, and that malformed output is rejected or repaired
   deterministically.
3. Implement the node.
4. Reasoning *quality* is owned by `evals/` (golden datasets, DeepEval), never by pytest.

**0.4 Commit discipline**

Each cycle is exactly two commits, Conventional Commits (matching the existing
`feat(foundation): …` history):

```
test(<scope>): RED — <the specific expectation that fails>
feat(<scope>): <the behaviour that now holds>
```

- The RED commit is *expected* to leave the suite red, and must be paired with the very next commit.
- A GREEN commit with no preceding RED commit on the branch is a Rule 0 violation.
- An optional third `refactor(<scope>): …` commit keeps the suite green.

**0.5 Forbidden**

- Implementation written before a failing test demands it.
- `pytest.skip`, a commented-out assert, or a `# type: ignore` added to turn the suite green.
- Writing the test after the code and calling it TDD.
- Adding a dependency to make something testable — inject a seam instead.
- Widening scope mid-cycle. A new capability is a new cycle.

**0.6 The hygiene check that matters most**

`uv run pytest -q` must stay green with **no network and no API keys**. If it needs
`GITHUB_TOKEN` or `OPENAI_API_KEY`, a boundary is wrong. Real Postgres / pgvector / Redis belong
behind `@pytest.mark.integration` (§22).

**0.7 Precedence**

Rule 0 > this file > `.github/instructions/ai-sdlc-genie.md.instructions`. For LangChain /
LangGraph / LangSmith APIs, the **current official documentation beats all three** (§42) — that
ecosystem changes fast and model memory is not a source.

**0.8 A real agent is tested by a real agent**

An agent is not implemented until it has been observed producing validated output against a real
model on a real repository. Mocked tests prove plumbing; only `tests/e2e/` proves the agent.
Shipping an agent without a real-agent test is a Rule 0 violation.

*Corollary — quality rules live in assertions, not in prompt text.* If a prompt has to **forbid**
something, a test must **assert** it. `src/aisdlc/graph/nodes.py:130-134` currently begs the model
not to emit `"No summary provided"`; under this rule that becomes
`assert "no summary provided" not in report.architecture_summary.lower()`. Prompt begging is not
verification.

- **e2e asserts contracts, never exact content.** Real output varies per run. Assert: Pydantic
  validation passes · required fields non-empty · no placeholder text · groundedness (cited paths
  exist in the real inventory) · stage advanced correctly.
- **Skip loudly, never silently.** A missing key or unreachable provider produces `pytest.skip`
  *with the reason printed*. A green run that never called a model is a lie.
- **Provider coverage is parametrized** (§29) — one provider per run. The architecture claim is
  proven by running the suite twice (`LLM_PROVIDER=openai`, then `LLM_PROVIDER=ollama`), never by
  rewriting an agent.
- **Repositories are never hard-coded** (§4) — `E2E_REPOSITORY` env var, ≥2 distinct public repos.
- **e2e ≠ evals.** e2e asks *does the agent work at all*. `evals/` asks *does it reason well*.

**0.9 Completing the project**

§46 is delivered as vertical slices (§9). A slice closes only when the test was written first, the
gate is green, docs match the code, and its §46 checkbox flips. Never jump ahead — §47 exists
precisely so this stays tractable.

---

# 1. Mission & current status

```text
GitHub repository → onboard → discover → [approval] → PO → [approval] → QA → [approval]
  → architecture → [approval] → security → [approval] → implementation plan → [approval]
  → implementation → QA verification → [approval] → Pull Request
```

The goal is **not** an impressive AI demo. It is a deterministic software system in which LLM
agents perform bounded reasoning inside explicit contracts, state machines, tools, evaluation loops
and human approval gates. Making the boundary between deterministic software and probabilistic AI
*obvious* is a core feature of the product (§49).

| Phase | Scope | Status |
|---|---|---|
| 1 | domain models, state machine, pytest | done |
| 2 | LangGraph: state, routing, nodes, HITL interrupt | done (2 nodes only) |
| 3 | first real agent: Repository Discovery | done (no real-agent e2e — see §10) |
| **0** | **test + e2e harness** | **pending — do this first** |
| 4 | tools + MCP (GitHub, filesystem, test runner) | pending |
| 5 | RAG: indexing, embeddings, pgvector, retrieval | pending |
| 6 | remaining agents: PO, QA, ARCH, SEC, DEV_PLAN, DEV_IMPL, QA_VERIFY, PR | pending |
| 7 | LangSmith: tracing, metadata, datasets, eval hooks | pending |
| 8 | evaluation: golden datasets, Promptfoo, DeepEval | pending |
| 9 | FastAPI + CLI, sharing one application layer | pending |
| 10 | Docker, docs, security hardening, health checks | pending |

---

# 2. Architecture: three layers

**Layer A — deterministic application logic.** State, invariants, permissions, transitions,
persistence, GitHub/filesystem operations, test execution, validation, API contracts.
**This layer MUST NOT depend on an LLM.** If something can be deterministic, make it deterministic.

**Layer B — agentic reasoning.** Repository understanding, requirements, acceptance criteria, QA
scenarios, architecture and security analysis, implementation planning, code generation, review.
Uses LangGraph + LangChain.

**Layer C — observability & evaluation.** Traces, runs, latency, token usage, model comparison,
golden datasets, regression checks. LangSmith + Promptfoo/DeepEval.

*Which layer does this file belong to?* If it can be unit-tested with no network and no model, it is
Layer A. If its output is produced by a model, it is Layer B. If it observes or scores the other two,
it is Layer C.

## Allowed import direction

| Package | May import |
|---|---|
| `domain/` | nothing but stdlib + pydantic |
| `persistence/` | `domain` + sqlalchemy |
| `llm/` | stdlib + langchain + pydantic (no application imports) |
| `tools/` | stdlib + third-party (no application imports) |
| `graph/` | `domain`, `llm`, `tools` |
| `api/`, `application/`, `cli.py` (planned) | `graph`, `domain`, `persistence` — never the reverse |

The domain layer must stay usable without MCP, without LangGraph and without a model (§43).
A test that imports a model into `domain/` is a bug in the test.

---

# 3. Domain invariants — non-negotiable

The work-item state machine is a first-class domain object (`src/aisdlc/domain/`).
**Never let an LLM directly mutate state.** Use `transition()`; it is the only door.

```text
STAGE ∈ { IDLE, AWAITING_HUMAN_APPROVAL, IN_PROGRESS_BY_AGENT, AWAITING_AGENT_PICKUP, READY, DONE }
ROLE  ∈ { PO, DEV, QA, SEC, ARCH, AI }
AGENT = explicit identifier, e.g. aialm-po-analyze, aialm-dev-impl, aialm-pr  (None, never "none")
```

**Biconditional** — `validate_state()` enforces it, and each half needs a test:

```text
AGENT = None  ↔  STAGE ∈ { IDLE, AWAITING_HUMAN_APPROVAL, READY, DONE }
AGENT ≠ None  ↔  STAGE ∈ { AWAITING_AGENT_PICKUP, IN_PROGRESS_BY_AGENT }
```

**The transition table** (`state_machine.py:6-13`) is exhaustive. No implicit transitions, no
"magic" status changes, no LLM-generated arbitrary states:

| From | To |
|---|---|
| `IDLE` | `AWAITING_AGENT_PICKUP` |
| `AWAITING_AGENT_PICKUP` | `IN_PROGRESS_BY_AGENT` |
| `IN_PROGRESS_BY_AGENT` | `AWAITING_HUMAN_APPROVAL`, `AWAITING_AGENT_PICKUP` |
| `AWAITING_HUMAN_APPROVAL` | `AWAITING_AGENT_PICKUP`, `DONE` |
| `READY` | `AWAITING_AGENT_PICKUP` |
| `DONE` | — terminal, no outgoing edges |

Further rules, each with an existing-or-required test in `tests/unit/test_state_machine.py`:

- only one active agent owns a work item; an agent may mutate only work assigned to it;
- `DONE` has no active agent — `transition()` forces `agent = None` on the terminal stages;
- `AI` is a transient handoff role `[not implemented]`;
- illegal transitions fail deterministically via `StateMachineError`;
- **LLM output can never bypass transition validation.**

**Approval semantics** (§36) — an approval must reference the exact artifact *and version*
approved (`work_item_id`, `artifact_id`, `artifact_version`, `approved_by`, `approved_at`). If the
artifact changes afterwards, the previous approval is invalid and a new one is required.
Today the graph carries a bare `approval_granted: bool` `[not implemented]`.

**No autonomous production mutation** (§37) — AI may analyze, propose, prepare, implement in
sandbox and test. **AI must not merge a Pull Request.** Creating the final PR requires an explicit
human approval gate.

---

# 4. Repository layout

```text
src/aisdlc/
├── domain/          # Layer A. models.py (Stage, Role, Repository, WorkItem, DiscoveryReport)
│                    #          state_machine.py (LEGAL_TRANSITIONS, validate_state, transition)
├── persistence/     # Layer A. models.py (SQLAlchemy 2.0 Declarative), session.py, repository.py
├── graph/           # Layer B. state.py (AgentState TypedDict), nodes.py, router.py, workflow.py
├── llm/             # factory.py — LLMConfig, LLMFactory, get_llm
└── tools/           # Layer A. repository.py (GitHubClient), resilience.py (RetryPolicy, retry_async)

tests/
├── unit/            # no network, no model
├── graph/           # [planned] LangGraph flows, fake models
├── integration/     # [planned] @pytest.mark.integration, real infra, opt-in
├── e2e/             # [planned] REAL agent, REAL model, REAL repository
└── evals/           # [planned] golden datasets

evals/  prompts/  docs/  scripts/  docker/     # [planned, §5]
```

Planned items are marked so documentation never documents hypothetical functionality as
implemented (§39). The package is `aisdlc`, while §5 sketches `aialm` — the installed name
(`aialm` → `aisdlc.cli:app`) is currently broken, see §10.

---

# 5. Coding conventions — as this codebase actually does it

- `from __future__ import annotations` at the top of application modules; stdlib, then third-party,
  then local imports.
- Google-style docstrings with `Args:`, `Returns:`, `Raises:` on every public function. Explain
  *why*, not what.
- Module constants are `Final[...]` with a `#:` comment when the rationale is not obvious.
- Value objects and tool payloads are `@dataclass(frozen=True, slots=True)`. Pydantic models that
  cross a boundary are `frozen=True` where mutation is not required (`DiscoveryReport`).
- `Model | None` — never the string `"none"`.
- Validate all external input **at the boundary** before it reaches domain logic.
- Raise typed, specific exceptions (`StateMachineError`, `RepositoryNotFoundError`,
  `GitHubAPIError`, `RetryExhaustedError`, `LLMConfigurationError`) and always `raise X from error`.
- Every outbound call declares an explicit timeout and routes through `retry_async` with a bounded
  `RetryPolicy`. **Retries are bounded; never retry indefinitely** (§32).
- Log structured context (`work_item_id`, `agent`, `stage`). **Never log or print secrets**, and
  never send them to a model (§17, §27).
- No abstraction without a caller. No dependency without a concrete problem it solves.
- Do not rewrite working code without a reason.
- Tooling: ruff line-length 100, target `py312`; mypy `disallow_untyped_defs` +
  `check_untyped_defs`; Python ≥3.12.
- Commits: Conventional Commits, two per TDD cycle (Rule 0.4).

---

# 6. Commands

```bash
uv sync                              # install deps + repoint the editable package at this repo
uv run pytest -q                     # default suite: unit + graph, no network, no keys
uv run pytest -m e2e_smoke           # cheap real-agent gate: 1 repo, 1 provider
uv run pytest -m e2e                 # full real-agent matrix (expensive)
uv run pytest -m integration         # real Postgres / pgvector / Redis
uv run ruff check .                  # lint
uv run mypy src                      # type check
```

> **Before trusting any result, confirm you are running *this* repo's code:**
> `uv run python -c "import aisdlc; print(aisdlc.__file__)"`
> It must resolve under `…/ai-sdlc-genie-opencode/src`. The checked-in `.venv` currently points at
> a sibling checkout, which silently runs the wrong sources (§10).

Always use `uv run`. A bare `python -m pytest` may bind to the wrong interpreter or the wrong
package path.

---

# 7. Testing taxonomy

| Suite | Network | Model | Infra | Marker | Invoked by |
|---|---|---|---|---|---|
| `tests/unit/` | — | mocked | — | — | `pytest` (default) |
| `tests/graph/` | — | fake `ainvoke` | — | `graph` | `pytest` (default) |
| `tests/e2e_smoke` | real GitHub | **real** | — | `e2e_smoke` | `-m e2e_smoke` |
| `tests/e2e/` | real GitHub | **real** | — | `e2e` | `-m e2e` |
| `tests/integration/` | real GitHub | mocked | real PG / pgvector / Redis | `integration` | `-m integration` |
| `evals/` | real | real | real | — | Promptfoo / DeepEval |

Four real-dependency tiers, three invocations. The default `pytest` run touches no network and no
credentials, keeping §22 satisfied ("normal `pytest` must remain fast and deterministic"), while
`e2e_smoke` gives every commit a real-agent signal. Where a test needs a key that is absent, it must
`skip` **with the reason printed** — never pass vacuously.

## Rules

- **No real GitHub and no real LLM in `tests/unit/` or `tests/graph/`.** Patch at the module
  boundary (`aisdlc.graph.nodes.get_llm`, `aisdlc.graph.nodes.list_files`).
- **Real-agent tests assert contracts, not content.** Validation succeeds · required fields
  non-empty · no placeholder text · groundedness (cited paths exist in the real inventory) · stage
  advanced. Never exact strings — real output varies per run.
- **Everything async needs `@pytest.mark.asyncio`.** `asyncio_mode = "strict"`; the marker is not
  inferred. Async *fixtures* need `@pytest_asyncio.fixture`.
- Persistence tests use in-memory SQLite (`sqlite+aiosqlite:///:memory:`), never a live database.
- Name tests after the behaviour and the rule they protect (§20). Docstrings state the
  Arrange / Act / Assert intent.
- Integration and e2e tests are **opt-in** and must declare their external dependencies in
  `conftest.py` so the reason for a skip is visible.

---

# 8. Working loop for an agent on this repo

1. Read `.github/instructions/ai-sdlc-genie.md.instructions` §N for the rule you are about to touch,
   and this file for how the repo actually is.
2. Inspect the existing architecture, the neighbouring code and the relevant tests.
3. If an external framework API is involved, **verify it against current official documentation**
   (§42). Do not rely on model memory, and do not copy old LangGraph tutorials.
4. Propose the smallest coherent change — one capability, one cycle (Rule 0.9).
5. Write the test (RED), implement (GREEN), refactor, gate (Rule 0.1).
6. For a new agent, also write the real-agent e2e test (Rule 0.8) and the evals entry.
7. Run the full gate: `pytest` + `ruff` + `mypy`.
8. Update the documentation in the same cycle — docs must match the implementation (§39).
9. Update §9 phase status and §10 if you closed a gap.

---

# 9. Backlog — vertical slices with TDD gates

Do not build everything at once (§47). One slice, one cycle set, one gate.

### Phase 0 — test + e2e harness *(do this first)*

Nothing else scales until this exists. Exit gate: `pytest -q`, `ruff`, `mypy` clean, **and**
`pytest -m e2e_smoke` green against a real provider.

- `tests/conftest.py`: skip-reason gating, real-LLM fixture, provider fixture, `E2E_REPOSITORY` fixture.
- Register markers `graph`, `e2e_smoke`, `e2e`, `integration`; deselect the real-dependency tiers
  from the default run so §22 still holds.
- Create `tests/{graph,integration,evals}/`; relocate the two fully-mocked files out of `tests/e2e/`.
- **The first true e2e test: Discovery against a real model on a real repository** — the highest-value
  missing test in the project, since the only real agent has never been run unmocked.
- Ship a pre-commit hook for `e2e_smoke`, **opt-in via `AISDLC_E2E_SMOKE=1`**, so a paid endpoint is
  never called by surprise.

### Then, in order

| Phase | Slice | Gate |
|---|---|---|
| 4 | GitHub / filesystem / repository tools + test runner, exposed via MCP (§43) | every tool has typed in/out, timeout, deterministic errors, unit tests |
| 5 | repository indexing, embeddings, pgvector, `retrieve(query, repository_id, filters=None)` | retrieval tested against real Postgres + pgvector, no vector-search-only assumption (§16) |
| 6 | PO, QA, ARCH, SEC, DEV_PLAN, DEV_IMPL, QA_VERIFY, PR — one responsibility each | each agent ships a real-agent e2e test (Rule 0.8) + an evals entry |
| 7 | LangSmith tracing, metadata, datasets, run comparison | a full run is traceable: API → graph → node → agent → LLM → retrieval → tool → transition |
| 8 | golden datasets, Promptfoo, DeepEval, regression | prompt change cannot silently regress a golden dataset |
| 9 | FastAPI + CLI over one shared application layer | no agent logic in the API; no duplicated business logic (§24) |
| 10 | Docker, docker-compose, health checks, docs, security hardening | `api` + `postgres` + `redis` up from a documented command |

### Definition of Done (§46), reduced to checkable items

Each item closes only when a test or command proves it — not by a manual run.

- LangGraph executes end-to-end · state machine deterministic · invariants tested · human approval
  durable · agent ownership enforced · repository discovery works · repository RAG works · GitHub
  integration works · MCP tools work.
- **Local Ollama model usable, cloud model usable — each proven by an e2e run, not by hand** (§29).
- LangSmith tracing works · evaluation dataset exists · Promptfoo and/or DeepEval runs · `pytest` suite passes ·
  FastAPI works · CLI works · docker-compose works · PostgreSQL + pgvector work.
- Retries bounded · operations idempotent (`advance`, `approve`, `create_branch`, `create_pr`,
  `index_repository` — a retry must not duplicate a PR, a work item, or a transition, §26) ·
  secrets protected · README complete · docs match the code · **one end-to-end demo produces a
  traceable PR** (§45).

---

# 10. Known gaps — snapshot of 2026-09-26

Stale the moment code changes. Verify before trusting; fix via Rule 0 and update this list.

| # | Gap | Location |
|---|---|---|
| 1 | `.venv` editable install points at a **sibling checkout** (`…/ai-sdlc-genie/src`), so `pytest` silently runs the wrong sources. Fix: `uv sync`. | `.venv/…/_editable_impl_aisdlc.pth` |
| 2 | `Final`, `Sequence`, `RepositoryListing` are used but never imported → module fails to import, **4 of 17 tests error during collection**, ruff 9 errors, mypy 6 errors. Fix: extend the import block. | `src/aisdlc/graph/nodes.py:45,52-54,57,73` |
| 3 | `human_approval` has no outgoing edge, so the graph can never reach `READY` or `DONE` — the workflow terminates at the first approval. | `src/aisdlc/graph/workflow.py:19-30` |
| 4 | `STAGE_TO_NODE[READY] = "discover"` sends approved work back into discovery instead of to the next agent. | `src/aisdlc/graph/router.py:11` |
| 5 | `READY`/`DONE` both route to `discover`; the router has one target per stage and no post-approval path. | `src/aisdlc/graph/router.py:6-13` |
| 6 | Default DB URL uses `postgresql+asyncpg://` while the project depends on `psycopg[binary]`; `asyncpg` is not installed. | `src/aisdlc/persistence/session.py:9` |
| 7 | Module-level `db_manager` singleton builds an engine at import time — hostile to test isolation and to a clean `/health` startup. | `src/aisdlc/persistence/session.py:53` |
| 8 | `[project.scripts] aialm = "aisdlc.cli:app"` points at a module that does not exist; `typer` and `rich` are declared but unused. `httpx` is imported directly but never declared. | `pyproject.toml:19,47`, `src/aisdlc/tools/repository.py:19` |
| 9 | Discovery hand-rolls `json.loads` plus a normalizer instead of LangChain structured output, so §14's validate → retry/repair loop is only partially implemented. | `src/aisdlc/graph/nodes.py:150-192` |
| 10 | **`tests/e2e/` contains no e2e** — both files mock `get_llm` and `list_files`; `test_llm_connection.py` patches the factory and asserts a `Mock` passthrough. Zero of 17 tests touch a real model or real GitHub. → Phase 0. | `tests/e2e/test_llm_connection.py:19`, `tests/e2e/test_discovery_flow.py:36-38` |
| 11 | **Quality rules in prompt text** — the prompt forbids placeholder output and threatens failure, because no test asserts it. → Rule 0.8 corollary. | `src/aisdlc/graph/nodes.py:130-134` |
| 12 | `transition()` copies the work item but never refreshes `updated_at`; the ORM relies on `onupdate` instead, so the domain and persistence layers disagree on who owns that field. | `src/aisdlc/domain/state_machine.py:53-56`, `src/aisdlc/persistence/models.py:57-62` |
| 13 | `tests/unit/test_llm_factory.py` is **empty** — the model-factory layer (§3, provider abstraction) is untested. | `tests/unit/test_llm_factory.py` |
| 14 | `uv.lock` exists on disk but is gitignored and untracked, contradicting §2/§5 which mandate `uv` with a committed lockfile. | `.gitignore:44` |
| 15 | No `conftest.py`, no registered markers, no CI. `pytest-asyncio` 1.4 is installed without `asyncio_default_fixture_loop_scope`. | `tests/`, `pyproject.toml:49-51` |

**Recorded baseline:** `13 passed, 4 errors` of 17 collected · ruff 9 · mypy 6 — all from gap #2.

**Environment for real-agent work:** cloud via `openai` at `https://ollama.com/v1`
(`LLM_MODEL=gemma4:31b`), local Ollama reachable on `:11434`, and `GITHUB_TOKEN` unset — so the
unauthenticated archive fallback is the de facto GitHub path (`tools/repository.py:256`).

---

# 11. Where the full rules live

| Topic | Section in `.github/instructions/ai-sdlc-genie.md.instructions` |
|---|---|
| Mission, pipeline, production standards | §0, §1.1 |
| Layer A / B / C split | §1 |
| Technology stack, `uv` policy | §2 |
| Model provider abstraction | §3 |
| Repository concept, no hard-coded repos | §4 |
| Project structure | §5 |
| State machine, STAGE/ROLE/AGENT | §6, §7 |
| Legal transitions | §8 |
| LangGraph architecture | §9 |
| Agent responsibilities (9 agents) | §10 |
| Human-in-the-loop | §11 |
| MCP + synchronisation strategy | §12, §43 |
| Tool contracts, Pydantic contracts | §13, §14 |
| Repository RAG, retrieval quality | §15, §16 |
| LangSmith, observability | §17, §33 |
| Evaluation architecture and tools | §18, §19, §44 |
| Deterministic, graph, integration tests | §20, §21, §22 |
| FastAPI, CLI, persistence, idempotency | §23, §24, §25, §26 |
| Security, Docker, local LLM, prompts | §27, §28, §29, §30 |
| Agent design rules, error handling, artifacts, traceability | §31, §32, §34, §35 |
| Approval semantics, no autonomous mutation | §36, §37 |
| Documentation, development methodology, doc lookup | §38, §39, §40, §42 |
| Coding-agent conduct (the ten steps behind §8) | §41, §50 |
| Demo scenario, Definition of Done, phases, anti-patterns | §45, §46, §47, §48 |
| Primary engineering principle, anti-patterns | §48, §49 |
