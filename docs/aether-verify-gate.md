# Aether as a VERIFY command gate

Healing Agent can run Aether as a check-only verifier before a generated repair
touches the live source file:

```python
VERIFY_COMMAND = "python path/to/aether_healing_agent_verify.py"
```

The command runs inside a temporary workspace where the candidate function has
already been applied. The live file is unchanged while the gate runs.

The gate contract is intentionally small:

- exit code `0` accepts the candidate;
- any nonzero exit code rejects it;
- protocol-aware gates may read the `HEALING_AGENT_CANDIDATE` environment
  variable;
- stdout may contain JSON detail, such as
  `{"ok": false, "error": "hidden test failed"}`, but the exit code decides.

This gives Aether the role that fits the 0.4 pipeline best: validate, sandbox,
and report structured failure detail without taking ownership of Healing
Agent's final write step. Aether can still be used later as an `APPLY="command"`
engine where snapshot-backed, multi-file, transactional mutation is needed.
