# Propose, Verify & Apply design

*Target: the "repairs that can be trusted" milestone (see
[ROADMAP.md](../ROADMAP.md)). The milestone spans several minor releases, so it
is named rather than numbered — version numbers follow from release content.*

The 0.3 heal loop verifies AFTER mutating the live file: the only behavioral
check (re-running with the original arguments) happens once the source is
already rewritten. This design inverts that and makes the whole pipeline explicit
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

| Mode | Behavior | Status |
|---|---|---|
| exception (default) | context is captured when a supervised function raises | shipped |
| `capture` | `healing_agent.capture(label="after-fetch")` writes a redacted context snapshot at any point in the code; no AI call, no mutation | **shipped** |
| log ring buffer | `LOG_BUFFER_SIZE` > 0 plus `healing_agent.enable_log_capture()` keeps the last N application log records and includes them in the captured context and both prompts | **shipped** |
| `probe` | perform a configured call (e.g. an API request) and save its context — "what does this integration actually return today?" | planned, best as a model-invokable tool |

### Evidence: pushed vs. pulled

Everything the model sees today is *pushed*: the prompt carries a fixed
selection, and what it omits is invisible. The `variables` block — locals and
globals, about 2.5 KB of a typical 8 KB context — is captured and saved but
deliberately **never sent**, because it would roughly double the ~990-token
fix prompt on every attempt, and attempts nest. The ring buffer is a
measured exception to that rule: it is off unless asked for, and its size is
the operator's explicit budget.

The better long-term answer is *pulled* evidence: give the model tools
(`get_variables`, `search_logs`, `probe`) so it requests only what a specific
failure needs. See ROADMAP item 7; it depends on the structured/tool-calling
provider layer.

⚠ Log messages are free text, so name-based redaction cannot see inside them:
`logger.info(f"token={t}")` would reach the provider. The ring buffer is
therefore opt-in, level-filtered, and documented as such.

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

### Interoperating with issue→PR agents

The `issue` backend is not primarily a way to notify a human — it is the
handshake with an entire class of tools that already exists and is missing
exactly what healing-agent has.

[OpenHands](https://github.com/All-Hands-AI/OpenHands),
[SWE-agent](https://github.com/SWE-agent/SWE-agent),
[auto-code-rover](https://github.com/nus-apr/auto-code-rover), GitHub's
Copilot coding agent and the research agents behind them all share one shape:
**a GitHub issue goes in, a pull request comes out.** They are good at
repository-scale reasoning and they run on infrastructure someone else
maintains. What none of them can do is observe a running program: by the time
they read the issue the process is gone, and with it the arguments, the local
variables, the log lines leading up to the failure, and the knowledge of which
candidate repair was already tried and rejected. Reproducing a runtime failure
from a bug report is itself an open research problem.

healing-agent occupies precisely the other half. It sits inside the process at
the moment of the exception, and its artifacts already contain what those
agents have to guess at.

```text
runtime exception → OBSERVE (evidence) → PROPOSE/VERIFY (local attempt)
   → gave up → issue with the evidence attached
       → external issue→PR agent writes the patch
           → PR → pr-checks (the repository's own CI) → merge
               → next run is healed
```

Design consequences, all of them cheap:

- **The issue body is agent input, not a notice.** Beyond the human-readable
  summary it carries, at the configured detail level, the redacted context
  JSON (arguments, locals, traceback frames), the failing source line text,
  the candidate healing-agent generated, and the gate verdict that rejected
  it. A rejected candidate is signal, not noise: it tells the next agent
  which direction is already known to fail.
- **Nothing bespoke is invented for them.** The handshake is a labelled
  GitHub issue and a pull request — the interface every one of these tools
  already speaks. No plugin, no SDK, no version coupling.
- **The verification story does not change.** A patch arriving from an
  external agent is not trusted more than one healing-agent generated
  itself: it flows through `pr-checks` (the repository's own CI) like any
  other candidate, and the original exception keeps propagating until
  something green lands.
- **Reciprocal option.** The same protocol works in the other direction:
  such an agent can be plugged in as a `PROPOSE = "command"` backend for
  synchronous repair, with the `issue` backend as its asynchronous form. One
  boundary, two latencies.

#### The same agents, plugged in directly as PROPOSE backends

Escalating through an issue is the zero-coupling path, and it is the right
default. But every one of these tools also has a headless entry point that
takes a problem statement and a repository and returns a patch — which is
exactly the `PROPOSE = "command"` contract. The adapter is a shell script
that writes the redacted context to a problem-statement file, runs the tool,
and echoes the unified envelope with the resulting patch as `candidate`.

| Engine | Headless invocation | Where the patch appears |
|---|---|---|
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | `sweagent run --agent.model.name=… --env.repo.path=<repo> --problem_statement.path=<file>` | a `.patch` file whose path the run prints |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | `openhands --headless -f task.txt` (`--json` for machine-readable output) | working tree of the mounted repository |
| [auto-code-rover](https://github.com/nus-apr/auto-code-rover) | `python app/main.py local-issue --local-repo <repo> --issue-file <file> --output-dir <dir> --task-id …` | `selected_patch.json` in the output directory |

Flag names and outputs are the current upstream ones and will drift; that is
precisely why the adapter is a user-supplied script on the subprocess
boundary and not code in this repository. What healing-agent guarantees is
the part that does not drift: the problem statement it writes (redacted
context, traceback frames, failing line, rejected candidates and their gate
verdicts), and that whatever comes back is treated as an unverified
candidate — it enters the VERIFY chain at the first gate like any other.

Two properties make this worth having even though the `issue` path exists:
it is synchronous, so a repair can land inside the same run rather than the
next one; and it works on repositories with no GitHub remote at all.

The honest limit: these engines expect a repository and a task description,
and they are priced accordingly — a heavyweight agent per runtime exception
is the wrong default for a loader that fails every night at 02:00. Use them
where a repair genuinely needs repository-scale reasoning, and let the
built-in provider handle drift.

### Incident memory feeds PROPOSE

The artifact directories are currently written and never read again. Indexing
them by failure fingerprint and injecting the most similar *resolved* case
into the fix prompt costs one JSON file and no new dependency, and it targets
this library's actual workload: recurring failures. It also improves the
escalated issue — "this failure class was healed on 2026-03-12 by this
candidate, and the same fix no longer works" is a far better bug report than
a bare traceback. Tracked as roadmap item 14.

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
| `command` | **shipped.** Run any command in a temporary workspace holding the candidate FILE with the repair already applied; **exit code 0 = pass**, and a command that cannot start is a configuration error rather than a verdict. Protocol-aware engines (e.g. Aether in check mode) can read the redacted candidate context from the `HEALING_AGENT_CANDIDATE` env var and MAY print a JSON object to stdout (`{"ok": false, "error": "hidden test failed"}`) for detail — the exit code alone decides. Set globally (`VERIFY_COMMAND`) or per function via the decorator's local-config merge. Ordered gates: a list of argument lists. | s | one command line |
| `pr-checks` | open a PR from the candidate and treat the repository's OWN CI as the gate | minutes | **none** — the CI already exists |

There is deliberately no separate "tests" gate: an application test run IS a
command. One gate type covers self-contained checkers, hidden-test engines,
linters, or anything else that can express pass/fail as an exit code.

**Workspace scope — deliberately limited.** The gate runs in a temporary
directory holding the candidate FILE alone. That serves a self-contained
checker, a sandbox engine or a linter, and it is all the gate does.

An application's own test suite needs more: a test imports siblings, reads
fixtures and expects its package layout. Making that work means placing the
whole project in the workspace with one file swapped, and an earlier draft of
this document used `pytest tests/test_loader.py` as the example while only the
file scope existed — which could not work, and failed as a *rejection*,
discarding valid repairs.

That capability was prototyped and then deliberately dropped, because copying
a project tree brings a long tail of failure modes — size, symlinks,
permissions, untracked files such as `.env` that the copy would not contain,
assumptions about where the virtualenv lives — and each of them turns into a
support question about someone else's repository layout. The gate is more
useful being small and predictable.

If the capability is wanted, this is how it should be built, and the choice is
not obvious: copy the WORKING TREE, not a `git worktree`. A worktree checks
out `HEAD`, so on any machine with uncommitted changes the gate would pass
judgment on code other than the code that is running. A filtered copy with a
size guard, falling back to the file scope when the tree is too large, is the
variant whose verdict is about the program in front of us. Ask, and it can be
added behind an opt-in setting.

The zero-configuration way to get the full suite as a gate is different and
already designed: let the repository's own CI run it on a pull request
(`pr-checks` below). The project already has that infrastructure; duplicating
it locally is what this note declines to do.

`pr-checks` is the zero-config profile: no per-function declarations — the
whole existing suite validates the repair, using infrastructure the team
already trusts. Gates compose cheapest-first: syntax and rerun filter garbage
so the expensive CI gate (and human reviewers) never see it.

## APPLY — where an accepted candidate lands

| Policy | Behavior |
|---|---|
| `report` | artifacts only; the original exception propagates |
| `patch` | reviewable diff + provenance sidecar (today's `GIT_MODE="patch"`) |
| `ask` | print the candidate diff and apply only on explicit confirmation; anything but a yes is treated as a definitive failure (restore + re-raise). Non-interactive sessions (no TTY) refuse rather than assume consent |
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
   byte-identical to its pre-healing state.* — **shipped in 0.3.1**
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

## Why this is not a CI healer

The obvious-looking product next door is "CI went red, let an LLM fix it and
open a PR". That space is crowded and it is not ours: Codex has a documented
CI-autofix recipe, Claude Code watches PRs and pushes fixes, GitHub is putting
coding agents inside the Actions loop, and `autofix.ci` covers the
deterministic formatter/linter half. Those tools are on home ground there —
CI hands them a repository, a diff and a log, which is exactly what an
issue→PR agent needs.

What none of them can see is the running process. Healing Agent's ground is
the 02:00 scheduled job: no pull request, no diff, no reviewer, no agent
watching — just an exception and the values that were in memory when it
happened. That evidence exists for one moment and then is gone.

So the relationship is inverted deliberately:

| | CI healer | Healing Agent |
|---|---|---|
| Trigger | a red pipeline | a runtime exception inside the process |
| Evidence | logs and the diff | arguments, locals, traceback frames, recent log records |
| CI's role | the thing being repaired | **the verification gate** (`pr-checks`) |
| Failure mode it prevents | a broken build | a scheduled job silently producing wrong data |

CI is therefore infrastructure we *consume*, not a surface we compete on: the
repository's own suite is what decides whether a runtime-derived candidate is
allowed to land (`pr-checks` + `APPLY="pr"`). A small public CI healer we
looked at makes the point from the other side — its allowlist restricts it to
`requirements.txt`, `deployment.yaml` and the workflow file, i.e. it repairs
infrastructure, never the application logic that produced a wrong number.

The one CI-shaped artifact worth shipping is thin: an optional GitHub Action
that runs a scheduled job under `healing-agent run`, so a nightly pipeline
gets the same observe → propose → verify → apply → restore loop and the same
escalation path. That is packaging, not a second product.

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
