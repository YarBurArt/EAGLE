"""
hot state of mythic tasks and payloads in redis,
statuses and events live here only as current state,
db keeps the durable record and is used for recovery
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis
from sqlalchemy import select

from app.cmd.llm_analysis import llm_service
from app.core.config import get_settings
from app.core.database_session import get_async_session
from app.models import AttackStep, MythicTask

if TYPE_CHECKING:
    from app.cmd.c2_tool import MythicClient

logger = logging.getLogger(__name__)

TERMINAL = ("completed", "error", "finished", "cancelled")
TASK_EVENTS_ATTRS = "id display_id status completed"
# how long a step stream stays open with no fresh events before closing
STREAM_IDLE_SEC = 90
# gr a terminal status may still be followed by output & analysis
STREAM_GRACE_SEC = 20
# one xread block, low value just makes tests fast
STREAM_BLOCK_MS = 15_000


def _row_now() -> str:
    return datetime.now(UTC).isoformat()


def _snap(kind: str, **fields) -> dict:
    """one redis stream row, ndjson like frontend gets"""
    return {"event": kind, "at": _row_now(), **fields}


def _encode(snap: dict) -> dict:
    """streams store field/value dicts, single data field with ndjson inside"""
    return {"data": json.dumps(snap)}


def _decode(raw) -> str:
    """back from redis row to ndjson string"""
    if isinstance(raw, dict):
        return str(raw.get("data", ""))
    return str(raw)


class MythicEventsService:
    """single mythic subscription -> redis -> sse & mcp consumers"""

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._sub_task: asyncio.Task | None = None
        self._mythic_client: MythicClient | None = None
        self._watchers: set[asyncio.Task] = set()
        self.available = False

    @property
    def _instance(self):
        if self._mythic_client is not None:
            return self._mythic_client.instance
        return None

    def bind_client(self, mythic_client: MythicClient) -> None:
        """reuse the same mythic websocket instance as c2_tool"""
        self._mythic_client = mythic_client

    @property
    def _mythic_cfg(self) -> dict[str, Any]:
        c = get_settings().mythic
        return {
            "username": c.username,
            "password": c.password.get_secret_value(),
            "server_ip": c.server_ip,
            "server_port": c.server_port,
            "timeout": -1,
        }

    async def start(self) -> None:
        """connect redis, then subscribe to mythic, recovery is done by
        mythic replay + db, so no redis persistence is needed"""
        cfg = get_settings().redis
        self._redis = redis.Redis(
            host=cfg.hostname,
            port=cfg.port,
            password=cfg.password.get_secret_value(),
            decode_responses=True,
        )
        try:
            await self._redis.ping()
        except Exception as e:
            logger.warning("redis is not available, events live in logs only: %s", e)
            return
        self.available = True
        self._sub_task = asyncio.create_task(self._subscribe_loop())
        self._spawn(self._recover_stale())

    async def stop(self) -> None:
        if self._sub_task:
            self._sub_task.cancel()
        for t in tuple(self._watchers):
            t.cancel()
        if self._redis:
            await self._redis.aclose()

    @staticmethod
    def task_key(mythic_task_id: int) -> str:
        return f"eagle:task:{mythic_task_id}"

    @staticmethod
    def payload_key(payload_uuid: str) -> str:
        return f"eagle:payload:{payload_uuid}"

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._watchers.add(t)
        t.add_done_callback(self._watchers.discard)
        return t

    async def _subscribe_loop(self) -> None:
        """one mythic task subscription, resubscribe on any failure"""
        from mythic import mythic  # noqa: PLC0415

        instance = None
        while True:
            try:
                if instance is None:
                    instance = self._instance or await mythic.login(**self._mythic_cfg)
                async for task in mythic.subscribe_all_tasks_and_updates(
                    mythic=instance, custom_return_attributes=TASK_EVENTS_ATTRS
                ):
                    await self._on_task_event(task)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                instance = None
                logger.warning("task subscription failed, retry in 5s: %s", e)
                await asyncio.sleep(5)

    async def _recover_stale(self) -> None:
        """tickets left in db by a dead process get a redis row again,
        so sse consumers do not hang on expired keys"""
        if not self.available:
            return
        try:
            async with get_async_session() as session:
                rows = await session.execute(
                    select(MythicTask).where(MythicTask.status == "submitted")
                )
                task_ids = [r.mythic_task_id for r in rows.scalars()]
        except Exception as e:
            # db is another process, events service itself must not die for it
            logger.warning("stale ticket recovery skipped: %s", e)
            return
        for task_id in task_ids:
            await self._emit_task(task_id, "submitted", completed=False)
        logger.info("recovered %s stale tickets into redis", len(task_ids))

    async def _on_task_event(self, task: dict) -> None:
        task_id = task.get("display_id")
        if task_id is None:
            return
        status = str(task.get("status") or "submitted").lower()
        terminal = bool(task.get("completed")) or status in TERMINAL
        await self._emit_task(task_id, status, completed=terminal)
        if terminal:
            self._spawn(self._collect_output(int(task_id), status))

    async def _write_state(self, stream_key: str, status: str, snap: dict) -> None:
        """write one status row to the stream & hash, ttl like the contract"""
        if not self.available:
            return
        hash_key = stream_key.removesuffix(":events")
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.xadd(stream_key, _encode(snap))
            pipe.hset(hash_key, mapping={"status": status})
            ttl = get_settings().redis.events_ttl
            pipe.expire(hash_key, ttl)
            pipe.expire(stream_key, ttl)
            await pipe.execute()

    async def _emit_task(
        self, task_id: int, status: str, completed: bool = False
    ) -> None:
        k = self.task_key(task_id)
        await self._write_state(
            f"{k}:events",
            status,
            _snap("status", task_id=task_id, status=status, completed=completed),
        )

    async def _collect_output(
        self, task_id: int, event_status: str = "completed"
    ) -> None:
        """after terminal, aggregate output and save to db,
        llm analysis if the ticket was asked for it at run time"""
        from mythic import mythic  # noqa: PLC0415

        try:
            instance = self._instance or await mythic.login(**self._mythic_cfg)
            output = await mythic.waitfor_for_task_output(
                mythic=instance, task_display_id=task_id
            )
            text_out = str(output)
            auto_analyze, status, step_id = await self._persist_output(
                task_id, text_out, event_status
            )
            # always, even for tasks created outside our ticket flow
            await self._write_state(
                f"{self.task_key(task_id)}:events",
                status,
                _snap("output", task_id=task_id, raw_log=text_out, step_id=step_id),
            )
            if auto_analyze and step_id is not None:
                self._spawn(self._auto_analyze(task_id, step_id, text_out))
        except Exception as e:  # general exception cuz mythic lib
            logger.warning("output collection for task %s failed: %s", task_id, e)

    async def _persist_output(
        self, task_id: int, output: str, event_status: str = "completed"
    ) -> tuple[bool, str, int | None]:
        """save final state & output to mythic_task and attack_step durable"""
        auto_analyze, final_status, step_id = False, "completed", None
        async with get_async_session() as session:
            row = await session.scalar(
                select(MythicTask).where(MythicTask.mythic_task_id == task_id)
            )
            if row is None:
                # task not created here (like custom flows), keep it in redis only
                return False, event_status or "completed", None
            auto_analyze = row.auto_analyze
            failed = event_status in ("error", "cancelled")
            final_status = "failed" if failed else "completed"
            row.status = final_status
            row.output = output
            row.completed_at = datetime.now(UTC)
            if row.step_id:
                step_id = row.step_id
                step = await session.scalar(
                    select(AttackStep).where(AttackStep.id == row.step_id)
                )
                if step is not None:
                    step.raw_log = output
                    step.status = "fail" if failed else "success"
            await session.commit()
        return auto_analyze, final_status, step_id

    async def _auto_analyze(self, task_id: int, step_id: int, output: str) -> None:
        """run llm analysis on step output, save & emit like the others,
        only when the caller asked for it at submission time"""
        analysis = ""
        try:
            analysis = await llm_service.query_llm(
                f"command:\noutput: {output}\n"
                "analyze results and find most important things."
            )
        except Exception as e:
            analysis = f"error while analysis LLM: {str(e)}"
        await self._persist_analysis(step_id, analysis)
        await self._redis.xadd(
            f"{self.task_key(task_id)}:events",
            _encode(
                _snap(
                    "analysis", task_id=task_id, step_id=step_id, llm_analysis=analysis
                )
            ),
        )

    async def _persist_analysis(self, step_id: int, analysis: str) -> None:
        async with get_async_session() as session:
            step = await session.scalar(
                select(AttackStep).where(AttackStep.id == step_id)
            )
            if step is None:
                return
            step.llm_analysis = analysis
            await session.commit()

    async def emit_analysis(self, step_id: int, analysis: str) -> None:
        """mirror llm analysis to all task streams of the step"""
        if not self.available:
            return
        keys = await self._task_keys_for_step(step_id)
        raw = _encode(_snap("analysis", step_id=step_id, llm_analysis=analysis))
        for key in keys:
            await self._redis.xadd(key, raw)

    async def watch_payload(self, payload_uuid: str) -> None:
        """background payload build watcher, statuses go to redis & db"""
        self._spawn(self._payload_watch_loop(payload_uuid))

    async def _payload_watch_loop(self, payload_uuid: str) -> None:
        from mythic import mythic  # noqa: PLC0415

        try:
            instance = self._instance or await mythic.login(**self._mythic_cfg)
            # subscription waits until build_phase != building
            result = await mythic.waitfor_payload_complete(
                mythic=instance, payload_uuid=payload_uuid
            )
            build_phase = (result or {}).get("build_phase", "error")
            build_log = str((result or {}).get("build_message") or "")
            await self._write_state(
                f"{self.payload_key(payload_uuid)}:events",
                build_phase,
                _snap(
                    "build",
                    payload_uuid=payload_uuid,
                    status=build_phase,
                    raw_log=build_log,
                ),
            )
            await self._persist_payload_build(payload_uuid, build_phase, build_log)
        except Exception as e:
            logger.warning("payload watch for %s failed: %s", payload_uuid, e)

    async def _persist_payload_build(
        self, payload_uuid: str, build_phase: str, build_log: str
    ) -> None:
        """save final build state on step rows & mirror to their streams"""
        async with get_async_session() as session:
            rows = await session.execute(
                select(AttackStep).where(AttackStep.mythic_payload_uuid == payload_uuid)
            )
            step_ids = []
            for step in rows.scalars():
                step.status = build_phase
                step.raw_log = build_log
                step_ids.append(step.id)
            await session.commit()
        for step_id in step_ids:
            for key in await self._task_keys_for_step(step_id):
                await self._redis.xadd(
                    key,
                    _encode(
                        _snap(
                            "build",
                            step_id=step_id,
                            status=build_phase,
                            raw_log=build_log,
                        )
                    ),
                )

    async def _task_keys_for_step(self, step_id: int) -> list[str]:
        async with get_async_session() as session:
            rows = await session.execute(
                select(MythicTask).where(MythicTask.step_id == step_id)
            )
            return [f"{self.task_key(r.mythic_task_id)}:events" for r in rows.scalars()]

    async def follow_task(self, mythic_task_id: int) -> AsyncGenerator[str]:
        """iterate task events from redis, from the current moment"""
        if not self.available:
            return
        key = f"{self.task_key(mythic_task_id)}:events"
        last_id = "$"
        while True:
            resp = await self._redis.xread({key: last_id}, count=10, block=10_000)
            if not resp:
                continue
            for stream, rows in resp:
                for row_id, raw in rows:
                    if stream != key:
                        break
                    last_id = row_id
                    yield _decode(raw)

    async def wait_for_task(self, mythic_task_id: int, timeout: int = 300) -> str:
        """bounded wait like old blocking way, returns final status or timeout"""

        async def _inner() -> str:
            async for raw in self.follow_task(mythic_task_id):
                event = json.loads(raw)
                if event.get("completed") or event.get("status") in TERMINAL:
                    return event.get("status", "completed")
            return "fail"

        try:
            return await asyncio.wait_for(_inner(), timeout)
        except TimeoutError:
            return "timeout"

    async def wait_for_task_output(  # noqa: PLR0913, PLR0917
        self, mythic_task_id: int, timeout: int = 300, grace: int = 15
    ) -> tuple[str, str]:
        """like wait_for_task but collects raw output too,
        gr a status may still be followed by output rows"""
        out, status = "", "submitted"
        completed_at = None
        started = asyncio.get_running_loop().time()

        async def _inner() -> tuple[str, str]:
            nonlocal out, status, completed_at
            async for raw in self.follow_task(mythic_task_id):
                event = json.loads(raw)
                loop_t = asyncio.get_running_loop().time()
                completed = (
                    bool(event.get("completed")) or event.get("status") in TERMINAL
                )
                if completed and completed_at is None:
                    completed_at = loop_t
                if event.get("event") == "output":
                    out += str(event.get("raw_log") or "")
                    return out, str(event.get("status") or status)
                if event.get("event") == "status":
                    status = str(event.get("status") or status)
                # keep following after terminal, output collector emits soon
                if completed and (loop_t - completed_at) > grace:
                    return out, status
                if loop_t - started > timeout:
                    return out, status
            return out, status

        try:
            return await asyncio.wait_for(_inner(), timeout + grace)
        except TimeoutError:
            return out, status

    async def get_task_status(self, mythic_task_id: int) -> dict | None:
        """current status from redis hot state, or None"""
        if not self.available:
            return None
        hash_map = await self._redis.hgetall(self.task_key(mythic_task_id))
        return hash_map if hash_map else None

    async def step_stream_keys(self, step_id: int) -> list[str]:
        """event stream keys of step: all task streams + payload stream"""
        keys = await self._task_keys_for_step(step_id)
        async with get_async_session() as session:
            step = await session.scalar(
                select(AttackStep).where(AttackStep.id == step_id)
            )
            if step is not None and step.mythic_payload_uuid:
                keys.append(f"{self.payload_key(step.mythic_payload_uuid)}:events")
        return keys

    async def read_streams(
        self, last: dict[str, str], block_ms: int = 15_000
    ) -> list[tuple[str, list[tuple[str, str]]]]:
        """multi-stream xread by caller-owned last ids, low level for sse"""
        if not self.available:
            return []
        return await self._redis.xread(last, count=50, block=block_ms)

    async def stream_step_events(
        self, step_id: int, snapshot: dict
    ) -> AsyncGenerator[str]:
        """ndjson stream of one step: snapshot first, then live task & payload
        events; a stream closes after terminal rows settle (grace), or if it
        stays idle too long, so the client re-snapshots instead of hanging"""
        yield json.dumps({"event": "snapshot", "step": snapshot}) + "\n"
        keys = await self.step_stream_keys(step_id)
        if not keys or not self.available:
            return
        # state per key: last id + when it got terminal (None=not yet)
        state = {k: {"last": "$", "terminal_t": None} for k in keys}
        start_t = time.time()

        def all_settled() -> bool:
            return not state

        while not all_settled():
            live_last = {k: s["last"] for k, s in state.items()}
            resp = await self.read_streams(live_last, block_ms=STREAM_BLOCK_MS)
            now_t = time.time()
            if not resp:
                # idle: drop settled-by-grace keys and stale-idle streams
                for k in sorted(state):
                    s = state[k]
                    if s["terminal_t"] and now_t - s["terminal_t"] > STREAM_GRACE_SEC:
                        del state[k]
                    elif not s["terminal_t"] and now_t - start_t > STREAM_IDLE_SEC:
                        logger.info("step %s stream %s idle, closing", step_id, k)
                        del state[k]
                continue
            for stream_key, rows in resp:
                if stream_key not in state:
                    continue
                for row_id, raw in rows:
                    state[stream_key]["last"] = row_id
                    row = _decode(raw)
                    event = json.loads(row)
                    if event.get("event") == "status" and event.get("completed"):
                        state[stream_key]["terminal_t"] = time.time()
                    if event.get("event") in ("output", "build", "analysis") and (
                        state[stream_key].get("terminal_t") is None
                    ):
                        state[stream_key]["terminal_t"] = time.time() - (
                            STREAM_GRACE_SEC - 2
                        )
                    yield row
