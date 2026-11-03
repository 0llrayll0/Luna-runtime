from __future__ import annotations

from typing import Any

from luna.models.schema import Message


def _text_of(message: Any) -> str:
    if isinstance(message, Message):
        parts = [message.content or ""]
        for tc in (message.tool_calls or []):
            parts.append(str(tc.name))
            parts.append(str(tc.args))
        if message.tool_result is not None:
            parts.append(str(message.tool_result))
        return " ".join(parts)
    if isinstance(message, dict):
        parts = [str(message.get("content") or "")]
        for tc in message.get("tool_calls") or []:
            parts.append(str(tc))
        if message.get("tool_result") is not None:
            parts.append(str(message.get("tool_result")))
        return " ".join(parts)
    return str(message)


class ContextEngine:
    def __init__(self, default_budget_tokens: int = 8000, chars_per_token: int = 4) -> None:
        self.default_budget_tokens = int(default_budget_tokens)
        self.chars_per_token = int(chars_per_token)

    def estimate_tokens(self, text: Any) -> int:
        s = text if isinstance(text, str) else _text_of(text) if not isinstance(text, (list, tuple)) else " ".join(_text_of(m) for m in text)
        if not isinstance(s, str):
            s = str(s)
        if not s:
            return 0
        return max(1, len(s) // self.chars_per_token)

    def message_tokens(self, message: Any) -> int:
        if isinstance(message, (list, tuple)):
            return sum(self.message_tokens(m) for m in message)
        return self.estimate_tokens(_text_of(message))

    def _is_system(self, message: Any) -> bool:
        role = getattr(message, "role", None)
        if role is None and isinstance(message, dict):
            role = message.get("role")
        return role == "system"

    def select_context(self, messages: list[Any], budget_tokens: int | None = None) -> list[Any]:
        budget = int(budget_tokens if budget_tokens is not None else self.default_budget_tokens)
        msgs = list(messages or [])
        system = [m for m in msgs if self._is_system(m)]
        non_system = [m for m in msgs if not self._is_system(m)]

        # Keep the most recent non-system messages that fit the budget.
        selected_rev: list[Any] = []
        used = sum(self.message_tokens(m) for m in system)
        for m in reversed(non_system):
            mt = self.message_tokens(m)
            if used + mt <= budget or not selected_rev:
                selected_rev.append(m)
                used += mt
            else:
                break
        selected_non = list(reversed(selected_rev))
        return system + selected_non

    def compact(self, messages: list[Any], budget_tokens: int | None = None) -> int:
        budget = int(budget_tokens if budget_tokens is not None else self.default_budget_tokens)
        msgs = messages
        # Work on a shallow copy of indices; mutate in place.
        if self._total_tokens(msgs) <= budget:
            return 0
        # remove oldest non-system until fits (in blocks of 1, oldest first)
        removed = 0
        # identify removable indices
        while self._total_tokens(msgs) > budget:
            idx = self._oldest_non_system_index(msgs)
            if idx is None:
                break
            del msgs[idx]
            removed += 1
        if removed > 0:
            # insert a truncation placeholder after leading system messages
            insert_at = 0
            while insert_at < len(msgs) and self._is_system(msgs[insert_at]):
                insert_at += 1
            placeholder = Message(role="system", content=f"[Context compacted: {removed} older messages truncated]")
            msgs.insert(insert_at, placeholder)
        return removed

    def _total_tokens(self, messages: list[Any]) -> int:
        return sum(self.message_tokens(m) for m in messages)

    def _oldest_non_system_index(self, messages: list[Any]) -> int | None:
        for i, m in enumerate(messages):
            if not self._is_system(m):
                return i
        return None


__all__ = ["ContextEngine"]
