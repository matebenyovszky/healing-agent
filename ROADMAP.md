# Healing Agent roadmap

Healing Agent's direction is a safe repair layer for programs and agents: observe a failure, preserve evidence, propose the smallest repair, verify it in isolation, and return a reviewable result. Runtime mutation remains an explicit opt-in.

This roadmap is ordered by dependency and risk. Each checkbox should be small enough to become one focused issue or pull request.

## Flagship: Data Healing

Data Healing is a primary product direction, not a side case of exception
handling. The target workflow is a supervised Excel, PDF, CSV, JSON, API, or
database loader that encounters a structurally changed source whose contents
can still satisfy the existing business contract.

The differentiator should be the complete governed repair loop:

1. preserve the original document and extraction provenance;
2. profile the failing sample and compare it with known-good samples;
3. distinguish extraction failure, schema drift, and genuinely invalid data;
4. map the changed structure to the canonical Pydantic/data contract;
5. generate a narrow, versioned loader adapter rather than weakening the model;
6. create regression fixtures and replay old plus new document variants;
7. verify business invariants and report ambiguous or missing required fields;
8. run in report/shadow mode before approval, canary activation, and rollback.

Initial vertical slice: Excel column/header/sheet drift into a Pydantic model.
Second slice: PDF table heading/layout drift using pluggable extractors while
retaining page, table, cell, and bounding-box provenance.

## Current release: 0.2.7 safety baseline

- [x] Bound recursive healing with `MAX_ATTEMPTS`.
- [x] Re-raise the original exception whenever healing does not succeed.
- [x] Restore the previous module when a repaired module fails to load or execute.
- [x] Use pytest discovery and propagate its exit status.
- [x] Make invalid configuration fail the overall test run.
- [x] Default new configurations to `AUTO_FIX=False` and `AUTO_SYSCHANGE=False`.
- [x] Add a Python 3.9-3.13 CI matrix and package metadata check.
- [x] Review the 0.2.7 diff and changelog.
- [x] Build the 0.2.7 artifacts and install the wheel in a clean virtual environment.
- [ ] Publish 0.2.7 to TestPyPI and run an install smoke test.
- [ ] Tag `v0.2.7`, create release notes, then publish to PyPI.

## Short term: 0.3 — repairs that can be trusted

### 1. Make proposal-only operation a first-class API

- [ ] Introduce a `RepairResult` containing status, original error, proposal, diff, attempts, verification evidence, and artifact paths.
- [ ] Separate `observe`, `propose`, `verify`, and `apply` stages.
- [ ] Add modes: `report`, `propose`, `verify`, and `apply`; keep `apply` opt-in.
- [ ] Add maximum changed-line and allowed-path policies.

Acceptance: an unsuccessful run raises the application error and still leaves a complete, machine-readable repair report.

### 2. Verify in isolation

- [ ] Apply candidates in a temporary worktree or disposable directory, never the live source tree first.
- [ ] Compile the candidate and run a configurable test command with a timeout.
- [ ] Re-run the original failing input plus user-supplied regression cases.
- [ ] Reject patches that edit unrelated files, weaken tests, or exceed the retry budget.
- [ ] Promote a verified patch to the real tree only after policy approval.

Acceptance: a candidate cannot reach the working tree unless every configured gate passes.

### 3. Give repairs business contracts and related tests

- [ ] Add a versioned `HealingContract` with purpose, preconditions, postconditions, invariants, side effects, sensitive fields, and forbidden changes.
- [ ] Accept contracts through typed decorator arguments, structured docstring sections, or external JSON/YAML; normalize them to one schema.
- [ ] Support optional `tests`, `test_paths`, and `test_command` inputs per supervised function or component.
- [ ] Use related tests primarily as verification evidence; never let a repair silently delete, weaken, or rewrite them.
- [ ] Send test source to a model only when explicitly enabled, redacted, and within a context-size budget.
- [ ] Make executable assertions and business invariants authoritative over prose descriptions.

Acceptance: a repair can explain which business invariant it preserves and which supplied tests prove it.

### 4. Heal data contracts and schema drift

- [ ] Build the first demonstrator: ingest two differently structured Excel files into one unchanged Pydantic model and generate a verified adapter for the second format.
- [ ] Add Excel-specific evidence: workbook/sheet identity, header candidates, merged cells, formulas versus values, locale-aware dates/numbers, and column similarity.
- [ ] Add PDF-specific evidence: extractor identity/version, page/table/cell coordinates, OCR confidence, reading order, and alternate extraction candidates.
- [ ] Distinguish malformed individual records from an upstream schema/version change.
- [ ] Capture a redacted schema, validation error, source/version metadata, and representative samples at the ingestion boundary.
- [ ] Propose versioned input adapters for renamed fields, changed nesting, safe type conversions, date/unit formats, optional fields, and enum aliases.
- [ ] Never invent required business data; quarantine or escalate records that cannot satisfy the declared contract.
- [ ] Replay historical valid and invalid samples and verify domain invariants before accepting an adapter.
- [ ] Add shadow mode, deterministic sampling, drift metrics, circuit breakers, and rollback before any automatic activation.
- [ ] Generate the adapter, regression fixtures, and an upstream-change report as separate reviewable artifacts.

Acceptance: a changed but business-valid payload can be normalized at the boundary without weakening the domain model or silently corrupting data.

### 5. Build a decision ledger and repair cache

- [ ] Define a failure fingerprint from exception type, normalized stack, function identity, source hash, and relevant inputs.
- [ ] Record proposals, model/provider, latency, token use, tests, confidence, outcome, and rollback.
- [ ] Cache only verified successful repairs; never replace a success with a later failure.
- [ ] Redact secrets and cap serialized values before persistence or model submission.

Acceptance: every autonomous decision can be reconstructed without storing credentials or unrestricted process state.

### 6. Classify before asking an LLM

- [ ] Distinguish application bugs from transient provider, dependency, environment, configuration, and resource failures.
- [ ] Try deterministic recovery first: bounded retry/backoff, fallback provider, dependency check, or explicit escalation.
- [ ] Replace `AUTO_SYSCHANGE` direct package installation with a pinned dependency proposal, allowlist/policy check, isolated install test, and approval gate.
- [ ] Add confidence thresholds: report-only at low confidence, proposed patch at medium confidence, eligible-for-apply only at high confidence with strong verification.

### 7. Modern provider layer and compatibility matrix

- [ ] Replace provider-specific branches with a small adapter protocol and capability metadata.
- [ ] Add OpenAI Responses API support while retaining Chat Completions compatibility.
- [ ] Support structured repair output instead of parsing free-form Markdown.
- [ ] Test representative OpenAI, Azure OpenAI, Anthropic, LiteLLM/OpenRouter, and Ollama models in a scheduled compatibility suite.
- [ ] Publish tested model IDs and dates; treat arbitrary configured IDs as unverified, not unsupported.

The current OpenAI adapter accepts configurable Chat Completions-compatible model IDs. It does not yet use persisted reasoning, tool calling, or the Responses API repair workflow.

### 8. Publish an honest benchmark

- [ ] Create small syntax, runtime, behavioral, dependency, and multi-file bug suites.
- [ ] Include adversarial cases where a patch passes weak tests but is semantically wrong.
- [ ] Report repair rate, false-fix rate, first-pass success, attempts, latency, cost, diff size, and human acceptance.
- [ ] Compare proposal-only, verified repair, and direct model baselines.

## Medium term: 0.4-0.6 — heal LLM applications and agents

Healing an agent is broader than rewriting a Python function. The system must diagnose which layer failed and choose a bounded response.

### LLM and agent failure taxonomy

- **Inference failures:** timeouts, rate limits, unavailable models, refusals, malformed or truncated output, and context-window overflow.
- **Tool failures:** invalid arguments, stale schemas, permission errors, unavailable MCP servers, selector drift, and partial side effects.
- **Control-loop failures:** repeated actions, no-progress loops, exhausted budgets, incorrect delegation, or lost stop conditions.
- **Context failures:** irrelevant history, missing evidence, prompt injection, memory poisoning, stale skills, or contradictory instructions.
- **Application failures:** exceptions, regressions, dependency changes, and incorrect source code.

### Small implementation steps

- [ ] Publish a framework-neutral `FailureEvent` JSON schema for traces, tool calls, model configuration, budgets, and artifacts.
- [ ] Add hooks around agent tools so Healing Agent can capture failures without owning the whole agent loop.
- [ ] Implement safe remediations for inference errors: retry with jitter, model fallback, context reduction, and structured-output repair.
- [ ] Detect repeated tool calls and no-progress loops with explicit turn, cost, and wall-clock budgets.
- [ ] Propose repairs to prompts, tool schemas, skills, configuration, or source code as distinct artifact types.
- [ ] Require stronger gates for durable memory, skill, prompt, and source modifications than for a one-run retry.
- [ ] Add replay: reproduce a failed agent trajectory with mocked or recorded tool outputs before accepting a repair.

### Agent health monitor and sampling

- [ ] Define a framework-neutral health envelope: success criteria, output schema validity, repeated/no-progress actions, error rate, latency, token/cost budgets, permission denials, test evidence, side effects, and cancellation state.
- [ ] Enter Healing Agent synchronously on hard failures or invalid tool/model output, after a bounded no-progress trigger, and asynchronously in post-run evaluation.
- [ ] Support deterministic hash sampling by `run_id`/`trace_id` so sampled runs are reproducible across services.
- [ ] Add separate observation and repair rates, for example `OBSERVATION_SAMPLE_RATE` and `REPAIR_SAMPLE_RATE`; keep hard failures and high-risk actions always observed.
- [ ] Add risk-weighted sampling so novel tools, changed schemas, high-value transactions, and degraded health receive more coverage than routine successful runs.
- [ ] Escalate gradually: observe/report, deterministic retry, fallback, repair proposal, sandbox replay, then human-approved application.

Random sampling is useful for detecting silent quality regressions, but it must
not decide whether explicit failures are captured. Repair sampling should default
to zero until verification and approval policies are configured.

### Agent harness integrations

- [ ] Provide a Python middleware/decorator for agent tool functions.
- [ ] Provide a CLI that accepts a failure bundle and emits a `RepairResult` without importing Healing Agent into the target process.
- [ ] Expose that CLI through an MCP server so Codex, Hermes Agent, OpenHands, and other harnesses can request diagnosis or verification.
- [ ] Build a Hermes Agent proof of concept: ingest a failed tool call or skill run, produce a proposed skill/tool repair, replay it in a sandbox, and return a diff for approval.
- [ ] Add OpenTelemetry and Sentry-style ingestion adapters for production exceptions and agent traces.
- [ ] Add an optional GitHub App/Action that turns a verified incident repair into an issue or draft pull request.
- [ ] Use fine-grained permissions, dry-run mode, evidence attachments, and branch/path allowlists; never push to the default branch, merge, or close issues autonomously.

For self-improving systems such as [Hermes Agent](https://github.com/NousResearch/hermes-agent) and [Browser Harness](https://github.com/browser-use/browser-harness), Healing Agent should be an external immune system rather than editable agent memory. The harness may learn skills; Healing Agent independently enforces budgets, provenance, verification, rollback, and approval boundaries.

## Long term: 1.0 — language-neutral repair infrastructure

Do not port the Python decorator and AST replacement code wholesale. Split the system into a language-neutral coordinator and language-specific adapters.

- [ ] Define a versioned protocol for failure events, source locations, candidate patches, verification commands, and results.
- [ ] Extract the coordinator, policy engine, ledger, cache, and model adapters from Python-specific capture and patching.
- [ ] Build a TypeScript/Node adapter next: uncaught exceptions, source maps, TypeScript compiler, Vitest/Jest, and ESLint verification.
- [ ] Build a Go adapter: panic/error capture, `gofmt`, `go vet`, and `go test`.
- [ ] Evaluate Java and Rust only after the protocol survives two independent adapters.
- [ ] Use native parsers or language servers for edits; reserve text replacement as a guarded fallback.
- [ ] Support repository-level and multi-service fault localization with trace-to-source mapping.

Acceptance: the coordinator can repair the same benchmark failure through two language adapters without language-specific branches in its policy or ledger.

## Long shots

- [ ] Calibrated repair confidence learned from verified outcomes rather than model self-rating.
- [ ] Counterfactual replay that compares several candidate fixes against recorded production traffic with secrets removed.
- [ ] Canary repairs with automatic rollback when health or semantic metrics regress.
- [ ] Privacy-preserving repair signatures that share successful failure patterns without sharing source code.
- [ ] An agent immune system that monitors multiple specialized agents, identifies the faulty layer, quarantines unsafe skills or tools, and proposes the smallest reversible intervention.
- [ ] Continual improvement of repair strategies while keeping the trusted verifier and policy core immutable.

## Guardrails and non-goals

- Never treat “the exception disappeared” as proof of correctness.
- Never silently return `None` or fabricate success after a failed repair.
- Never let the component being repaired be the only verifier of its own repair.
- Never modify production, durable memory, skills, prompts, dependencies, or credentials without an explicit policy allowing it.
- Never send unrestricted locals, globals, source, or tool output to a remote model; minimize and redact first.
- Prefer a small rejected repair over a broad plausible patch.

## Success measures

- Original-error preservation rate: 100% when healing fails.
- Budget enforcement rate: 100% across recursion, reloads, tools, and agent turns.
- Verified repair rate and false-fix rate on published, reproducible suites.
- Median attempts, latency, model cost, and diff size per accepted repair.
- Rollback success and post-repair regression rate.
- Human acceptance rate for generated patches and draft pull requests.
