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

## Short term: repairs that can be trusted

*Milestone names and version numbers are deliberately separate. A version
number follows from what a release contains (SemVer), and this milestone spans
several minor releases — the first slice, GitHub issue escalation, ships in
0.4.0.*

The unifying design is the **observe → propose → verify → apply pipeline** —
context capture with or without a failure, pluggable fix generation, ordered
verification gates before any mutation, a single APPLY policy switch for where
accepted candidates land, and automatic restore on definitive failure. See the
full specification in
[docs/apply-verify-design.md](docs/apply-verify-design.md).

1. **VERIFY chain before apply** — move the behavioral check (re-run with
   original arguments) to an isolated copy BEFORE the live file is touched;
   gates are ordered and all must pass: `syntax` → `rerun` → optional
   `command` gate(s) → `pr-checks`.
   *Acceptance: no candidate reaches the working tree unless every configured
   gate passes.*
   Verification-before-mutation also unlocks candidate *selection*: once
   nothing is written until the gates pass, generating a few candidates and
   letting the gates choose costs only model calls. This is how
   [Agentless](https://github.com/OpenAutoCoder/Agentless) reached its
   results — sample, then filter by execution, instead of steering a single
   attempt through an agent loop. Worth adding only when the benchmark
   (item 13) can show it beats one candidate plus one retry, per unit cost.
2. **One unified `command` verify gate** — any command run inside the
   isolated candidate workspace, pass = exit 0: the app's own pytest
   (`@healing_agent(VERIFY_COMMAND="pytest tests/test_loader.py")`, also
   settable in config), an external sandbox/hidden-test engine, a linter.
   No separate "tests" gate: a test run IS a command. *Acceptance: a heal
   that fails the declared verify command never reaches the source tree.*
3. **PR flow with repository CI as the zero-config gate** (`pr-checks` +
   `APPLY="pr"`) — branch → commit patch → push → draft PR built from the
   redacted provenance sidecar; optionally wait for the repository's OWN CI
   on the PR, continue locally with the candidate on green, and let GitHub
   native auto-merge (branch protection + required checks) land it. On red,
   the PR stays open for humans and the original error propagates — never
   continue silently. No per-function test declarations needed: the existing
   CI suite is the verification. Token stays host-level; never push to the
   default branch. *Acceptance: a scheduled job broken by drift at night has
   a CI-verified, merged fix and a successful re-run by morning, with zero
   bespoke test configuration.*
4. **Definitive-failure sequence** — what happens once healing gives up
   (`MAX_ATTEMPTS` exhausted, repaired module still failing, gate rejection,
   or `AUTO_FIX=False`):
   - [x] **Restore the source** (`RESTORE_ON_FAILURE`, default on): the
         session's first backup — the pre-healing original — is copied back,
         so no half-healed file is left behind; candidates stay in
         `_healing_agent_fixes/`. *Acceptance: after any failed healing
         session the source file is byte-identical to its pre-healing state.*
   - [x] **Escalate as plan B** (`GITHUB["issue_on_failure"]`): open a GitHub
         issue at the configured detail level so the failed attempt is not
         lost — an external agent or a human answers with a PR that flows
         through `pr-checks`. Same mechanism as the `issue` PROPOSE backend,
         but triggered after local healing gave up rather than instead of it.
   - [x] **Re-raise the original exception**, always — a failed repair never
         becomes an implicit `None`, and an opened issue is never a fix.
5. **One subprocess boundary for everything external** — fix generation
   (`PROPOSE` via external bot/harness returning `fixed_code`), verification
   (`command` gate), external apply (`APPLY="command"`, the community
   mutation-backend hook), and the PR delivery itself all speak the same
   versioned JSON protocol; `GIT_MODE` and `MUTATION_BACKEND` are absorbed as
   branches of the APPLY switch with backwards-compatible aliases. External
   engines (e.g. Aether) earn "verified backend" status by passing the live
   data-drift acceptance suite through the hook.
6. **OBSERVE: capture without a failure**
   - [x] `healing_agent.capture(label=...)` writes a redacted snapshot of the
         calling frame at any point — no AI call, no mutation. It reuses the
         `error=None` path that `capture_context` always supported but nothing
         exposed.
   - [x] Optional ring buffer of the application's own log records
         (`LOG_BUFFER_SIZE`, 0/absent = never installed), armed with
         `healing_agent.enable_log_capture()` and included in both the fix and
         hint prompts. The stack says where it broke, the log says what it was
         doing.
   - [ ] `CAPTURE_SINK`: send snapshots somewhere other than the local
         directory (a command, object storage, a GitHub issue).
   - [ ] A `probe` that exercises a configured call and stores its context, so
         integration drift is visible BEFORE a loader raises — see the tools
         item below: a probe is most useful as a tool the model can invoke.
7. **Give the model tools instead of a bigger prompt** — captured evidence is
   currently all-or-nothing: whatever the prompt includes is sent every time,
   and whatever it omits is invisible. Today the `variables` block (locals and
   globals, ~2.5 KB of a ~8 KB context) is captured and saved but **never
   sent** — a deliberate cost decision that also means the model is blind to
   runtime state, which matters most for data drift. Tool calls invert this:
   the model asks only for what it needs.
   - [ ] `get_variables(pattern)` — fetch or search the captured locals and
         globals on demand instead of shipping them all.
   - [ ] `search_logs(pattern)` — query the ring buffer rather than pasting
         every record into the prompt.
   - [ ] `probe(request)` — perform a bounded, allowlisted network or CLI check
         (a `curl`-style request against the drifted endpoint) so the model can
         confirm what the source returns *today* rather than inferring it.
   - [ ] `open_issue(...)` — escalate deliberately, reusing the shipped
         escalation module.
   Requires the structured/tool-calling provider layer (item 12). Every tool
   that touches the system or creates outward-facing artifacts needs real
   tests first: the existing `agent_tools/` are experimental and untested.
8. **Logging interoperability** — emit through
   `logging.getLogger("healing_agent")` so hosts route healing output with
   stdlib logging (loguru/structlog interoperate through their documented
   stdlib bridges); printing remains the fallback when no handler is
   configured, so current behavior is preserved. (The inward half — the ring
   buffer — shipped with item 6.)
9. **Proposal-only as a first-class API** — a `RepairResult` (status, error,
   proposal, diff, attempts, evidence, artifact paths); `report`/`propose`/
   `verify`/`apply` modes with `apply` as compatibility default; changed-line
   and allowed-path policies. *Acceptance: a failed run raises the original
   error and still leaves a machine-readable repair report.* Includes
   `APPLY="ask"`: show the diff, apply only on explicit confirmation, refuse
   rather than assume consent when there is no TTY. (Wolverine's unmerged
   PRs [#23](https://github.com/biobootloader/wolverine/pull/23) and
   [#21](https://github.com/biobootloader/wolverine/pull/21) both added this
   independently in 2023 — it is what people reach for first when a healer
   surprises them.)
10. **Business contracts** — optional per-function contracts (invariants,
   forbidden changes, related tests); executable assertions are authoritative
   over prose. Repairs may never delete or weaken supplied tests. When a
   `command` gate fails, the two possible readings — "the candidate is wrong"
   and "the test encodes behavior that legitimately changed" — must be kept
   apart, and only a human may resolve the second one; the repair itself
   never edits the test that judges it. ([ghost](https://github.com/tripathiji1312/ghost)
   arrived at the same rule from the opposite direction: it generates tests
   and refuses to "heal" an assertion when the source looks buggy.)
11. **Classify before asking an LLM** — separate application bugs from
   transient provider/dependency/environment failures; deterministic recovery
   (retry/backoff/fallback) first; replace direct `AUTO_SYSCHANGE` installs
   with a reviewable, policy-gated dependency proposal. Field evidence for
   why this comes first: in a small public CI healer
   ([shazilhamzah/self-healing-pipeline](https://github.com/shazilhamzah/self-healing-pipeline/issues))
   every escalated failure was a misspelled dependency, a missing test
   directory, or the healer being blocked from editing a test file — not one
   was an application code bug an LLM should have been asked about.
12. **Modern provider layer** — small adapter protocol, structured repair
   output instead of Markdown parsing, scheduled compatibility matrix with
   published tested model IDs. Includes `healing-agent doctor`: check that a
   config file was found and from where, that the selected provider's
   environment variables are present (never printing their values), that the
   configured model ID answers a one-token request, and that the artifact
   directories are writable. "No provider configured" is the failure every
   user meets first, and today it is discovered in the middle of an actual
   incident. ([ghost](https://github.com/tripathiji1312/ghost) ships the same
   command for the same reason.)
13. **Honest benchmark** — small bug suites including adversarial cases where a
   patch passes weak tests but is semantically wrong; report repair rate,
   false-fix rate, attempts, latency, cost, and diff size. Publish the
   data-drift suite and its numbers as a short citable write-up: the LLM4APR
   literature (e.g. [AwesomeLLM4APR](https://github.com/iSEngLab/AwesomeLLM4APR),
   TOSEM 2026) indexes papers rather than repositories, so a preprint is the
   only route into the surveys — and the drift scenarios are a repair class
   the existing benchmarks (Defects4J, SWE-bench) do not cover at all.
   Designed in [docs/benchmark.md](docs/benchmark.md) — dataset layout,
   outcome taxonomy (`healed` / `false-fix` / `refused` / `fabricated` /
   `unhealed`), the model × params × prompt matrix, and the four small
   library changes that block it (provider selectable per run, sampling
   parameters passed through to every provider, token usage captured,
   prompts addressable as named variants). Concretely, in dependency order:
   - **A named benchmark, not a test suite.** `tests/test_data_drift.py`
     proves the scenarios pass; a benchmark must let a stranger reproduce
     the numbers. Split the fixtures and expected business results into a
     declarative dataset (one directory per scenario: original input, drifted
     input, the loader under repair, the expected result for BOTH formats)
     plus a runner that reports repair rate, false-fix rate, attempts,
     latency, cost and diff size per model.
   - **Report failures, including the ones we did not solve.** Merged Excel
     cells and formula-vs-value drift are already documented as deferred;
     a benchmark that only contains passing scenarios is marketing. The
     anti-fabrication guardrails are the most interesting rows precisely
     because the correct behavior is to REFUSE.
   - **Multiple models, published matrix.** A single-model result is an
     anecdote. The provider layer (item 12) is what makes the matrix cheap.
   - **Then the write-up**: the claim is not "an LLM can fix bugs" — it is
     that a small decorator plus drift-aware prompts plus
     verification-before-mutation repairs a failure class the APR benchmarks
     omit (input drift, where the code is correct until the world changes),
     and that backward compatibility with the old format is the acceptance
     criterion that keeps it honest. arXiv `cs.SE` needs an endorsement for
     a first-time submitter; the alternative venues that do not are a
     workshop paper or a tool/demo track.
14. **Incident memory** — the `_healing_agent_exceptions/` and
   `_healing_agent_fixes/` directories are write-only today: every session
   starts from zero even when the identical failure was healed last night.
   Index the artifacts by the same failure fingerprint the issue
   deduplication uses, and feed the most similar RESOLVED case — the error,
   the accepted candidate, and which gate passed it — into the hint and fix
   prompts. No new dependency and no embedding store: a JSON index next to
   the artifacts, matched on fingerprint and normalized error text. Recurring
   failure classes are exactly what this library is for, so the memory
   compounds where it matters. *Acceptance: a repeat of an already-healed
   failure class is repaired in fewer attempts than its first occurrence,
   measured on the data-drift suite.*
15. **Interoperate with issue→PR agents** — [OpenHands](https://github.com/All-Hands-AI/OpenHands),
   [SWE-agent](https://github.com/SWE-agent/SWE-agent),
   [auto-code-rover](https://github.com/nus-apr/auto-code-rover) and GitHub's
   Copilot coding agent all start from a GitHub issue and end at a pull
   request — and none of them can observe a runtime failure. Healing Agent
   starts exactly where they cannot: at the exception, with the arguments and
   locals in hand. The two halves compose the moment the `issue` PROPOSE
   backend and the `pr-checks` gate exist, so the escalation issue is
   designed as *agent input*, not as a human notice: redacted context JSON,
   traceback frames, the candidate that was tried, and the gate verdict that
   rejected it. The same engines also plug in **synchronously** as
   `PROPOSE = "command"` backends — each has a headless entry point taking a
   problem statement plus a repository and returning a patch, which is
   already the subprocess contract; the adapter is a user-supplied script, so
   upstream flag changes never reach this repository. Concrete invocations
   and the honest cost caveat are in
   [docs/apply-verify-design.md](docs/apply-verify-design.md).
   *Acceptance: an issue opened by healing-agent contains everything an
   issue→PR agent needs to produce a patch without reproducing the failure
   itself.*

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
- [ ] Issue escalation as async PROPOSE: on failure, automatically open a
      GitHub issue with explicit detail-level policy (reference-only default /
      redacted context / AI-anonymized), so an external agent or human answers
      with a PR that flows through `pr-checks`; config groundwork (GITHUB
      block, token via env-var name only) ships earlier.
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

- [ ] **`healing-agent run script.py` — heal from the outside.** A subprocess
      runner that executes a whole program and treats its stderr as the
      failure signal, instead of requiring a decorator inside the source.
      This is what Wolverine did, it is the only mode available for code that
      cannot be imported or decorated (vendor scripts, notebooks exported to
      `.py`, scheduled one-offs), and it is the natural entry point for other
      languages, since the patch layer is already language-neutral. It buys
      breadth at the cost of evidence: no live arguments or locals, only the
      traceback — so the decorator stays the recommended mode, and this is
      the fallback, not the replacement. It also forces a patch
      representation below function granularity: Wolverine used line-numbered
      JSON edit operations applied in reverse order, which is fragile exactly
      because the model has to count lines — the existing unified-diff patch
      layer (`save_text_patch`) is the better carrier, with
      `git apply --check` as a free structural gate.
- [ ] Cross-language validation of the loop before adapters exist: the
      [Go self-healing pipeline](https://github.com/ammarlodhi255/Self-healing-LLM-Pipeline)
      shows the same compile → test → feed-the-error-back cycle outside
      Python and confirms nothing in it is Python-specific; what it lacks —
      an attempt budget, a restore path, and any check that the code is
      *right* rather than merely compiling — is the part worth keeping ours.

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
- Never let a repair edit, delete, or relax the tests and assertions that
  judge it.
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
