"""Tests for LLMClient static helpers (no Anthropic SDK required)."""

from __future__ import annotations

from agents.runtime.llm import LLMClient


class _Block:
    """Minimal duck-typed Anthropic content block."""

    def __init__(self, type_: str, name: str | None = None, input_: dict | None = None, text: str = ""):
        self.type = type_
        self.name = name
        self.input = input_ or {}
        self.text = text

    def model_dump(self) -> dict:
        return {"type": self.type, "name": self.name, "input": self.input, "text": self.text}


class _Response:
    def __init__(self, blocks):
        self.content = blocks


def test_extract_tool_input_finds_named_tool():
    resp = _Response([
        _Block("text", text="thinking..."),
        _Block("tool_use", name="decide_control_action", input_={"decisions": [{"a": 1}]}),
        _Block("tool_use", name="other_tool", input_={"x": 0}),
    ])
    out = LLMClient.extract_tool_input(resp, "decide_control_action")
    assert out == {"decisions": [{"a": 1}]}


def test_extract_tool_input_returns_none_when_missing():
    resp = _Response([_Block("text", text="hello")])
    assert LLMClient.extract_tool_input(resp, "any") is None


def test_dump_content_uses_model_dump_when_available():
    resp = _Response([_Block("text", text="ok"), _Block("tool_use", name="x", input_={"a": 1})])
    dumped = LLMClient.dump_content(resp)
    assert dumped[0]["type"] == "text"
    assert dumped[1]["name"] == "x"
    assert dumped[1]["input"] == {"a": 1}
