# Healing Agent roadmap

Healing Agent is a repair layer for programs and agents: observe a failure,
preserve evidence, propose the smallest repair, verify it, and return a
reviewable result.

**Working principle (KISS):** the repo stays thin, transparent, and minimal.
Intelligence lives in the model and the prompts; trust lives in acceptance
tests and verification. New logic is added only when a failing test proves that
prompts and context cannot solve a scenario class. Automatic application
remains the compatibility default; proposal-only and approval policies are
configurable alternatives.

## Flagship: Data Healing — demonstrated ✅

The recurring failure class where the code is fine but the input drifted
(renamed/reordered columns, reshaped API payloads, changed date formats) is
handled by the existing heal-the-function loop plus drift-aware prompts, and
proven by live acceptance tests: the healed source must return the identical
business result for the old **and** the new format, and unmappable input must
raise instead of fabricating data. See [docs/data-healing.md](docs/data-healing.md)
for the approach, the adversarial guardrail story, and the escalation rule
(prompt → context → code).

Next steps (each one scenario + at most a prompt/context change):

- [x] Excel workbook drift: renamed sheet + title rows above the header + translated headers (needs a higher `MAX_ATTEMPTS`: opaque path inputs are discovered round by round).
- [x] Mixed valid/invalid records: header drift healed while quarantine semantics are preserved.
- [x] Encoding and locale drift: UTF-8 BOM on the first header + Hungarian decimal/thousands format (passed with zero prompt changes).
- [x] Paginated / enveloped API shape changes: flat list → per-page envelopes, aggregated across pages (passed with zero prompt changes).
- [ ] Merged cells in Excel — deferred deliberately: forward-filling merged group labels is a semantic assumption that borders on the never-invent-data guardrail; needs a design decision first.
- [ ] Formula-vs-value drift in Excel — deferred: openpyxl-generated fixtures carry no cached values (`data_only=True` yields `None`), so the real-world case cannot be reproduced without committing binary Excel-saved fixtures.
- [ ] Related-function context in the fix prompt — only if a scenario empirically fails without it.

## Released

- **0.2.7 safety baseline** — bounded healing (`MAX_ATTEMPTS`), original
  exception always re-raised on failure, module restore on failed reload,
  pytest-based suite, Python 3.10–3.13 CI.
- **0.2.8 reviewable patch bridge** — minimal candidate replacement without
  reformatting unrelated code, optional `git apply`-consumable patches with
  JSON provenance sidecars, language-neutral text patch support.
- **0.2.9 guarded Git workflow + Data Healing spec** — `GIT_MODE=off|patch|apply`
  with `git apply --check` and source-hash guards; the dependency-free Data
  Healing design.
- **0.3.0 Data Healing demonstrated** — 11 live acceptance scenarios (9 heal +
  2 anti-fabrication guardrails) across CSV, Excel, API, date/locale and
  pagination drift; drift-aware prompts; decorator-preserving replacement;
  bounded generation retry.

## Short term: 0.4 — repairs that can be trusted

1. **Function-documented validation tests** — let the application declare
   which of its own tests validate a supervised function (e.g.
   `@healing_agent(test_command="pytest tests/test_loader.py")` or
   `tests=[...]`); after a heal, run them automatically and reject the fix on
   failure. This is the KISS-compatible verification step: the tests already
   exist in the host application, Healing Agent only runs them.
   *Acceptance: a heal that breaks a declared validation test never reaches
   the source tree.*
2. **Host-level GitHub flow so fixes are never lost** — turn the already-saved
   patch + provenance sidecar into a branch, commit, and draft pull request
   via an explicit host-level script/Action (token stays host-supplied,
   never in the healed process or LLM context; never pushes to the default
   branch). This moves verified heals toward production instead of leaving
   them in `_healing_agent_fixes/`.
3. **Proposal-only as a first-class API** — a `RepairResult` (status, error,
   proposal, diff, attempts, evidence, artifact paths); `report`/`propose`/
   `verify`/`apply` modes with `apply` as compatibility default; changed-line
   and allowed-path policies. *Acceptance: a failed run raises the original
   error and still leaves a machine-readable repair report.*
4. **Verify in isolation** — apply candidates in a temp worktree, compile and
   run a configured test command with timeout, replay the failing input plus
   regression cases, reject out-of-scope edits. *Acceptance: no candidate
   reaches the working tree unless every configured gate passes.*
5. **Business contracts** — optional per-function contracts (invariants,
   forbidden changes, related tests); executable assertions are authoritative
   over prose. Repairs may never delete or weaken supplied tests.
6. **Classify before asking an LLM** — separate application bugs from
   transient provider/dependency/environment failures; deterministic recovery
   (retry/backoff/fallback) first; replace direct `AUTO_SYSCHANGE` installs
   with a reviewable, policy-gated dependency proposal.
7. **Modern provider layer** — small adapter protocol, structured repair
   output instead of Markdown parsing, scheduled compatibility matrix with
   published tested model IDs.
8. **Honest benchmark** — small bug suites including adversarial cases where a
   patch passes weak tests but is semantically wrong; report repair rate,
   false-fix rate, attempts, latency, cost, and diff size.

## Medium term: 0.5–0.7 — heal LLM applications and agents

Failure taxonomy: inference (timeouts, refusals, malformed output), tools
(invalid arguments, schema drift, unavailable servers), control loop (repeated
actions, no progress, blown budgets), context (injection, poisoning, stale
skills), and application failures.

- [ ] Framework-neutral `FailureEvent` schema and hooks around agent tools.
- [ ] Safe inference remediations: retry with jitter, model fallback, context
      reduction, structured-output repair.
- [ ] Loop/no-progress detection with turn, cost, and wall-clock budgets.
- [ ] Distinct artifact types for prompt/tool-schema/skill/config/code repairs,
      with stronger gates for durable changes than for one-run retries.
- [ ] Replay a failed agent trajectory with recorded tool outputs before
      accepting a repair.
- [ ] Health envelope + deterministic sampling (`OBSERVATION_SAMPLE_RATE`,
      `REPAIR_SAMPLE_RATE`); hard failures are always observed; repair sampling
      defaults to zero until verification policies are configured.
- [ ] Harness integrations: tool-decorator middleware, a CLI that turns a
      failure bundle into a `RepairResult`, an MCP server exposing it, and
      OpenTelemetry/Sentry ingestion.
- [ ] Optional GitHub App/Action: verified incident → draft PR on an isolated
      branch with least-privilege, host-supplied tokens; never push to the
      default branch or merge autonomously.

Healing Agent should be an external immune system for self-improving harnesses
(e.g. Hermes Agent): the harness may learn skills; Healing Agent independently
enforces budgets, provenance, verification, rollback, and approval boundaries.

## Long term: 1.0 — language-neutral repair infrastructure

Split into a language-neutral coordinator (policy, ledger, cache, model
adapters) and language adapters (capture + patching). TypeScript/Node next
(source maps, tsc, Vitest/Jest), then Go (`go vet`, `go test`); Java/Rust only
after the protocol survives two independent adapters. *Acceptance: the
coordinator repairs the same benchmark failure through two language adapters
without language-specific branches in policy or ledger.*

## Long shots

Calibrated repair confidence from verified outcomes; counterfactual replay
against recorded traffic; canary repairs with automatic rollback;
privacy-preserving repair signatures; an agent immune system that quarantines
unsafe skills/tools and proposes the smallest reversible intervention.

## Guardrails and non-goals

- Never treat "the exception disappeared" as proof of correctness.
- Never silently return `None` or fabricate success after a failed repair.
- Never invent missing required business data; unmappable input raises clearly.
- Never let the repaired component be the only verifier of its own repair.
- Never modify production, durable memory, skills, prompts, dependencies, or
  credentials without an explicit policy allowing it.
- Never send unrestricted locals, globals, source, or tool output to a remote
  model; minimize and redact first.
- Prefer a small rejected repair over a broad plausible patch.

## Success measures

- Original-error preservation rate: 100% when healing fails.
- Budget enforcement rate: 100% across recursion, reloads, tools, agent turns.
- Verified repair rate and false-fix rate on reproducible suites.
- Old-format compatibility rate after data healing: 100%.
- Median attempts, latency, cost, and diff size per accepted repair.
- Human acceptance rate for generated patches and draft pull requests.
