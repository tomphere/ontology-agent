# 对话路由（SSE 流式）
import json
import asyncio
import uuid
import sqlite3
import logging
import re
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ontology_intelligence.config import settings
from ontology_intelligence.web.models import ChatRequest, CreateSessionRequest, ChatScoreRequest
from ontology_intelligence.web.routes.auth import verify_token
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["chat"])
logger = logging.getLogger("web-platform")

SESSIONS_DIR = settings.project_root / "data" / "chat_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _get_db_conn():
    db_path = SESSIONS_DIR / "sessions_meta.db"
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT, messages TEXT, scene_id TEXT
    )''')
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN scene_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def _load_session(session_id: str) -> dict:
    conn = _get_db_conn()
    cur = conn.execute("SELECT id, title, created_at, updated_at, messages, scene_id FROM sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3],
            "scene_id": row[5],
            "messages": json.loads(row[4]) if row[4] else []}


def _load_session_or_none(session_id: str) -> Optional[dict]:
    try:
        return _load_session(session_id)
    except HTTPException as e:
        if e.status_code == 404:
            return None
        raise


def _save_session(session_id: str, data: dict):
    conn = _get_db_conn()
    conn.execute('''INSERT INTO sessions (id, title, created_at, updated_at, messages, scene_id) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at, messages=excluded.messages, scene_id=excluded.scene_id''',
        (session_id, data.get("title", "新对话"), data.get("created_at", ""),
         data.get("updated_at", ""), json.dumps(data.get("messages", []), ensure_ascii=False),
         data.get("scene_id")))
    conn.commit()
    conn.close()


def _find_session_by_trace_id(trace_id: str):
    conn = _get_db_conn()
    cur = conn.execute("SELECT id, title, created_at, updated_at, messages, scene_id FROM sessions")
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        messages = json.loads(row[4]) if row[4] else []
        for idx, msg in enumerate(messages):
            if msg.get("langfuse_trace_id") == trace_id:
                return {
                    "session": {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "scene_id": row[5],
                        "messages": messages,
                    },
                    "message_index": idx,
                }
    return None


def _extract_langfuse_trace_id(handler) -> Optional[str]:
    for attr in ("trace_id", "root_trace_id", "last_trace_id", "id"):
        value = getattr(handler, attr, None)
        if value:
            return str(value)
    trace = getattr(handler, "trace", None)
    if trace is not None:
        for attr in ("id", "trace_id"):
            value = getattr(trace, attr, None)
            if value:
                return str(value)
    return None


def _get_langfuse_client():
    try:
        from langfuse import Langfuse
    except Exception:
        return None

    try:
        client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
    except Exception as e:
        logger.warning(f"Langfuse client disabled: {e}")
        return None

    try:
        from langfuse import get_client
        return get_client()
    except Exception:
        return client


def _create_langfuse_callback():
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:
        pass

    try:
        from langfuse.callback import CallbackHandler
    except Exception as e:
        logger.warning(f"Langfuse callback import failed: {e}")
        return None

    for kwargs in (
        {
            "secret_key": settings.langfuse_secret_key,
            "public_key": settings.langfuse_public_key,
            "host": settings.langfuse_host,
        },
        {},
    ):
        try:
            return CallbackHandler(**kwargs)
        except Exception:
            continue
    return None


def _create_langfuse_trace_id(seed: str = None) -> str:
    try:
        from langfuse import Langfuse
        factory = getattr(Langfuse, "create_trace_id", None)
        if callable(factory):
            return factory(seed=seed) if seed else factory()
    except Exception:
        pass

    client = _get_langfuse_client()
    if client:
        factory = getattr(client, "create_trace_id", None)
        if callable(factory):
            try:
                return factory(seed=seed) if seed else factory()
            except Exception:
                pass
    return uuid.uuid4().hex


@contextmanager
def _langfuse_trace_context(trace_id: str, session_id: str, username: str, scene_id: str, message: str):
    client = _get_langfuse_client()
    if not client:
        yield None
        return

    tags = ["agent_chat", f"scene:{scene_id or 'global'}"]
    trace_context = {"trace_id": trace_id} if trace_id else None
    trace_input = {"message": message, "scene_id": scene_id or "global"}

    try:
        from langfuse import propagate_attributes
    except Exception:
        propagate_attributes = None

    attr_ctx = nullcontext()
    if callable(propagate_attributes):
        try:
            attr_ctx = propagate_attributes(
                user_id=username,
                session_id=session_id,
                tags=tags,
                metadata={"scene_id": scene_id or "global"},
            )
        except Exception:
            attr_ctx = nullcontext()

    start_observation = getattr(client, "start_as_current_observation", None)
    if callable(start_observation):
        try:
            observation_kwargs = {
                "as_type": "span",
                "name": "ontology-agent-chat",
                "trace_context": trace_context,
                "input": trace_input,
            }
            try:
                observation_ctx = start_observation(**observation_kwargs)
            except TypeError:
                observation_kwargs.pop("input", None)
                observation_ctx = start_observation(**observation_kwargs)

            with observation_ctx as observation:
                update = getattr(observation, "update", None)
                if callable(update):
                    try:
                        update(input=trace_input)
                    except TypeError:
                        pass
                set_trace_io = getattr(observation, "set_trace_io", None)
                if callable(set_trace_io):
                    set_trace_io(input=trace_input)
                with attr_ctx:
                    yield observation
            return
        except Exception as e:
            logger.warning(f"Langfuse trace context disabled: {e}")

    trace = getattr(client, "trace", None)
    if callable(trace):
        try:
            trace(
                id=trace_id,
                name="ontology-agent-chat",
                user_id=username,
                session_id=session_id,
                input=trace_input,
                tags=tags,
                metadata={"scene_id": scene_id or "global"},
            )
        except Exception as e:
            logger.warning(f"Langfuse legacy trace create failed: {e}")

    yield None


def _update_langfuse_observation(observation, *, input=None, output=None, metadata=None):
    if observation is None:
        return
    try:
        set_trace_io = getattr(observation, "set_trace_io", None)
        if callable(set_trace_io) and (input is not None or output is not None):
            trace_io = {}
            if input is not None:
                trace_io["input"] = input
            if output is not None:
                trace_io["output"] = output
            set_trace_io(**trace_io)
        update = getattr(observation, "update", None)
        if callable(update):
            kwargs = {}
            if input is not None:
                kwargs["input"] = input
            if output is not None:
                kwargs["output"] = output
            if metadata is not None:
                kwargs["metadata"] = metadata
            if kwargs:
                update(**kwargs)
    except Exception as e:
        logger.warning(f"Langfuse observation update failed: {e}")


def _flush_langfuse(handler=None):
    flushed = False
    if handler:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            try:
                flush()
                flushed = True
            except Exception as e:
                logger.error(f"Langfuse handler flush error: {e}")
    client = _get_langfuse_client()
    flush = getattr(client, "flush", None) if client else None
    if callable(flush):
        try:
            flush()
            flushed = True
        except Exception as e:
            logger.error(f"Langfuse client flush error: {e}")
    return flushed


def _parse_tool_result_payload(content: str) -> Optional[dict]:
    """Parse structured ontology-agent tool payloads, falling back to legacy text."""
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except Exception:
        return None
    if isinstance(data, dict) and data.get("__oi_result__"):
        return data
    return None


def _format_tool_result_step_content(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""

    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    answer = (payload.get("content") or "").strip()
    lines = []

    cypher = evidence.get("cypher") or evidence.get("query")
    if cypher:
        lines.append(f"生成 Cypher:\n{cypher}")

    metric_parts = []
    if evidence.get("generate_ms") is not None:
        metric_parts.append(f"Cypher 生成 {evidence.get('generate_ms')}ms")
    if evidence.get("elapsed_ms") is not None:
        metric_parts.append(f"图数据库查询 {evidence.get('elapsed_ms')}ms")
    if evidence.get("total_ms") is not None:
        metric_parts.append(f"工具总耗时 {evidence.get('total_ms')}ms")
    if evidence.get("fast_path") is not None:
        metric_parts.append(f"快速路径 {'是' if evidence.get('fast_path') else '否'}")
    if metric_parts:
        lines.append("执行指标: " + "；".join(metric_parts))

    if answer:
        lines.append("结果预览:\n" + answer[:3000])

    rows = artifact.get("rows") or artifact.get("data") or []
    columns = artifact.get("columns") or []
    if columns:
        lines.append("结果列: " + "，".join(str(col) for col in columns))
    if rows:
        sample_rows = rows[:5] if isinstance(rows, list) else []
        if sample_rows:
            lines.append("结果样例:\n" + json.dumps(sample_rows, ensure_ascii=False, default=str, indent=2))

    return "\n\n".join(lines)[:8000]


def _stabilize_agent_message(message: str) -> str:
    """Make terse Chinese lookup questions less brittle for OpenAI-compatible tool calling."""
    text = (message or "").strip()
    if not text:
        return text
    normalized = re.sub(r"[？?。！!；;，,\s]+$", "", text)
    if len(normalized) <= 24 and re.search(r"(是谁|是什么|有哪些|多少|关系|关联|在哪里|在哪儿)$", normalized):
        if not re.match(r"^(请|帮|查询|查一下|请查询|请帮我|我想)", text):
            return f"请查询并回答：{text}"
    return text


@router.get("/chat/sessions")
async def list_sessions(username: str = Depends(verify_token)):
    conn = _get_db_conn()
    cur = conn.execute("SELECT id, title, created_at, updated_at, messages, scene_id FROM sessions ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()
    return {"sessions": [
        {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3],
         "scene_id": r[5],
         "message_count": len(json.loads(r[4]) if r[4] else [])}
        for r in rows
    ]}


@router.post("/chat/sessions")
async def create_session(req: CreateSessionRequest = None, username: str = Depends(verify_token)):
    sid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    data = {
        "id": sid,
        "title": req.title if req else "新对话",
        "scene_id": req.scene_id if req else None,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save_session(sid, data)
    return data


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str, username: str = Depends(verify_token)):
    return _load_session(session_id)


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, username: str = Depends(verify_token)):
    conn = _get_db_conn()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.put("/chat/sessions/{session_id}/title")
async def rename_session(session_id: str, req: CreateSessionRequest, username: str = Depends(verify_token)):
    data = _load_session(session_id)
    data["title"] = req.title
    data["updated_at"] = datetime.now().isoformat()
    _save_session(session_id, data)
    return {"status": "success"}


@router.get("/chat/sessions/{session_id}/export")
async def export_session(session_id: str, username: str = Depends(verify_token)):
    from fastapi.responses import PlainTextResponse
    data = _load_session(session_id)
    md = [f"# {data.get('title', '对话导出')}\n", f"**创建时间**: {data.get('created_at', 'N/A')}\n", "---\n"]
    for msg in data.get("messages", []):
        if msg["role"] == "user":
            md.append(f"## 🧑 用户\n\n{msg['content']}\n")
        else:
            md.append(f"## 🤖 智能体\n\n{msg.get('content', '')}\n")
        md.append("---\n")
    return PlainTextResponse("\n".join(md), media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=chat_{session_id}.md"})


@router.post("/chat/sessions/{session_or_trace_id}/score")
async def score_session(session_or_trace_id: str, req: ChatScoreRequest, username: str = Depends(verify_token)):
    target = None
    try:
        session = _load_session(session_or_trace_id)
        target = {"session": session, "message_index": None}
    except Exception:
        target = _find_session_by_trace_id(session_or_trace_id)

    if not target:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="会话或 Trace 不存在")

    score = {
        "score_name": req.score_name,
        "value": req.value,
        "comment": req.comment or "",
        "created_at": datetime.now().isoformat(),
        "created_by": username,
        "trace_id": session_or_trace_id,
    }
    data = target["session"]
    msg_idx = target.get("message_index")
    if msg_idx is None:
        data.setdefault("scores", []).append(score)
    else:
        data["messages"][msg_idx].setdefault("scores", []).append(score)
    data["updated_at"] = datetime.now().isoformat()
    _save_session(data["id"], data)

    langfuse_status = "skipped"
    if settings.langfuse_enabled:
        try:
            client = _get_langfuse_client()
            if client is None:
                raise RuntimeError("Langfuse client unavailable")
            score_kwargs = {
                "trace_id": session_or_trace_id,
                "name": req.score_name,
                "value": req.value,
                "comment": req.comment or None,
            }
            if hasattr(client, "score"):
                client.score(**score_kwargs)
            else:
                client.create_score(**score_kwargs)
            _flush_langfuse()
            langfuse_status = "success"
        except Exception as e:
            langfuse_status = f"failed: {e}"

    audit_event(username, "chat.score", trace_id=session_or_trace_id, score_name=req.score_name, value=req.value, langfuse_status=langfuse_status)
    return {"status": "success", "score": score, "langfuse_status": langfuse_status}


@router.post("/chat")
async def chat_stream_endpoint(req: ChatRequest, username: str = Depends(verify_token)):
    session_id = req.session_id
    scene_id = req.scene_id
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    
    session_data = _load_session_or_none(session_id)
    if session_data is None:
        now = datetime.now().isoformat()
        _save_session(session_id, {
            "id": session_id,
            "title": req.message[:30],
            "scene_id": scene_id,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        })

    async def event_generator():
        request_started_at = time.perf_counter()
        try:
            yield f"data: {json.dumps({'type': 'session_id', 'content': session_id}, ensure_ascii=False)}\n\n"
            from ontology_intelligence.web.app import executor
            from ontology_intelligence.web.routes.agent import _init_agent, _get_agent_state

            agent_state = _get_agent_state(scene_id)
            if not agent_state["initialized"]:
                init_msg = '正在初始化场景智能体...' if scene_id else '正在初始化智能体...'
                yield f"data: {json.dumps({'type': 'status', 'content': init_msg}, ensure_ascii=False)}\n\n"
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, lambda: _init_agent(scene_id))

            agent = agent_state["agent"]
            thread_id = f"{scene_id}:{session_id}" if scene_id else session_id
            langfuse_handler = None
            langfuse_trace_id = None
            langfuse_tags = ["agent_chat", f"scene:{scene_id or 'global'}"]
            
            from langchain_core.callbacks import BaseCallbackHandler
            
            # Forward declaration so handler can capture loop/queue which are initialized below
            class StreamCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue, loop):
                    self.queue = queue
                    self.loop = loop
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    import asyncio
                    asyncio.run_coroutine_threadsafe(self.queue.put({"type": "token", "content": token}), self.loop)

            loop = asyncio.get_event_loop()
            queue = asyncio.Queue()
            
            callbacks = [StreamCallbackHandler(queue, loop)]
            
            if settings.langfuse_enabled:
                try:
                    langfuse_trace_id = _create_langfuse_trace_id(
                        f"{scene_id or 'global'}:{session_id}:{uuid.uuid4().hex}"
                    )
                    langfuse_handler = _create_langfuse_callback()
                    if langfuse_handler:
                        callbacks.append(langfuse_handler)
                    else:
                        langfuse_trace_id = None
                except Exception as e:
                    logger.warning(f"Langfuse callback disabled: {e}")
                    langfuse_trace_id = None

            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 20,
                "callbacks": callbacks,
                "metadata": {
                    "langfuse_user_id": username,
                    "langfuse_session_id": session_id,
                    "langfuse_tags": langfuse_tags,
                    "langfuse_trace_id": langfuse_trace_id,
                    "scene_id": scene_id or "global",
                    "chat_session_id": session_id,
                },
                "tags": langfuse_tags,
                "run_name": "ontology-agent-chat",
            }

            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 分析中...', 'elapsed_ms': int((time.perf_counter() - request_started_at) * 1000)}, ensure_ascii=False)}\n\n"
            collected_steps = []
            seen_steps = set()
            final_artifacts = []
            final_evidence = None
            final_answer = ""
            final_metrics = {}
            agent_message = _stabilize_agent_message(req.message)
            if agent_message != req.message:
                logger.info(
                    "[ChatInput] stabilized terse query scene_id=%s session_id=%s original_len=%s stabilized_len=%s",
                    scene_id or "global",
                    session_id,
                    len(req.message or ""),
                    len(agent_message),
                )

            def _run():
                nonlocal final_answer, final_evidence, final_metrics
                stream_started_at = time.perf_counter()
                pending_tool_calls = {}

                def emit_step(step: dict):
                    step.setdefault("elapsed_ms", int((time.perf_counter() - request_started_at) * 1000))
                    key = json.dumps(step, ensure_ascii=False, sort_keys=True)
                    if key in seen_steps:
                        return
                    seen_steps.add(key)
                    collected_steps.append(step)
                    asyncio.run_coroutine_threadsafe(queue.put(step), loop)

                try:
                    try:
                        current_state = agent.get_state(config)
                        processed = len(current_state.values.get("messages", [])) if current_state and hasattr(current_state, 'values') else 0
                    except Exception:
                        processed = 0

                    trace_ctx = _langfuse_trace_context(
                        langfuse_trace_id,
                        session_id,
                        username,
                        scene_id,
                        req.message,
                    ) if langfuse_trace_id else nullcontext()
                    with trace_ctx as observation:
                        for event in agent.stream(
                            {"messages": [{"role": "user", "content": agent_message}]},
                            config=config, stream_mode="values",
                        ):
                            if "messages" in event:
                                msgs = event["messages"]
                                for msg in msgs[processed:]:
                                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                        for tc in msg.tool_calls:
                                            tool_call_id = tc.get("id") or tc.get("name", "")
                                            pending_tool_calls[tool_call_id] = time.perf_counter()
                                            step = {
                                                "type": "tool_call",
                                                "tool": tc.get("name", ""),
                                                "input": str(tc.get("args", ""))[:500],
                                            }
                                            emit_step(step)
                                    if hasattr(msg, 'type') and msg.type == 'tool':
                                        tool_name = getattr(msg, 'name', '')
                                        tool_call_id = getattr(msg, 'tool_call_id', None) or tool_name
                                        started_at = pending_tool_calls.pop(tool_call_id, None)
                                        duration_ms = int((time.perf_counter() - started_at) * 1000) if started_at is not None else None
                                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                                        payload = _parse_tool_result_payload(content)
                                        if payload:
                                            answer = payload.get("content") or ""
                                            artifact = payload.get("artifact")
                                            evidence = payload.get("evidence")
                                            row_count = evidence.get("row_count") if isinstance(evidence, dict) else None
                                            summary = f"已返回结构化查询结果"
                                            if row_count is not None:
                                                summary += f"（{row_count} 条）"
                                            detail = _format_tool_result_step_content(payload)
                                            step = {
                                                "type": "tool_result",
                                                "tool": tool_name,
                                                "content": f"{summary}\n\n{detail}" if detail else summary,
                                            }
                                            if duration_ms is not None:
                                                step["duration_ms"] = duration_ms
                                            emit_step(step)
                                            if artifact:
                                                final_artifacts.append(artifact)
                                                asyncio.run_coroutine_threadsafe(queue.put({"type": "artifact", "content": artifact}), loop)
                                            if evidence:
                                                final_evidence = evidence
                                                asyncio.run_coroutine_threadsafe(queue.put({"type": "query_evidence", "content": evidence}), loop)
                                            # REMOVED the early final_answer emission here so the LLM gets to summarize it
                                        else:
                                            step = {"type": "tool_result", "tool": tool_name, "content": content[:2000]}
                                            if duration_ms is not None:
                                                step["duration_ms"] = duration_ms
                                            emit_step(step)
                                            if tool_name == 'Knowledge_Graph_Query' and content and not final_answer:
                                                final_answer = content
                                                asyncio.run_coroutine_threadsafe(queue.put({"type": "answer", "content": content}), loop)
                                processed = len(msgs)
                                last_msg = msgs[-1]
                                if hasattr(last_msg, 'content') and last_msg.content and getattr(last_msg, 'type', '') == 'ai':
                                    raw = last_msg.content
                                    if isinstance(raw, list):
                                        text = ''.join(item.get('text', '') if isinstance(item, dict) else str(item)
                                                       for item in raw if not isinstance(item, dict) or item.get('type') == 'text').strip()
                                    else:
                                        text = raw
                                    if text and not (hasattr(last_msg, 'tool_calls') and last_msg.tool_calls):
                                        final_answer = text
                                        asyncio.run_coroutine_threadsafe(queue.put({"type": "answer", "content": text}), loop)
                        _update_langfuse_observation(
                            observation,
                            input={"message": req.message, "scene_id": scene_id or "global"},
                            output={"answer": final_answer},
                            metadata={
                                "scene_id": scene_id or "global",
                                "step_count": len(collected_steps),
                                "steps": collected_steps[:50],
                                "has_evidence": bool(final_evidence),
                                "evidence": final_evidence,
                                "artifact_count": len(final_artifacts),
                            },
                        )
                    if langfuse_handler:
                        trace_id = langfuse_trace_id or _extract_langfuse_trace_id(langfuse_handler) or thread_id
                        asyncio.run_coroutine_threadsafe(queue.put({"type": "langfuse_trace_id", "content": trace_id}), loop)
                    elapsed_ms = int((time.perf_counter() - stream_started_at) * 1000)
                    final_metrics["agent_ms"] = elapsed_ms
                    logger.info(
                        "[ChatTiming] agent_stream scene_id=%s session_id=%s elapsed_ms=%s steps=%s answered=%s",
                        scene_id or "global",
                        session_id,
                        elapsed_ms,
                        len(collected_steps),
                        bool(final_answer),
                    )
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                except Exception as e:
                    error_msg = str(e)
                    logger.exception(
                        "[ChatTiming] agent_stream failed scene_id=%s session_id=%s error=%s",
                        scene_id or "global",
                        session_id,
                        error_msg,
                    )
                    
                    # 针对常见的 OpenAI 兼容服务商错误进行友好化处理
                    if "No generations found in stream" in error_msg:
                        error_msg = "智能体响应异常：模型输出为空。这通常是由于 LLM 服务商对复杂 Prompt 或工具调用的流式输出支持不稳定导致的。建议尝试：1. 刷新页面重试；2. 在设置中更换性能更强的模型（如 GPT-4, Claude 3, Qwen-Max）。"
                    elif "timeout" in error_msg.lower():
                        error_msg = "请求超时：LLM 服务响应过慢。请检查网络连接或稍后再试。"

                    asyncio.run_coroutine_threadsafe(queue.put({"type": "error", "content": error_msg}), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

            loop.run_in_executor(executor, _run)
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'content': '超时'}, ensure_ascii=False)}\n\n"
                    break
                if item is None:
                    total_ms = int((time.perf_counter() - request_started_at) * 1000)
                    final_metrics.update({
                        "total_ms": total_ms,
                        "step_count": len(collected_steps),
                    })
                    try:
                        if langfuse_handler:
                            langfuse_trace_id = langfuse_trace_id or _extract_langfuse_trace_id(langfuse_handler) or thread_id
                        sd = _load_session(session_id)
                        sd["scene_id"] = scene_id or sd.get("scene_id")
                        sd["messages"].append({
                            "role": "user",
                            "content": req.message,
                            "scene_id": scene_id,
                            "timestamp": datetime.now().isoformat(),
                        })
                        sd["messages"].append({
                            "role": "agent",
                            "content": final_answer,
                            "steps": collected_steps,
                            "artifacts": final_artifacts,
                            "evidence": final_evidence,
                            "metrics": final_metrics,
                            "langfuse_trace_id": langfuse_trace_id,
                            "scene_id": scene_id,
                            "timestamp": datetime.now().isoformat(),
                        })
                        sd["updated_at"] = datetime.now().isoformat()
                        if sd["title"] in ("新对话", req.message[:30]):
                            sd["title"] = req.message[:30]
                        _save_session(session_id, sd)
                        audit_event(
                            username,
                            "chat.message",
                            scene_id=scene_id,
                            session_id=session_id,
                            step_count=len(collected_steps),
                            elapsed_ms=total_ms,
                            answered=bool(final_answer),
                        )
                    except Exception as ex:
                        logger.error(f"保存会话失败: {ex}")
                    logger.info(
                        "[ChatTiming] request_done scene_id=%s session_id=%s elapsed_ms=%s",
                        scene_id or "global",
                        session_id,
                        total_ms,
                    )
                    if langfuse_handler:
                        _flush_langfuse(langfuse_handler)
                    yield f"data: {json.dumps({'type': 'metrics', 'content': final_metrics}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except Exception as e:
            if 'langfuse_handler' in locals() and langfuse_handler:
                _flush_langfuse(langfuse_handler)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
