from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.operator_chat import LlmResponse, OperatorChatEngine, ToolCall


class FakeToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def list_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_runtime_health",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict[str, str] | None = None) -> str:
        args = arguments or {}
        self.calls.append((name, args))
        return "Ready: yes"


class FakeLlmClient:
    def __init__(self, responses: list[LlmResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, object]]] = []

    def complete(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> LlmResponse:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("No fake LLM responses left.")
        return self.responses.pop(0)


class OperatorChatEngineTest(unittest.TestCase):
    def test_engine_executes_tool_then_returns_assistant_text(self) -> None:
        llm = FakeLlmClient(
            [
                LlmResponse(
                    content="",
                    tool_calls=(
                        ToolCall(
                            id="call-1",
                            name="get_runtime_health",
                            arguments="{}",
                        ),
                    ),
                ),
                LlmResponse(content="The simulator is healthy and ready."),
            ]
        )
        tools = FakeToolService()
        engine = OperatorChatEngine(llm, tools)

        result = engine.run_turn(history=[], user_message="Is the simulator ready?")

        self.assertEqual(tools.calls, [("get_runtime_health", {})])
        self.assertEqual(result["reply"], "The simulator is healthy and ready.")
        self.assertEqual(len(result["history"]), 2)

    def test_engine_normalizes_tool_arguments_to_strings(self) -> None:
        llm = FakeLlmClient(
            [
                LlmResponse(
                    content="",
                    tool_calls=(
                        ToolCall(
                            id="call-1",
                            name="get_runtime_health",
                            arguments='{"timeout": 30, "verbose": true}',
                        ),
                    ),
                ),
                LlmResponse(content="Done."),
            ]
        )
        tools = FakeToolService()
        engine = OperatorChatEngine(llm, tools)

        engine.run_turn(history=[], user_message="Check again.")

        self.assertEqual(tools.calls, [("get_runtime_health", {"timeout": "30", "verbose": "True"})])

    def test_engine_raises_after_too_many_rounds(self) -> None:
        llm = FakeLlmClient(
            [
                LlmResponse(
                    content="",
                    tool_calls=(ToolCall(id="call-1", name="get_runtime_health", arguments="{}"),),
                ),
                LlmResponse(
                    content="",
                    tool_calls=(ToolCall(id="call-2", name="get_runtime_health", arguments="{}"),),
                ),
            ]
        )
        tools = FakeToolService()
        engine = OperatorChatEngine(llm, tools, max_rounds=1)

        with self.assertRaises(RuntimeError):
            engine.run_turn(history=[], user_message="Loop")


if __name__ == "__main__":
    unittest.main()
