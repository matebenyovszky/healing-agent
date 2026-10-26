# Operating Healing Agent under NIS2, GDPR and the Cyber Resilience Act

This page is for an organisation that has to justify running Healing Agent:
an entity in scope of NIS2 (in Hungary, Act LXIX of 2024 on the
cybersecurity of Hungary, which transposes it), a controller under GDPR, or a
manufacturer who ships it inside a product under the Cyber Resilience Act.

Healing Agent is a library. Regulatory duties fall on the organisation that
runs it, not on the library itself. What the library can do is make the
risk visible, keep the data flows explicit and controllable, and ship with
settings that a regulated operator can lock down. This page lists those
settings and the evidence behind them. It is not legal advice.

## What leaves the process, and where it goes

When a decorated function fails, Healing Agent captures evidence (arguments,
variables, an allowlisted part of the environment, optionally recent log
records). It redacts that evidence once, in a single place, and then sends it
to up to four destinations:

| Destination | When | What decides the volume |
|---|---|---|
| AI provider (third party, over the network) | every healing attempt | `EVIDENCE["provider"]` |
| Local artifact files (`_healing_agent_exceptions/`, `_healing_agent_fixes/`, `_healing_agent_backups/`) | `SAVE_EXCEPTIONS`, `SAVE_AI_FIXES`, `BACKUP_ENABLED` | `EVIDENCE["disk"]` |
| GitHub issue in your repository | `GITHUB["issue_on_failure"]` | `GITHUB["issue_detail"]`, `EVIDENCE["issue"]` |
| GitHub pull request in your repository | `GITHUB["pull_request"]` | the repaired file and the attempt ledger |
| Your logging (the `healing_agent` logger) | always | `LOG_MODE`, `DEBUG` |

Redaction (`REDACT_SECRETS`) is on by default. It masks values stored under
sensitive-looking names, plus URL credentials and common token formats inside
environment values and log lines. The redaction is based on a list of known
patterns, so a secret with a bespoke format under a harmless name can pass
through. Add its name to `REDACT_EXTRA_PATTERNS`, and do the same for
personal-data fields such as `["adószám", "taj", "email", "customer[-_ ]?id"]`.

## A configuration profile for regulated environments

Start from these values. Each row says what it buys, so a deviation can be
argued for in the risk assessment.

| Setting | Value | Why |
|---|---|---|
| `AUTO_FIX` | `False` | Proposal only. A generated repair is saved and reported but never applied to running code. Change management stays with people |
| `GITHUB["pull_request"]` | `"draft"`, if repairs should be applied at all | A repair reaches production through your normal review and CI, with the attempt ledger as the description |
| `VERIFY_COMMAND` | your checker | If `AUTO_FIX=True`, nothing is applied that a deterministic check did not accept first |
| `AUTO_SYSCHANGE` | `False` (default) | Never install packages from a running process |
| `REDACT_SECRETS` | `True` (default) | Never disable |
| `REDACT_EXTRA_PATTERNS` | your secret and personal-data field names | Extends the built-in name list |
| `ENVIRONMENT_VARS` | `[]` or a minimal list | Environment capture is an allowlist; keep it to non-secret deployment markers |
| `EVIDENCE["provider"]` | lower limits, `"environment": 0`, `"logs": 0` | Data minimisation towards the third party (GDPR Art. 5(1)(c)) |
| `LOG_BUFFER_SIZE` | `0` (default) | Application log lines are not collected unless you opt in |
| `GITHUB["issue_detail"]` | `"reference"` | The issue carries the failure's identity and pointers, not the captured context |
| `DEBUG` | `False` | Keeps model analysis and gate output out of central log stores |
| Provider | a region or deployment that matches your data-residency duty (an EU Azure OpenAI region, a self-hosted Ollama on the same network) | Keeps the processing inside the jurisdiction your records of processing state |

Operational controls the library cannot enforce for you:

- Run under a dedicated service account. The source tree it may rewrite should
  be writable only by that account.
- Keep the artifact directories out of version control, container images and
  web roots, and include them in your retention schedule. The repository's
  `.gitignore` shows the patterns.
- Hold the GitHub token in a secret store and give it only the scopes the
  enabled features need: issues for escalation, contents and pull requests
  for PR delivery.
- Sign a data-processing agreement with the AI provider. Under GDPR it is a
  processor (Art. 28), and a provider outside the EEA is a transfer (Art. 44
  and following).

## Mapping to the frameworks

| Requirement | What Healing Agent provides | Evidence |
|---|---|---|
| NIS2 Art. 21(2)(d): supply-chain security | Pinned and reviewed dependencies, attested releases, published security policy | [SECURITY.md](../SECURITY.md), `.github/` |
| NIS2 Art. 21(2)(e): vulnerability handling and disclosure | Private vulnerability reporting, coordinated disclosure, GitHub Security Advisories | [SECURITY.md](../SECURITY.md) |
| NIS2 Art. 21(2)(i): access control | Token held only as an environment-variable name, never as a value; no default branch push; draft PRs | `config_template.py` (`GITHUB`) |
| Change management and traceability | Backups before every change, restore on failure, attempt ledger, optional `git apply` patches with provenance hashes, PR delivery | `RESTORE_ON_FAILURE`, `SAVE_GIT_PATCHES`, `GITHUB["pull_request"]` |
| GDPR Art. 25 and Art. 5(1)(c): data protection by default, minimisation | One redaction point, allowlisted environment capture, per-destination evidence limits, log capture off by default | `redactor.py`, `EVIDENCE`, `ENVIRONMENT_VARS` |
| GDPR Art. 32: security of processing | Redaction before any write or transfer, HTTPS for the hosted providers and GitHub, a timeout on every network call | `redactor.py`, `ai_broker.py` |
| CRA Annex I Part II: vulnerability handling, security updates, a software bill of materials | Disclosure policy, security updates on the supported line, dependency graph (exportable as an SPDX SBOM from the repository's *Insights → Dependency graph*) | [SECURITY.md](../SECURITY.md) |

### The Cyber Resilience Act

Healing Agent is free, open-source software developed outside any commercial
activity, so the CRA's obligations for manufacturers do not apply to it as
published. They apply to whoever integrates it into a product on the EU
market. That manufacturer must exercise due diligence on its components
(Art. 13(5)). The table above and [SECURITY.md](../SECURITY.md) are meant to
be that due-diligence record. The reporting obligations under Art. 14 have
applied since 11 September 2026. The remaining obligations apply from
11 December 2027.

### The AI Act

Healing Agent does not train or provide a general-purpose AI model. It calls
one through the provider you configure. Whether a system built with it is
high-risk depends on what that system does. Repairing code at runtime is not
an Annex III use case in itself.
