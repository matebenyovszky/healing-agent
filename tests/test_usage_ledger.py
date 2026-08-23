"""Token accounting for one healing session.

The ledger answers "what did this repair cost", which no single model call can
answer: a repair is a hint call, a fix call, and any retries. Three properties
are worth pinning down, because each of them is a way to be quietly wrong:

* a provider that reports no usage must leave ``None``, not a zero that reads
  as "this call was free";
* totals must not accumulate across healing sessions;
* nothing but counts may enter the ledger, because it is written to disk.
"""

from healing_agent import ai_broker, usage_ledger


class _FakeResponse:
    def raise_for_status(self):
        return None

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_records_are_ignored_outside_a_session():
    # A stray model call from a tool, with no healing session open, must not
    # start accumulating records in a long-lived process.
    usage_ledger.record(provider="openai", model="m", prompt_tokens=10)
    assert usage_ledger.records() == []
    assert usage_ledger.summary()["calls"] == 0


def test_totals_sum_the_calls_of_one_session():
    token = usage_ledger.start()
    try:
        usage_ledger.record("openai", "m", seconds=1.5, prompt_tokens=100, completion_tokens=20)
        usage_ledger.record("openai", "m", seconds=0.5, prompt_tokens=200, completion_tokens=30)

        totals = usage_ledger.summary()
        assert totals["calls"] == 2
        assert totals["prompt_tokens"] == 300
        assert totals["completion_tokens"] == 50
        assert totals["seconds"] == 2.0
        assert totals["partial"] is False
    finally:
        usage_ledger.reset(token)


def test_sessions_do_not_leak_into_each_other():
    first = usage_ledger.start()
    usage_ledger.record("openai", "m", prompt_tokens=100)
    usage_ledger.reset(first)

    second = usage_ledger.start()
    try:
        assert usage_ledger.summary()["calls"] == 0
    finally:
        usage_ledger.reset(second)


def test_unreported_usage_stays_none_and_is_marked_partial():
    token = usage_ledger.start()
    try:
        usage_ledger.record("ollama", "m", prompt_tokens=None, completion_tokens=None)
        assert usage_ledger.summary()["prompt_tokens"] is None
        assert "not reported" in usage_ledger.describe()

        usage_ledger.record("ollama", "m", prompt_tokens=10, completion_tokens=5)
        totals = usage_ledger.summary()
        # One of the two calls reported nothing: the total is real but partial,
        # and must say so rather than passing as a complete figure.
        assert totals["prompt_tokens"] == 10
        assert totals["partial"] is True
    finally:
        usage_ledger.reset(token)


def test_record_count_is_bounded():
    token = usage_ledger.start()
    try:
        for _ in range(usage_ledger.MAX_RECORDS + 25):
            usage_ledger.record("openai", "m", prompt_tokens=1)
        assert len(usage_ledger.records()) == usage_ledger.MAX_RECORDS
    finally:
        usage_ledger.reset(token)


def test_ollama_response_counts_are_recorded(monkeypatch):
    monkeypatch.setattr(
        ai_broker.requests,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse(
            {"response": "fixed", "prompt_eval_count": 321, "eval_count": 42}
        ),
    )

    token = usage_ledger.start()
    try:
        ai_broker._get_ollama_response("prompt", {"host": "http://h", "model": "qwen"})
        record = usage_ledger.records()[0]
        assert record["provider"] == "ollama"
        assert record["model"] == "qwen"
        assert record["prompt_tokens"] == 321
        assert record["completion_tokens"] == 42
        assert record["seconds"] is not None
    finally:
        usage_ledger.reset(token)


def test_a_provider_without_usage_records_the_call_anyway(monkeypatch):
    monkeypatch.setattr(
        ai_broker.requests,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse({"response": "fixed"}),
    )

    token = usage_ledger.start()
    try:
        ai_broker._get_ollama_response("prompt", {"host": "http://h", "model": "m"})
        record = usage_ledger.records()[0]
        assert record["prompt_tokens"] is None
        assert usage_ledger.summary()["calls"] == 1
    finally:
        usage_ledger.reset(token)


def test_ledger_holds_no_prompt_or_completion_text(monkeypatch):
    monkeypatch.setattr(
        ai_broker.requests,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse(
            {"response": "SECRET COMPLETION", "prompt_eval_count": 1, "eval_count": 1}
        ),
    )

    token = usage_ledger.start()
    try:
        ai_broker._get_ollama_response("SECRET PROMPT", {"host": "http://h", "model": "m"})
        serialized = repr(usage_ledger.records())
        assert "SECRET PROMPT" not in serialized
        assert "SECRET COMPLETION" not in serialized
    finally:
        usage_ledger.reset(token)
