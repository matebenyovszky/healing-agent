# Repair benchmark design

Two questions this repository cannot currently answer:

1. **Which model should I configure?** Today the honest answer is "the one we
   happened to test with". A user running a local Ollama model has no way to
   know whether it can heal a renamed CSV header, or whether it will quietly
   invent one.
2. **Is a prompt change an improvement?** The acceptance suite answers
   pass/fail on one model, at one moment. It cannot say that a prompt edit
   raised the repair rate from 60% to 80%, or that it fixed one scenario and
   broke two others.

The benchmark exists to answer both, and — as a by-product — to produce
numbers a paper can cite (ROADMAP item 13).

## Design rules

- **One source of truth for scenarios.** The pytest acceptance suite and the
  benchmark read the SAME scenario dataset. A scenario is not allowed to live
  only in the benchmark: if it is worth measuring it is worth gating CI on,
  and duplication would let the two drift apart. `tests/test_data_drift.py`
  becomes a thin parametrized wrapper over the dataset.
- **Measure refusals, not just repairs.** The anti-fabrication scenarios are
  the most important rows in the table. A model that heals 9 of 9 drift cases
  and also invents an `amount` column when none exists is worse than one that
  heals 7 and refuses correctly.
- **Report the failures.** Deferred scenarios (merged Excel cells,
  formula-vs-value drift) belong in the published table as unsupported, not
  omitted.
- **No hidden cost.** Every cell records tokens, wall time, and attempts. A
  repair rate without a cost column is not a result.

## Scenario dataset

```text
benchmark/scenarios/<scenario-id>/
    scenario.toml        # metadata: kind, function name, expected result, notes
    loader.py            # the decorated function under repair (pre-healing)
    input_old.<ext>      # the format the loader was written for
    input_new.<ext>      # the drifted format that triggers healing
```

`scenario.toml` carries what the runner needs and nothing else:

```toml
id = "csv-renamed-headers"
kind = "heal"              # heal | guard
function = "load_sales"
expected = 4200            # the business result, identical for old and new
drift = "translated column headers (amount -> osszeg)"
max_attempts = 3           # only where a scenario genuinely needs more
```

For `kind = "guard"` there is no expected value: the requirement is that the
healed code RAISES rather than returning a number. Guard scenarios carry the
decoy description instead, because that is what makes them adversarial.

Excel scenarios need generated fixtures rather than committed binaries; the
generator stays a function in the dataset directory, and the runner calls it.

## Outcome taxonomy

Every cell (one scenario × one configuration × one repeat) ends in exactly
one of these, and the distinction between the first two is the whole point:

| Outcome | Meaning |
|---|---|
| `healed` | the drifted input produces the expected result **and** the original input still does |
| `false-fix` | the exception is gone but the result is wrong, or the old format broke — a "successful" repair that silently corrupts business data |
| `refused` | guard scenario: the healed code raised a clear error instead of inventing data (this is a PASS) |
| `fabricated` | guard scenario: the healed code returned a number it had no basis for (the dangerous failure) |
| `unhealed` | healing gave up cleanly: attempts exhausted, source restored, original exception re-raised |
| `error` | infrastructure failure — provider unreachable, timeout, harness bug — excluded from rates, reported separately |

`false-fix` and `fabricated` are the metrics nobody publishes and the only
ones that matter for trusting a healer. The headline result should be a pair,
never a single number: **repair rate at a given false-fix rate.**

Per cell the runner also records: attempts used, wall-clock seconds, prompt
and completion tokens, estimated cost (zero for local models), changed-line
count of the accepted diff, and the path to the artifact directory when the
outcome was not `healed`.

## The matrix

| Dimension | Examples | Why |
|---|---|---|
| model | `ollama:qwen2.5-coder:7b`, `ollama:qwen2.5-coder:32b`, `azure:gpt-4o-mini`, `anthropic:claude-haiku-4-5` | the primary question |
| sampling params | temperature, seed, top_p, `num_ctx` | a 7B model at `num_ctx=2048` truncates the context and fails for reasons that have nothing to do with its repair ability |
| prompt variant | `default`, `no-drift-hints`, `minimal` | proves the drift-aware sentences actually earn their place |
| `MAX_ATTEMPTS` | 1, 3, 5 | separates "cannot do it" from "needs another round" |
| repeats | k = 5 (local), k = 3 (paid) | LLM output is not deterministic |

**Report `pass^k`, not just `pass@1`.** For code generation, "solved in at
least one of k attempts" is the interesting number. For a healer running
unattended at 02:00 it is the wrong one: what matters is that ALL k runs
succeeded. Report both, lead with the reliability figure.

## Runner

```bash
python -m benchmark.run \
    --models benchmark/models.toml \
    --scenarios all \
    --repeats 5 \
    --out benchmark/results/
```

- every cell runs in a fresh temporary directory with its own copy of the
  loader; nothing is shared, so a healed file never leaks into the next cell;
- the run is resumable — completed cells are keyed by
  `(scenario, model, params, prompt, repeat)` and skipped on re-run, because
  a 6-model × 13-scenario × 5-repeat sweep on local hardware takes hours;
- results are written as JSONL (one row per cell, append-only) plus a
  generated Markdown summary; both are committed under
  `benchmark/results/<date>/`, so history is auditable and a prompt change's
  effect can be diffed;
- every row records the provenance needed to reproduce it: healing-agent
  version, prompt variant hash, full model config, and the scenario dataset
  hash.

`benchmark/models.toml` is the only file a user edits to run their own sweep:

```toml
[[model]]
id = "qwen2.5-coder-7b"
provider = "ollama"
model = "qwen2.5-coder:7b"
params = { temperature = 0.2, seed = 7, num_ctx = 8192 }

[[model]]
id = "gpt-4o-mini"
provider = "azure"
deployment_name = "gpt-4o-mini"
params = { temperature = 0.2 }
```

## What has to change in the library first

The benchmark is mostly harness code, but four things in `healing_agent/`
block it. Each is independently useful, and three of them have shipped:

1. **Provider selectable per run — shipped ✅.** `AI_PROVIDER` in the shipped
   template now reads `HEALING_AGENT_PROVIDER` from the environment (default
   unchanged), and `load_config(local_config_path=...)` already accepts a
   generated per-cell config file for anything the environment cannot express.
2. **Sampling parameters passed through — shipped ✅.** Every provider block
   accepts a `params` dict, forwarded verbatim: request keyword arguments for
   Azure/OpenAI/Anthropic/LiteLLM, and Ollama's `options` object — which
   previously received nothing at all, so temperature, `seed` and `num_ctx`
   could not be set for local models. Absent or empty `params` sends exactly
   what earlier releases sent, so a sweep cannot silently shift the baseline.
3. **Token usage captured — shipped ✅.** `healing_agent/usage_ledger.py`
   records one entry per model call for the duration of a healing session
   (provider, model, seconds, prompt/completion tokens) and the totals are
   written into the saved fix artifact. Counts only: no prompt or completion
   text enters the ledger, because the artifact is meant to be shareable. A
   provider that reports no usage leaves `None` rather than a zero, and a
   total mixing reported and unreported calls is flagged `partial`.
   **Prices are deliberately not in the library** — they change faster than
   releases; tokens are the durable fact, and `models.toml` carries the rate.
4. **Prompt variants selectable — not yet.** The fix and hint prompts are
   string literals inside `ai_code_fixer.py` and `ai_hint_generator.py`. To
   A/B them they must be addressable: a `prompts/` directory with named
   variants and a `PROMPT_VARIANT` setting, defaulting to today's text so
   nothing changes for existing users.

Items 1–3 are what the local-model experiments needed; item 4 is what turns
the benchmark from "which model" into "which prompt".

## Running a sweep today

The matrix runner does not exist yet, but the library is already
parameterizable, so the acceptance suite can be pointed at any model:

```bash
# one local model, one setting
HEALING_AGENT_PROVIDER=ollama OLLAMA_MODEL=qwen2.5-coder:7b \
    python -m pytest tests/test_data_drift.py -v
```

Sampling settings live in the config file, because they are per provider:

```python
OLLAMA = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    "timeout": 300,                       # local models are slower than APIs
    "params": {"temperature": 0.2, "seed": 7, "num_ctx": 8192},
}
```

Two failure modes to rule out before blaming the model:

- **`num_ctx` too small.** The default context window of a local model can be
  shorter than the captured context, which truncates the evidence silently.
  The result looks like a repair failure and is a setup failure.
- **`timeout` too short.** The 120 s default is generous for an API and tight
  for a 32B model on consumer hardware.

Set `DEBUG = True` and each healing session prints its own usage line
(`♣ Model usage: 3 model call(s), 41.2s, tokens in/out: 5120/860`), which is
the per-repair cost the benchmark will aggregate.

## Phasing

- **Phase 1 — runner over the existing scenarios, one model.** Extract the
  11 live scenarios into the dataset, point the pytest suite at it, and make
  the runner reproduce today's pass/fail. Deliverable: a JSONL result file
  and a summary table. No new scenarios, no matrix.
- **Phase 2 — the matrix.** Prerequisites 1–3, then sweep local Ollama models
  (free, so the repeat count can be generous) plus one hosted model as the
  reference line. Deliverable: the published compatibility matrix that
  ROADMAP item 12 promises, with a false-fix column.
- **Phase 3 — prompts and the write-up.** Prerequisite 4, then A/B the
  drift-aware prompt sentences to show what they are worth — the adversarial
  guardrail story in `docs/data-healing.md` says two sentences fixed the
  decoy-column failure; the benchmark is what turns that anecdote into a
  number. Deliverable: the numbers a preprint needs.

## Expected results worth being honest about

Small local models are likely to score badly on the guard scenarios
specifically — refusing to answer is harder than answering, and a 7B model
under context pressure will happily sum the order-number column. If that is
what the data shows, it is a genuinely useful publishable finding: **the
capability threshold for safe healing is higher than the threshold for
apparent healing.** It also has a direct product consequence — the guard
scenarios become a gate a model must pass before it is recommended in the
compatibility matrix at all.
