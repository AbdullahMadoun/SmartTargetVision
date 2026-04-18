from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .runtime_tool_service import RuntimeToolService


SYSTEM_PROMPT = (
    "You are a remote drone operator controlling a PX4 autopilot through a Gazebo simulator. "
    "You can manage the simulator lifecycle (start, stop, reset, health checks, logs) "
    "and fly one or more drones (connect, arm, takeoff, land, go to GPS coordinates, hold position, "
    "return to launch, send body-frame velocity commands, inspect areas, configure geofences, "
    "record telemetry, capture camera frames, start or stop visual tracking, and check telemetry status). "
    "Always call connect_drone before issuing flight commands to a drone. "
    "For precise positioning, target following, or debugging autonomy, prefer send_body_velocity, "
    "run_visual_tracking_step, and get_visual_tracking_status when appropriate. "
    "Always check get_drone_status after movement commands to confirm the result. "
    "Keep responses concise. Do not invent telemetry data — use the tools. "
    "If visual access is mentioned, remind the user to open the live simulation pane."
)


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class LlmResponse:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


class OperatorLlmClient(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> LlmResponse:
        """Return the next assistant step, optionally with tool calls."""


class OperatorChatEngine:
    def __init__(
        self,
        llm_client: OperatorLlmClient,
        tool_service: RuntimeToolService,
        *,
        max_rounds: int = 6,
    ) -> None:
        self.llm_client = llm_client
        self.tool_service = tool_service
        self.max_rounds = max_rounds

    def run_turn(
        self,
        *,
        history: list[dict[str, str]],
        user_message: str,
    ) -> dict[str, object]:
        conversation: list[dict[str, object]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        conversation.extend(
            {
                "role": item["role"],
                "content": item["content"],
            }
            for item in history
        )
        conversation.append({"role": "user", "content": user_message})

        for _ in range(self.max_rounds):
            response = self.llm_client.complete(
                messages=conversation,
                tools=self.tool_service.list_tool_definitions(),
            )
            if response.tool_calls:
                conversation.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": tool_call.arguments,
                                },
                            }
                            for tool_call in response.tool_calls
                        ],
                    }
                )
                for tool_call in response.tool_calls:
                    arguments = self._parse_arguments(tool_call.arguments)
                    tool_result = self.tool_service.call_tool(tool_call.name, arguments)
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": tool_result,
                        }
                    )
                continue

            final_text = response.content.strip() or "No response returned."
            updated_history = list(history)
            updated_history.append({"role": "user", "content": user_message})
            updated_history.append({"role": "assistant", "content": final_text})
            return {
                "reply": final_text,
                "history": updated_history,
            }

        raise RuntimeError("Chat engine exceeded the maximum tool-calling rounds.")

    def _parse_arguments(self, raw_arguments: str) -> dict[str, str]:
        text = raw_arguments.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must decode to an object.")
        return {str(key): "" if value is None else str(value) for key, value in parsed.items()}
