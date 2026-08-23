# Propose, Verify & Apply design (0.4 target)

The 0.3 heal loop verifies AFTER mutating the live file: the only behavioral
check (re-running with the original arguments) happens once the source is
already rewritten. 0.4 inverts this and makes the whole pipeline explicit
policy — three swappable stages behind one external boundary:

```text
exception → capture + redact
        → PROPOSE  (who writes the fix)
        → VERIFY   (ordered gates, all must pass — BEFORE the live file changes)
        → APPLY    (where the accepted candidate lands)
        → on definitive failure: RESTORE the pre-healing source from backup,
          re-raise the original exception
```

The guiding principle stays KISS: healing-agent builds no repair, test, or
sandbox infrastructure of its own. It orchestrates things that already exist —
the AI provider, the Python compiler, the application's own tests, the
repository's own CI — and exposes ONE subprocess/JSON boundary for everything
external.

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
| `reference` (default) | error type + message, function name + file, timestamp/artifact id pointing to the LOCAL `_healing_agent_exceptions/` record — the reader fetches details from the machine/logs | lowest: no values leave the machine |
| `redacted` | the name-based redacted context JSON attached | sensitive VALUES under innocently-named variables can still slip through — documented, opt-in |
| `ai-anonymized` | an extra AI pass rewrites values (names, ids, amounts) into placeholders before upload | costs a model call; anonymization quality is probabilistic — opt-in |

Authentication follows the standing guardrail: the config stores only the
NAME of the environment variable holding the token
(`GITHUB["token_env"] = "GITHUB_TOKEN"`) or relies on `gh` CLI auth — the
token value itself never appears in `healing_agent_config.py`, which is
exactly the file class that must stay secret-free.

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

## RESTORE on definitive failure

Backups already exist (`BACKUP_ENABLED`, timestamped copies per attempt) but
0.3 never restores them: the in-memory module is rolled back, the file is not.
0.4 closes this: when healing ends in failure after the live file was mutated
— `MAX_ATTEMPTS` exhausted, or a post-apply gate failed — healing-agent
restores the FIRST backup of the healing session (the pre-healing original),
so the working tree is exactly as it was, and re-raises the original
exception. No half-healed files are ever left behind.
*Acceptance: after any failed healing session, the source file is
byte-identical to its pre-healing state.*

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
