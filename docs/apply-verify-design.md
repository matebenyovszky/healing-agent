# Propose, Verify & Apply design (0.4 target)

The 0.3 heal loop verifies AFTER mutating the live file: the only behavioral
check (re-running with the original arguments) happens once the source is
already rewritten. 0.4 inverts this and makes the whole pipeline explicit
policy — three swappable stages behind one external boundary:

```text
OBSERVE    (capture context — on an exception OR at an explicit point)
        → PROPOSE  (who writes the fix)
        → VERIFY   (ordered gates, all must pass — BEFORE the live file changes)
        → APPLY    (where the accepted candidate lands)
        → on definitive failure: RESTORE the pre-healing source from backup,
          optionally escalate, re-raise the original exception
```

The guiding principle stays KISS: healing-agent builds no repair, test, or
sandbox infrastructure of its own. It orchestrates things that already exist —
the AI provider, the Python compiler, the application's own tests, the
repository's own CI, the application's own logger — and exposes ONE
subprocess/JSON boundary for everything external.

## OBSERVE — capture without a failure

`capture_context()` already accepts `error=None` and tags the result
`capture_type: "debug"`, but nothing exposes it. Observation deserves to be a
first-class stage, because the same evidence that powers a repair is valuable
on its own: knowing every variable at the moment an API call returned
something unexpected is often the whole debugging session.

| Mode | Behavior |
|---|---|
| `off` (default) | context is captured only when an exception occurs |
| `capture` | `healing_agent.capture(label="after-fetch")` writes a redacted context snapshot at any point in the code; no AI call, no mutation |
| `probe` | run a configured call (e.g. the API request described in config) and save its context — a self-test that answers "what does this integration actually return today?" |

Where snapshots go is the same one-boundary decision as everywhere else
(`CAPTURE_SINK`): the local `_healing_agent_exceptions/` directory by default,
a command for anything else (ship to object storage, a log pipeline, a
ticket), or `issue` to attach it to a GitHub issue. Redaction runs before any
sink, exactly as it does for failures.

Observation also makes the drift story proactive rather than reactive: a
`probe` snapshot taken nightly against a supplier's API shows the structure
changing *before* a loader raises.

## Logging — connect to the application's own logger

healing-agent prints today. Two connections are worth having, and both use
Python's standard `logging`, so no third-party logger becomes a dependency:

- **Outward:** emit through `logging.getLogger("healing_agent")` so the host
  application decides where healing output goes. Standard-library `logging`
  is the interoperability point everyone already has: loguru users install
  their documented `InterceptHandler`, structlog wraps stdlib, and plain
  `logging.basicConfig()` just works. Printing stays the fallback when the
  application configured no handler, so current behavior is preserved.
- **Inward (the more valuable direction):** attach a small ring-buffer
  `logging.Handler` that keeps the last N records, and include them in the
  captured context. The stack trace says where the program broke; the recent
  log lines say what it was doing. That narrative is exactly what a repair
  proposal — and a human reading an escalated issue — is missing today.
  Opt-in, size-capped, and redacted through the same chokepoint, because log
  messages are free text that can carry sensitive values.

## PROPOSE — who writes the fix

| Backend | Behavior |
|---|---|
| `provider` (default) | today's built-in flow: the configured AI provider generates the candidate from the redacted context |
| `command` | the redacted context JSON goes to an external bot/harness over the subprocess protocol; it answers with the unified envelope carrying the candidate |
| `issue` | **async escalation**: open a GitHub issue about the failure and stop (the original error propagates). Whoever watches the repo's issues — a human, or an agent like a coding-assistant GitHub app — delivers the fix as a PR, which flows through the normal `pr-checks` / auto-merge path. The current run does not heal; the NEXT run does. |

The command form lets an organization plug in its own repair harness
(a stronger agent, a fine-tuned model, a rule engine) without healing-agent
learning anything about it. Its response uses the unified envelope (below)
with a required `candidate`; inline code is the v1 contract, path and branch
are planned extensions.

### Issue content privacy levels

Exception context and captured variables can carry sensitive data, so the
issue body's detail level is explicit policy (`GITHUB["issue_detail"]`):

| Level | Issue contains | Residual risk |
|---|---|---|
| `reference` (default) | error type + message, function name, repository-relative file/line, and pointers to the LOCAL `_healing_agent_exceptions/` / `_healing_agent_fixes/` artifacts | lowest: no captured values are uploaded — but note the exception MESSAGE itself is included, and a message like `KeyError: 'customer_tax_id'` is already a disclosure |
| `redacted` | additionally attaches the name-based redacted context JSON | sensitive VALUES under innocently-named variables can still slip through — documented, opt-in |
| `ai-anonymized` | additionally attaches a context JSON where an extra AI pass replaced values with placeholders | costs a model call; anonymization quality is probabilistic — opt-in |

The choice is the operator's: whoever supplies the repository and the token
decides how much detail is appropriate. On an internal repository the richer
levels are a gift rather than a risk, which is why all three exist instead of
one cautious default.

Authentication follows the standing guardrail: the config stores only the
NAME of the environment variable holding the token
(`GITHUB["token_env"] = "GITHUB_TOKEN"`) or relies on `gh` CLI auth — the
token value itself never appears in `healing_agent_config.py`, which is
exactly the file class that must stay secret-free.

### Deduplication — one issue per distinct failure

A scheduled job failing every minute must not open 1440 issues a day. Each
issue carries an invisible fingerprint marker in its body
(`<!-- healing-agent-fingerprint: … -->`), built from:

- the exception type;
- the function's qualified name;
- the repository-relative file path (never the absolute path, so local
  usernames are not disclosed);
- the failing source line's TEXT, not its line number — line numbers shift on
  every edit and would fragment one failure into many issues;
- the exception message with **digits normalized** (`row 5 failed` and
  `row 812 failed` collapse into one issue) while quoted identifiers are
  preserved (`KeyError: 'amount'` stays distinct from `KeyError: 'osszeg'`,
  because two different drifted columns are two different problems).

Before opening, healing-agent lists the repository's OPEN issues carrying the
`healing-agent` label and matches the fingerprint. The search API is
deliberately avoided: its indexing lag would let duplicates through exactly in
the rapid-repeat case that matters most.

Decisions kept deliberately simple:

- **Duplicate found → skip**, logging the existing issue URL. Every occurrence
  is already recorded in the local artifacts, so nothing is lost, and the
  issue thread stays readable.
- **Closed issue + recurrence → new issue.** A failure that returns after
  being fixed is a regression and deserves its own ticket; the closed issue
  keeps the earlier history.
- **No local dedup cache.** The one API call costs nothing next to the model
  calls already being made, and a cache would only add a file that can
  disagree with reality after someone closes an issue by hand.

### Also available as an agent tool

The same issue opener is exposed as an agent tool, so escalation can be a
deliberate act rather than only an automatic consequence: an agent that
concludes a failure is not safely repairable can file the report itself. The
existing `agent_tools/` are experimental and untested; tools that can create
outward-facing artifacts need real tests before they are trusted.

## VERIFY — ordered gates, all must pass

| Gate | What it does | Cost | Config needed |
|---|---|---|---|
| `syntax` | `compile()` + single-function AST check | ms | none (always on) |
| `rerun` | execute the candidate with the original arguments on an ISOLATED copy (temp import), never the live file | ms–s | none (default on) |
| `command` | run ANY command inside the isolated workspace where the candidate is already applied; **exit code 0 = pass**. `pytest tests/test_loader.py` needs no protocol at all; protocol-aware engines (e.g. Aether in check mode) can read the candidate-context JSON from the `HEALING_AGENT_CANDIDATE` env var, and MAY print a JSON object to stdout (`{"ok": false, "error": "hidden test failed"}`) which is logged as structured detail — but the exit code alone decides. Configurable globally (`VERIFY_COMMAND`) or per function (`@healing_agent(VERIFY_COMMAND="pytest tests/test_loader.py")` — the decorator's existing local-config merge already carries it). | s | one command line |
| `pr-checks` | open a PR from the candidate and treat the repository's OWN CI as the gate | minutes | **none** — the CI already exists |

There is deliberately no separate "tests" gate: an application test run IS a
command. One gate type covers pytest, hidden-test engines, linters, or
anything else that can express pass/fail as an exit code.

`pr-checks` is the zero-config profile: no per-function declarations — the
whole existing suite validates the repair, using infrastructure the team
already trusts. Gates compose cheapest-first: syntax and rerun filter garbage
so the expensive CI gate (and human reviewers) never see it.

## APPLY — where an accepted candidate lands

| Policy | Behavior |
|---|---|
| `report` | artifacts only; the original exception propagates |
| `patch` | reviewable diff + provenance sidecar (today's `GIT_MODE="patch"`) |
| `direct` | backup → write → reload → continue (classic behavior, default) |
| `command` | delegate apply to an external tool over the same subprocess protocol (validate/sandbox/apply/rollback externally — this is the community mutation-backend hook) |
| `pr` | branch → commit the patch → push → pull request |
| `direct+pr` | heal locally NOW **and** open the PR for durability |

`GIT_MODE` and `MUTATION_BACKEND` are absorbed as branches of this one switch
(backwards-compatible aliases retained).

**Terminology bridge:** what the mutation-backend hook calls "mutation" is
this APPLY stage with verification bundled inside the external tool. In this
design the same external engine can serve either role separately: check-only
as a `command` VERIFY gate, or full pipeline as `APPLY="command"`.

**Recommended integration is verify-only.** Once the verify gates passed,
the write itself is trivial and healing-agent's own backup + restore-on-fail
already covers rollback — so delegating APPLY only pays off for engines with
genuinely transactional apply semantics (snapshots, multi-file atomicity).
Verify-only also removes the trust problem entirely: healing-agent performs
the write itself, so no external "ok" has to be believed.

## What happens on definitive failure — implemented ✅ (restore) + planned

Healing ends definitively when `MAX_ATTEMPTS` is exhausted, the repaired
module still fails, a gate rejects the candidate, or `AUTO_FIX=False`. The
sequence is:

1. **RESTORE the sources** (`RESTORE_ON_FAILURE=True`, default) — the FIRST
   backup of the healing session holds the pre-healing original; it is copied
   back, so the working tree is exactly as it was. Attempts nest (a repaired
   function that fails again re-enters the decorator), so only the outermost
   invocation owns the session and restores. The generated candidates stay
   available under `_healing_agent_fixes/`; `False` keeps the mutated file for
   inspection instead.
   *Acceptance: after any failed healing session, the source file is
   byte-identical to its pre-healing state.* — **shipped in 0.4 groundwork**
2. **Escalate as plan B** (`GITHUB["issue_on_failure"]`, planned) — open a
   GitHub issue describing the failure at the configured detail level, so the
   attempt is not silently lost: an external agent or a human can answer with
   a PR that flows through the normal `pr-checks` path. This is the same
   escalation as the `issue` PROPOSE backend, only triggered AFTER local
   healing gave up rather than instead of it.
3. **Re-raise the original application exception** — always, unchanged. A
   failed repair never becomes an implicit `None`, and an opened issue is
   never treated as a fix.

## The PR flow in detail (standard Git machinery only)

```text
candidate passes local gates
  → branch from current HEAD → commit patch (provenance sidecar in PR body)
  → push → open PR (draft by default)
  → [optional] wait for checks (PR_WAIT_FOR_CHECKS=True)
       green → continue locally with the candidate (the process already
               holds it: write + reload — no need to wait for merge
               mechanics) and let GitHub native auto-merge land it
       red   → PR stays open for humans; RESTORE runs if the live file was
               touched; the original error propagates;
               NEVER continue silently on red
```

- **Scheduled pipelines / batch jobs** are the sweet spot: drift breaks the
  02:00 ETL → fix generated and verified locally → PR at 02:03 → full CI
  green at 02:08 → auto-merge → the job re-runs healed. Nothing is lost,
  everything is audited.
- **Live processes** should use `direct+pr`: heal now after local gates,
  let CI + humans confirm asynchronously, next deploy carries the durable fix.

Guardrails:

- auto-merge only via GitHub native auto-merge with branch protection and
  required status checks; default is a draft PR with no auto-merge;
- never push to the default branch directly;
- the token is host-level (`gh` auth / environment), never enters the model
  context or the healed process config;
- PR bodies are built from the redacted provenance sidecar.

## One external boundary: the subprocess protocol

Fix generation (`PROPOSE command`), verification (`VERIFY command`), external
apply (`APPLY="command"`), and the PR delivery itself are all commands
speaking the same versioned JSON-over-stdin protocol family
(`healing-agent-mutation-v1`, introduced by the community mutation-backend
hook). The first-party PR backend is simply a `gh`-based script on that
boundary — the first of hopefully many backends. The subprocess boundary is
also a dependency and license boundary: external engines stay external.

### Unified response envelope (every stage, one parser)

```json
{"ok": true,
 "error": "only when not ok",
 "candidate": {"code": "..."} | {"path": "..."} | {"branch": "..."}}
```

- **PROPOSE**: `ok` + `candidate` required — the candidate IS the answer.
- **VERIFY**: the exit code alone decides pass/fail; the envelope is optional
  structured detail. A verifier MAY return a `candidate` meaning "passed,
  but in this canonicalized form" (e.g. an AST engine re-serializing the
  patch). Guardrail: a gate that returns a NEW candidate restarts the chain
  from the first gate with it, counted against the attempt budget —
  otherwise gate ordering could be bypassed.
- **APPLY**: `ok` = the change landed; `candidate.branch` (plus e.g. a PR
  URL) says where — the PR delivery backend's response is this same envelope.

## Division of labor

- healing-agent core: stage orchestration, gate ordering, policy dispatch,
  PR backend, restore-on-fail, artifacts.
- External engines (community): repair harnesses behind PROPOSE, fast local
  sandbox/hidden-test verification behind VERIFY, alternative apply
  strategies behind APPLY. Verified-backend status is earned by passing the
  live data-drift acceptance suite (`tests/test_data_drift.py`) through the
  hook.
