# Data Healing design

Data Healing is the boundary layer that repairs a loader when the incoming
document or payload changes shape but still contains valid business data. It
does not guess business rules, weaken a canonical model, or become an Excel/PDF
parser. The application supplies the contract and the extractor; Healing Agent
supplies evidence collection, drift diagnosis, adapter proposals, replay, and
approval gates.

## Target flow

```text
source -> extractor -> evidence envelope -> drift classifier
                                      -> adapter proposal
                                      -> replay + contract/invariant checks
                                      -> report | shadow | canary | apply
```

Every stage produces an artifact. A failed stage preserves the original source,
the original exception, and the evidence envelope. An adapter is accepted only
when it passes old fixtures, the changed sample, and the application's
authoritative invariants.

## Small, dependency-free protocol

The core should use plain mappings/dataclasses and callables, not import
Pydantic, pandas, Docling, Fidelis, or a particular document library.
Applications may provide any of these through an optional adapter.

```python
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    source_kind: str                 # excel, pdf, json, api, database, ...
    extractor: str
    extractor_version: str | None
    schema: Mapping[str, Any]
    samples: Sequence[Mapping[str, Any]]
    provenance: Sequence[Mapping[str, Any]]

@dataclass(frozen=True)
class DataContract:
    name: str
    version: str
    schema: Mapping[str, Any]
    validate: Callable[[Any], Any]
    invariants: Sequence[Callable[[Any], bool]] = ()

@dataclass(frozen=True)
class AdapterProposal:
    source_version: str | None
    target_contract: str
    mapping: Mapping[str, str]
    transformations: Sequence[str]
    code_or_callable: Any
    fixtures: Sequence[Any]
    confidence: float
    evidence: Mapping[str, Any]
```

`validate` may call a Pydantic model, dataclass, JSON Schema validator, or a
hand-written function. The contract is authoritative; the model may propose a
mapping but cannot change required fields or invariants.

## Five implementation stages

### 1. Capture (safe and deterministic)

At the ingestion boundary, capture a bounded, redacted envelope:

- source identifier and version/ETag when available;
- extractor name/version and parsing options;
- field paths, types, null rates, cardinality, and representative samples;
- provenance such as workbook/sheet/header coordinates or PDF page/table/cell
  coordinates;
- the original validation/parse error and a hash of the source.

Never store the whole document by default. Keep a configurable sample budget,
redact secrets before persistence or model submission, and make the envelope
replayable without credentials.

### 2. Classify drift

Use deterministic checks before an LLM:

- renamed header or field with high similarity;
- moved sheet/table or changed nesting;
- safe type/locale/unit conversion;
- optional field added or removed;
- malformed record versus an upstream schema/version change;
- extractor failure (OCR, encoding, merged cells, reading order).

The classifier returns `no_drift`, `record_error`, `schema_drift`,
`extractor_error`, or `ambiguous`. Ambiguous cases are report-only.

### 3. Propose a narrow adapter

Generate a versioned input adapter, not a weaker target contract. An adapter
may rename a column, select a new sheet, unwrap a nesting level, normalize a
date/decimal/unit, or map an explicitly allowed enum alias. It must not invent
required values, silently drop records, or convert an invalid value merely to
make validation pass.

The first vertical slice should accept an application-provided tabular
extractor and demonstrate two Excel layouts mapping to one unchanged contract.
The second should accept a document extractor's table/cell provenance; a PDF
library remains an optional integration.

### 4. Replay and verify

Run the candidate adapter in an isolated process or temporary worktree against:

1. historical valid fixtures;
2. historical invalid fixtures;
3. the changed source sample;
4. adversarial cases for missing required fields, ambiguous aliases, locale,
   duplicate rows, and unit mistakes.

Record validation errors, invariant results, row/record counts, dropped or
quarantined items, and a machine-readable diff. A candidate is not successful
because parsing stops raising an exception.

### 5. Activate with policy

Support four explicit policies:

- `report`: create evidence only;
- `shadow`: run the adapter beside the old loader and compare outputs;
- `canary`: use it for deterministic samples and monitor drift/quality;
- `apply`: activate after approval, with rollback to the prior adapter.

Hard failures and high-risk sources are always observed. Optional deterministic
sampling can use `hash(source_id + contract_version)`, but random sampling must
never decide whether an explicit failure is captured.

## Proposed package boundaries

```text
healing_agent/data_healing/
  protocol.py       # evidence, contract, proposal, result dataclasses
  profile.py        # deterministic schema/profile comparisons
  classify.py       # drift/error classification
  replay.py         # isolated fixture replay and invariant checks
  policy.py         # report/shadow/canary/apply gates
  adapters/
    tabular.py      # generic rows/columns adapter
    pydantic.py     # optional extra, not a core dependency
    document.py     # extractor-neutral provenance adapter
```

The first release should expose `heal_input(...)` or a boundary decorator that
accepts `contract=`, `extractor=`, `fixtures=`, and `policy=`. It should return
a `DataHealingResult` even when the original application exception is
re-raised, so operators can inspect the evidence path without parsing logs.

## Acceptance criteria for the first demonstrator

Given two Excel-like row streams with renamed headers and a stable contract:

1. the original loader fails with a validation error;
2. the envelope records both schemas and sample/provenance evidence;
3. the classifier identifies header drift rather than invalid business data;
4. the proposed adapter maps only approved aliases;
5. old, new, and adversarial fixtures replay successfully or are quarantined;
6. invariants and record counts pass;
7. report/shadow output includes the adapter, mapping, confidence, evidence,
   and rollback information;
8. no Docling, Fidelis, Pydantic, pandas, or model-specific package is needed
   to install the core.

This is the feature that can later make Healing Agent valuable to agent
harnesses: a failed tool input can be treated as a versioned boundary contract
failure, repaired and replayed, rather than patched blindly inside the agent's
business logic.
