# Aether-style Safe Mutation Backend

Healing Agent's default repair path keeps the project deliberately small:

```text
exception -> generated Python function -> backup -> replace function -> reload
```

For experiments with safer autonomous mutation, Healing Agent can optionally
delegate the file mutation step to an external command:

```python
MUTATION_BACKEND = "command"
MUTATION_COMMAND = "python path/to/aether_healing_agent_adapter.py"
MUTATION_TIMEOUT_SECONDS = 120
```

The command receives a JSON payload on stdin:

```json
{
  "protocol_version": "healing-agent-mutation-v1",
  "source_file": "path/to/module.py",
  "function_name": "broken_function",
  "fixed_code": "def broken_function(...): ...",
  "error": {},
  "function_info": {}
}
```

It should validate, sandbox, apply, and verify the repair, then print:

```json
{"ok": true}
```

or reject it:

```json
{"ok": false, "rolled_back": true, "error": "hidden test failed"}
```

This design keeps Aether or other safe-mutation engines optional and external.
The default `MUTATION_BACKEND = "direct"` behavior is unchanged.

## Why use a safe mutation backend?

Self-healing systems are most dangerous when a generated repair is wrong but
still mutates the repository. A safe mutation backend can add:

- structured patch validation
- sandboxed apply
- hidden test verification
- snapshot rollback
- mutation evidence logs
- smaller patch-oriented model outputs

In one deterministic local A/B benchmark from the Aether project, valid repairs
matched raw full-file mutation while Aether-style mutation prevented all tested
bad-repair corruptions and reduced generated output size. Treat those numbers
as integration motivation, not production proof.
