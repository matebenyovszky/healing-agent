# Verify & Apply design (0.4 target)

The 0.3 heal loop verifies AFTER mutating the live file: the only behavioral
check (re-running with the original arguments) happens once the source is
already rewritten. 0.4 inverts this and makes both stages explicit policy:

```text
exception → capture + redact → hint + fix (AI, MAX_ATTEMPTS bounded)
        → VERIFY chain (ordered gates, all must pass)
        → APPLY policy (where the accepted candidate lands)
```

The guiding principle stays KISS: healing-agent builds no verification
infrastructure of its own. It orchestrates gates that already exist — the
Python compiler, the application's own tests, the repository's own CI — and
exposes one subprocess boundary for everything external.

## VERIFY — ordered gates, all must pass

| Gate | What it does | Cost | Config needed |
|---|---|---|---|
| `syntax` | `compile()` + single-function AST check | ms | none (always on) |
| `rerun` | execute the candidate with the original arguments on an ISOLATED copy (temp import), never the live file | ms–s | none (default on) |
| `tests` | run application tests declared for the supervised function: `@healing_agent(TEST_COMMAND="pytest tests/test_loader.py")`; failure rejects the fix | s | per function |
| `command:<cmd>` | external verifier over the subprocess/JSON protocol (e.g. a sandbox/hidden-test engine such as Aether in check mode) | s | external tool |
| `pr-checks` | open a PR from the candidate and treat the repository's OWN CI as the gate | minutes | **none** — the CI already exists |

`pr-checks` is the zero-config profile: no per-function test declarations —
the whole existing suite validates the repair, using infrastructure the team
already trusts. `tests` is the fast, targeted profile for live processes.
They compose: cheap gates first filter garbage so the expensive CI gate (and
human reviewers) never see it.

## APPLY — where an accepted candidate lands

| Policy | Behavior |
|---|---|
| `report` | artifacts only; the original exception propagates |
| `patch` | reviewable diff + provenance sidecar (today's `GIT_MODE="patch"`) |
| `direct` | backup → write → reload → continue (classic behavior, default) |
| `command` | delegate apply to an external tool over the same subprocess protocol (validate/sandbox/apply/rollback externally) |
| `pr` | branch → commit the patch → push → pull request |
| `direct+pr` | heal locally NOW **and** open the PR for durability |

`GIT_MODE` and the mutation-backend hook are absorbed as branches of this one
switch (backwards-compatible aliases retained).

## The PR flow in detail (standard Git machinery only)

```text
candidate passes local gates
  → branch from current HEAD → commit patch (provenance sidecar in PR body)
  → push → open PR (draft by default)
  → [optional] wait for checks (PR_WAIT_FOR_CHECKS=True)
       green → continue locally with the candidate (the process already
               holds it: write + reload — no need to wait for merge
               mechanics) and let GitHub native auto-merge land it
       red   → PR stays open for humans; the original error propagates;
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

Verification (`command:`), external apply (`command`), and the PR delivery
itself are all implementable as commands speaking the same versioned
JSON-over-stdin protocol (`healing-agent-mutation-v1`, introduced by the
community mutation-backend hook). The first-party PR backend is simply a
`gh`-based script on that boundary — the first of hopefully many backends.
The subprocess boundary is also a dependency and license boundary: external
engines stay external.

## Division of labor

- healing-agent core: gate ordering, policy dispatch, PR backend, artifacts.
- External engines (community): fast local sandbox/hidden-test verification
  and alternative apply strategies behind `command`. Verified-backend status
  is earned by passing the live data-drift acceptance suite
  (`tests/test_data_drift.py`) through the hook.
