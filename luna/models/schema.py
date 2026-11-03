from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


class ToolCall(BaseModel):
    id: str = ""
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: str
    content: str | None = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: Any = None


class CompletionRequest(BaseModel):
    model: str
    messages: list[Message] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str | None = None
    model: str
    provider: str

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens


class StreamChunk(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None
    provider: str | None = None
    usage: Usage | None = None
    done: bool = False


__all__ = [
    "Usage",
    "ToolCall",
    "Message",
    "CompletionRequest",
    "CompletionResponse",
    "StreamChunk",
]