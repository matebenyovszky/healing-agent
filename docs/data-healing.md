# Data Healing

Data Healing is Healing Agent's answer to a recurring IT failure class: the
code is fine, but the world changed. A CSV renames or reorders its columns, an
API renests its fields, a date format flips locale. The business data is still
there — the structure drifted.

## The approach: minimal code, maximal verification

Healing Agent deliberately does **not** ship a schema-matching engine, fuzzy
matcher, or data-profiling subsystem. The entire implementation is:

1. **Drift-aware prompts.** The code-fixer prompt instructs the model to adapt
   the function so it handles **both** the previous and the new structure
   (runtime header/field inspection, alias mapping), to map fields only by
   names that are synonyms or translations of the *same business concept*, and
   to raise a clear error instead of inventing missing required data. The
   hint-generator prompt carries the matching rule so the analysis step cannot
   steer the fixer toward fabrication.
2. **Acceptance tests as the contract.** A drift scenario passes only when the
   healed source produces the identical business result for the old **and**
   the new input. "The exception disappeared" is never accepted as success.

That is the whole design. Intelligence lives in the model; trust lives in the
tests.

## What is demonstrated (live, `tests/test_data_drift.py`)

| # | Scenario | Drift | Expectation |
|---|---|---|---|
| 1 | CSV renamed headers | English → Hungarian column names | heal, both formats work |
| 2 | CSV reordered columns | index-based parsing broke | heal, both formats work |
| 3 | API payload reshaped | keys renamed + renested | heal, both formats work |
| 4 | Date format drift | ISO → `DD.MM.YYYY` | heal, both formats work |
| 5 | Error in undecorated helper | fix must adapt at the decorated boundary | heal, both formats work |
| 6 | Required column missing | no honest mapping exists | raise, never fabricate |
| 7 | Missing column + decoy numeric column | order numbers ≠ amounts | raise, never fabricate |

The tests write each loader to a temp module, run the old input (must work
untouched), run the drifted input (triggers healing), then re-import the healed
source and assert both inputs produce the same expected result. They skip
automatically when no AI provider is configured, so CI stays green.

## The guardrail story (why adversarial tests matter)

Scenario 7 initially **failed**: the model saw the drifted headers in the error
context and "fixed" the loader by summing the order-number column as amounts —
even the generated hint encouraged substituting "the numeric column present in
the CSV". Two targeted prompt sentences (an alias must name the *same business
concept*; an identifier/order number/date is never a valid alias for an
amount) fixed the behavior, and the adversarial test keeps it fixed.

This is the working loop for evolving Data Healing:

```text
adversarial test fails -> smallest prompt change -> full suite re-run -> keep the test forever
```

## How to extend

Escalate in this order, and only when a test empirically fails:

1. **Prompt** — a sentence in `ai_code_fixer.py` / `ai_hint_generator.py`.
2. **Context** — give the model more to see (e.g. include related functions
   from the same file in the fix prompt; `agent_tools/tool_list_files_functions.py`
   already exists). Not needed so far: the helper-function scenario passed on
   traceback context alone.
3. **Code** — only if prompts and context demonstrably cannot solve a scenario
   class, consider a small dedicated mechanism. None has been needed yet.

Candidate scenarios worth adding next: Excel workbooks (sheet renames, moved
header rows, merged cells), encoding drift, multi-record quarantine (mixed
valid/invalid rows), paginated API shape changes, and drift in functions with
multiple data sources.

## Guardrails (non-negotiable)

- Never treat "no exception" as success — assert business results.
- Never invent required business data; unmappable input must raise clearly.
- Old-format inputs must keep working after every heal.
- Secrets are redacted before any context reaches a provider or disk.
