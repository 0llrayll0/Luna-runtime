from __future__ import annotations

import json
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from luna.models.schema import Message, ToolCall
from luna.sessions.models import Base, MessageRecord, SessionRecord


def _coerce_message(message: Any) -> Message:
    if isinstance(message, Message):
        return message
    if isinstance(message, dict):
        tc = []
        for item in (message.get("tool_calls") or []):
            if isinstance(item, ToolCall):
                tc.append(item)
            elif isinstance(item, dict):
                tc.append(ToolCall(**item))
        return Message(
            role=message.get("role", "user"),
            content=message.get("content", "") or "",
            tool_calls=tc,
            tool_result=message.get("tool_result"),
        )
    return Message(role="user", content=str(message))


class SessionManager:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///:memory:", echo: bool = False) -> None:
        self.db_url = db_url
        # ensure parent dir for file sqlite
        if db_url.startswith("sqlite+aiosqlite:///") and not db_url.endswith(":memory:"):
            path = db_url[len("sqlite+aiosqlite:///"):]
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(db_url, echo=echo)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._initialized = True

    async def create_session(
        self,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        await self.init()
        sid = session_id or str(uuid.uuid4())
        async with self.session_factory() as session:
            existing = await session.get(SessionRecord, sid)
            if existing is None:
                record = SessionRecord(
                    id=sid,
                    agent_name=agent_name,
                    metadata_json=json.dumps(metadata or {}),
                )
                session.add(record)
                await session.commit()
        return sid

    async def get_session(self, session_id: str) -> SessionRecord | None:
        await self.init()
        async with self.session_factory() as session:
            record = await session.get(SessionRecord, session_id)
            if record is None:
                return None
            # detach by returning copy attributes
            return record

    async def append_message(
        self,
        session_id: str,
        message: Any = None,
        *,
        role: str | None = None,
        content: str | None = None,
        tool_calls: list[Any] | None = None,
        tool_result: Any = None,
        **kwargs: Any,
    ) -> None:
        await self.init()
        await self.create_session(session_id=session_id)
        msg = _coerce_message(message) if message is not None and role is None and content is None and tool_calls is None and tool_result is None else Message(
            role=role or (message.role if isinstance(message, Message) else "user"),
            content=content if content is not None else (message.content if isinstance(message, Message) else str(message or "")),
            tool_calls=tool_calls if tool_calls is not None else (message.tool_calls if isinstance(message, Message) else []),
            tool_result=tool_result if tool_result is not None else (message.tool_result if isinstance(message, Message) else None),
        )
        tc_json = json.dumps([ (tc.model_dump() if hasattr(tc, "model_dump") else tc) for tc in (msg.tool_calls or []) ])
        tr_json = None if msg.tool_result is None else json.dumps(msg.tool_result, default=str)
        async with self.session_factory() as session:
            record = MessageRecord(
                session_id=session_id,
                role=msg.role,
                content=msg.content or "",
                tool_calls_json=tc_json,
                tool_result_json=tr_json,
            )
            session.add(record)
            # update session timestamp
            srec = await session.get(SessionRecord, session_id)
            if srec is not None:
                srec.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            await session.commit()

    async def get_messages(self, session_id: str) -> list[Message]:
        await self.init()
        await self.create_session(session_id=session_id)
        async with self.session_factory() as session:
            stmt = select(MessageRecord).where(MessageRecord.session_id == session_id).order_by(MessageRecord.id)
            rows = (await session.execute(stmt)).scalars().all()
            out: list[Message] = []
            for r in rows:
                tc_raw = r.tool_calls()
                tool_calls = []
                for item in tc_raw:
                    if isinstance(item, dict):
                        tool_calls.append(ToolCall(**item))
                    else:
                        tool_calls.append(ToolCall(name=str(item)))
                tr = r.tool_result()
                out.append(Message(role=r.role, content=r.content or "", tool_calls=tool_calls, tool_result=tr))
            return out

    async def list_sessions(self) -> list[SessionRecord]:
        await self.init()
        async with self.session_factory() as session:
            stmt = select(SessionRecord).order_by(SessionRecord.created_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)


__all__ = ["SessionManager", "SessionRecord", "MessageRecord"]
