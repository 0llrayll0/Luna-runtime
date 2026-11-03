from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    agent_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    metadata_json = Column(Text, default="{}")

    def to_dict(self) -> dict:
        try:
            metadata = json.loads(self.metadata_json or "{}")
        except Exception:
            metadata = {}
        return {"id": self.id, "agent_name": self.agent_name, "created_at": self.created_at, "updated_at": self.updated_at, "metadata": metadata}


class MessageRecord(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, default="")
    tool_calls_json = Column(Text, default="[]")
    tool_result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    def tool_calls(self):
        try:
            return json.loads(self.tool_calls_json or "[]")
        except Exception:
            return []

    def tool_result(self):
        if self.tool_result_json is None:
            return None
        try:
            return json.loads(self.tool_result_json)
        except Exception:
            return self.tool_result_json


__all__ = ["Base", "SessionRecord", "MessageRecord"]
