# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately**, through GitHub's private
vulnerability reporting:
[Report a vulnerability](https://github.com/matebenyovszky/healing-agent/security/advisories/new).
Do not open a public issue, pull request or discussion for it.

A useful report names the version, the configuration keys involved (never
their secret values), what an attacker controls, and what they gain.

What happens next:

| Step | Target |
|---|---|
| Acknowledgement | within 5 working days |
| First assessment (accepted / not a vulnerability / more information needed) | within 10 working days |
| Fix released for a confirmed issue | as fast as severity requires; critical and high issues take priority over all other work |
| Public advisory | when the fix is released, through a GitHub Security Advisory (with a CVE where applicable), crediting the reporter unless they prefer otherwise |

Disclosure is coordinated: the advisory is published once a fixed version is
on PyPI, or after 90 days if no fix can be agreed, whichever comes first.

## Supported versions

Security fixes go into the latest minor release line. Healing Agent is
pre-1.0, so upgrading within a minor line never requires a configuration
change.

| Version | Supported |
|---|---|
| 0.5.x | ✅ |
| < 0.5 | ❌ upgrade to 0.5.x |

## What counts as a vulnerability

Healing Agent applies AI-generated code to a running program when
`AUTO_FIX=True`, which is the documented default. That a generated repair runs
is the design, not a vulnerability. These are vulnerabilities:

- a secret or captured value reaching a destination (AI provider, disk
  artifact, GitHub issue or pull request, log output) that the documented
  redaction and `EVIDENCE` settings say it must not reach
- data from outside the program steering which code is generated or applied
  past a configured gate (`VERIFY_COMMAND`, `AUTO_FIX=False`, PR delivery)
- a write outside the files and artifact directories the documentation names
- a package installed, a command run or a network request made that the
  configuration did not enable
- any weakness in the release and supply chain described below

## How releases are protected

- Releases are built and published by GitHub Actions only, through PyPI
  Trusted Publishing (short-lived OIDC credentials; no upload token exists),
  from a job separate from the one that runs third-party build code.
- Every PyPI upload carries PEP 740 attestations binding the files to this
  repository and workflow.
- Workflow actions are pinned to commit SHAs; Dependabot proposes updates
  after a cooldown, and only patch and minor updates merge automatically once
  every required check passes.
- Every change is scanned by CodeQL (Python and the workflows themselves),
  gitleaks over the full history, GitHub secret scanning with push protection,
  dependency review and `pip-audit` over the resolved dependency tree.

For how to operate Healing Agent in an environment with regulatory duties
(NIS2, GDPR, the Cyber Resilience Act), see
[docs/security-compliance.md](docs/security-compliance.md).
