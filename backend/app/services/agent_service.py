"""Persistence, ownership rules and the LLM facade for the analysis agent."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.parsing import DocumentError, mime_of, parse_bytes, suffix_of
from app.agent.validation import validate_draft
from app.cmd.llm_analysis import (
    ChatStreamProvider,
    ProviderNotConfigured,
    build_provider,
    list_models,
    llm_service,
)
from app.core.config import (
    AGENT_WORKSPACE_DIR,
    MAX_DOCUMENT_CHARS,
    MAX_DOCUMENT_MB,
    get_settings,
    phases,
)
from app.models import (
    AgentDocument,
    AgentFinding,
    AgentMessage,
    AgentRun,
    AgentSession,
    AttackChain,
    AttackStep,
    ChainDraft,
    CurrentAttackPhase,
    User,
)

# ask-mode chain snapshot is bounded so a long chain cannot eat the context
_MAX_CHAIN_CONTEXT_CHARS = 8000
_EDITABLE_STATUSES = ("planned", "pending")
_EDIT_STEP_TYPES = ("local", "agent", "bash")


class EditError(RuntimeError):
    """one operation could not be applied; reported per-op, never aborts the run"""


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # headers/endpoints never import app/cmd directly; provider selection,
    # provider listing and the chain-work g4f/ollama pool all go through here

    def get_provider(
        self, *, provider: str | None = None, model: str | None = None
    ) -> ChatStreamProvider:
        try:
            return build_provider(
                get_settings().llmservice, provider=provider, model=model
            )
        except ProviderNotConfigured as exc:
            # a missing provider is config, not a crash; the SSE/UI maps it
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

    async def list_providers(self) -> dict[str, dict[str, Any]]:
        return await list_models(get_settings().llmservice)

    def llm_providers(self) -> dict[str, str]:
        """registered g4f provider classes for the chain-work LLM path"""
        return {name: p.__name__ for name, p in llm_service.providers.items()}

    async def query_llm(self, prompt: str, provider_name: str | None = None) -> str:
        return await llm_service.query_llm(prompt, provider_name)

    async def query_llm_chat(
        self, messages: list[dict[str, Any]], provider_name: str | None = None
    ) -> str:
        return await llm_service.query_llm_chat(messages, provider_name)

    async def create_session(
        self, user: User, *, chain_id: int | None = None, title: str | None = None
    ) -> AgentSession:
        if chain_id is not None:
            await self._owned_chain(chain_id, user)
        row = AgentSession(
            user_id=user.user_id,
            chain_id=chain_id,
            title=(title or "New analysis").strip()[:256],
            status="active",
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_sessions(self, user: User) -> list[AgentSession]:
        result = await self.session.scalars(
            select(AgentSession)
            .where(AgentSession.user_id == user.user_id)
            .order_by(AgentSession.update_time.desc(), AgentSession.id.desc())
        )
        return list(result)

    async def get_session(self, session_id: int, user: User) -> AgentSession:
        row = await self.session.scalar(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.user_id == user.user_id,
            )
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="agent session not found"
            )
        return row

    async def update_session(
        self, session_id: int, user: User, *, title: str
    ) -> AgentSession:
        row = await self.get_session(session_id, user)
        row.title = title.strip()[:256]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_session(self, session_id: int, user: User) -> None:
        row = await self.get_session(session_id, user)
        await self.session.delete(row)
        await self.session.commit()

    async def list_messages(self, session_id: int) -> list[AgentMessage]:
        result = await self.session.scalars(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.id)
        )
        return list(result)

    async def list_documents(self, session_id: int) -> list[AgentDocument]:
        result = await self.session.scalars(
            select(AgentDocument)
            .where(AgentDocument.session_id == session_id)
            .order_by(AgentDocument.id)
        )
        return list(result)

    async def get_latest_draft(self, session_id: int) -> ChainDraft | None:
        return await self.session.scalar(
            select(ChainDraft)
            .where(ChainDraft.session_id == session_id)
            .order_by(ChainDraft.id.desc())
            .limit(1)
        )

    async def add_document(
        self, session_id: int, user: User, *, filename: str, data: bytes
    ) -> AgentDocument:
        await self.get_session(session_id, user)
        limit = MAX_DOCUMENT_MB * 1024 * 1024
        if len(data) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"document is larger than {MAX_DOCUMENT_MB} MB",
            )

        safe_name = Path(filename or "upload").name[:512]
        try:
            parsed = parse_bytes(safe_name, data, max_chars=MAX_DOCUMENT_CHARS)
        except DocumentError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

        row = AgentDocument(
            session_id=session_id,
            filename=safe_name,
            sha256=_sha256_hex(data),
            mime=mime_of(safe_name),
            size=len(data),
            storage_path="",
            parse_status="parsed",
            page_count=parsed.page_count,
            char_count=parsed.char_count,
            truncated=parsed.truncated,
            error=None,
        )
        self.session.add(row)
        await self.session.flush()

        session_dir = _workspace_dir() / str(session_id)
        session_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        suffix = suffix_of(safe_name) or ".bin"
        raw_path = session_dir / f"{row.id}-{row.sha256[:16]}{suffix}"
        parsed_path = session_dir / f"{row.id}-{row.sha256[:16]}.pages.json"
        raw_path.write_bytes(data)
        parsed_path.write_text(
            json.dumps(
                {
                    "extractor": parsed.extractor,
                    "pages": [[page, text] for page, text in parsed.pages],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        row.storage_path = str(raw_path)
        row.parsed_path = str(parsed_path)
        await self.session.commit()
        await self.session.refresh(row)

        return row

    async def get_document(
        self, document_id: int, user: User
    ) -> tuple[AgentDocument, AgentSession]:
        row = await self.session.scalar(
            select(AgentDocument).where(AgentDocument.id == document_id)
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
            )
        session_row = await self.get_session(row.session_id, user)
        return row, session_row

    def load_pages(self, document: AgentDocument) -> list[tuple[int | None, str]]:
        if not document.parsed_path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="document has no parsed text",
            )
        payload = json.loads(Path(document.parsed_path).read_text(encoding="utf-8"))
        return [(page, text) for page, text in payload.get("pages", [])]

    async def add_user_message(self, session_id: int, content: str) -> AgentMessage:
        row = AgentMessage(
            session_id=session_id,
            role="user",
            content=[{"type": "text", "text": content}],
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_run(self, session_id: int, document_id: int | None) -> AgentRun:
        row = AgentRun(
            session_id=session_id,
            document_id=document_id,
            status="running",
            cancel_requested=False,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_run(self, run_id: int, user: User) -> AgentRun:
        row = await self.session.scalar(
            select(AgentRun)
            .join(AgentSession, AgentRun.session_id == AgentSession.id)
            .where(
                AgentRun.id == run_id,
                AgentSession.user_id == user.user_id,
            )
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="agent run not found"
            )
        return row

    async def request_cancel(self, run_id: int) -> None:
        row = await self.session.get(AgentRun, run_id)
        if row is not None and row.status == "running":
            row.cancel_requested = True
            await self.session.commit()

    async def attach_message_to_run(self, message_id: int, run_id: int) -> None:
        row = await self.session.get(AgentMessage, message_id)
        if row is not None:
            row.run_id = run_id
            await self.session.commit()

    async def save_assistant_message(
        self, session_id: int, run_id: int, content: list[dict[str, Any]]
    ) -> AgentMessage:
        row = AgentMessage(
            session_id=session_id,
            role="assistant",
            content=content,
            run_id=run_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    def make_finding_saver(
        self, run: AgentRun
    ) -> Callable[[dict[str, Any]], Awaitable[int]]:
        """returns an async callback the pipeline uses to persist one finding."""
        counter = {"index": 0}

        async def save(finding: dict[str, Any]) -> int:
            counter["index"] += 1
            row = AgentFinding(
                run_id=run.id,
                session_id=run.session_id,
                order_index=counter["index"],
                stage=finding.get("stage"),
                title=finding["title"],
                description=finding.get("description") or "",
                confidence=float(finding.get("confidence") or 0.0),
                uncertainty=finding.get("uncertainty") or None,
                evidence=finding.get("evidence") or [],
                status="accepted",
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return row.id

        return save

    async def finish_run(
        self, run_id: int, *, status: str, error: str | None = None
    ) -> None:
        row = await self.session.get(AgentRun, run_id)
        if row is None:
            return
        row.status = status
        row.cancel_requested = status == "cancelled"
        row.error = error
        row.finished_at = datetime.now(UTC)
        await self.session.commit()

    async def save_draft(
        self,
        *,
        session_id: int,
        run_id: int,
        user: User,
        payload: dict[str, Any],
        name: str,
    ) -> ChainDraft:
        row = ChainDraft(
            session_id=session_id,
            run_id=run_id,
            user_id=user.user_id,
            name=(name or "Untitled draft")[:256],
            status=payload.get("status", "needs_review"),
            version=1,
            payload=payload,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_draft(self, draft_id: int, user: User) -> ChainDraft:
        row = await self.session.scalar(
            select(ChainDraft).where(
                ChainDraft.id == draft_id, ChainDraft.user_id == user.user_id
            )
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="draft not found"
            )
        return row

    def build_import(
        self, draft: ChainDraft, *, chain_name: str, require_commands: bool = True
    ) -> dict[str, Any]:
        """re-validate on read, then shape steps exactly like ChainCanvas expects."""
        payload = dict(draft.payload or {})
        validated = validate_draft(
            payload,
            phase_names=phases,
            risky_patterns=get_settings().local_bash.reject,
            require_commands=require_commands,
        )
        if validated["validation"]["errors"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "draft failed validation",
                    "errors": validated["validation"]["errors"],
                },
            )

        steps: list[dict[str, Any]] = []
        for index, step in enumerate(validated["steps"], start=1):
            is_agent = step["step_type"] == "agent"
            steps.append(
                {
                    "_tempId": f"draft-{draft.id}-{index}",
                    "chain_name": chain_name,
                    "phase": step["phase"],
                    "step_type": step["step_type"],
                    "tool_name": step["tool_name"],
                    "command": "" if is_agent else step["command"],
                    "command_params": step["command"] if is_agent else "",
                    "tool": step["tool_name"] if is_agent else "shell",
                    "callback_display_id": 0,
                    "status": "pending",
                    "raw_log": "",
                    "rationale": step.get("rationale", ""),
                    "finding_ids": step.get("finding_ids", []),
                    "confidence": step.get("confidence", 0.0),
                    "dangerous": step.get("dangerous", False),
                }
            )

        return {
            "draft_id": draft.id,
            "name": draft.name,
            "steps": steps,
            "validation": validated["validation"],
        }

    async def import_draft(
        self, draft: ChainDraft, user: User, *, chain_name: str
    ) -> dict[str, Any]:
        """materialize draft steps as real, non-executing AttackStep rows."""
        if draft.status == "imported":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="draft was already imported",
            )
        session_row = await self.get_session(draft.session_id, user)
        if session_row.chain_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="agent session is not bound to a chain",
            )
        chain = await self._owned_chain(session_row.chain_id, user)
        if chain.chain_name != chain_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="session is bound to a different chain",
            )

        is_plan = (draft.payload or {}).get("mode") == "plan" or (
            draft.payload or {}
        ).get("status") == "plan"
        result = self.build_import(
            draft, chain_name=chain.chain_name, require_commands=not is_plan
        )

        # one constructor: a new proposal replaces the previous unexecuted one.
        # Executed rows (success/error/submitted) are never touched.
        replaced = await self.session.execute(
            delete(AttackStep).where(
                AttackStep.chain_id == chain.id,
                AttackStep.status.in_(("planned", "pending")),
                AttackStep.mythic_task_id == 0,
                AttackStep.mythic_payload_id == 0,
            )
        )
        replaced_count = int(getattr(replaced, "rowcount", 0) or 0)
        row_status = "planned" if is_plan else "pending"
        steps: list[dict[str, Any]] = []
        for step in result["steps"]:
            is_agent = step["step_type"] == "agent"
            row = AttackStep(
                chain_id=chain.id,
                phase=step["phase"],
                step_type=step["step_type"],
                tool_name=step["tool_name"] or "shell",
                command=step["command_params"] if is_agent else step["command"],
                mythic_task_id=0,
                mythic_payload_id=0,
                mythic_payload_uuid=str(uuid.uuid4()),
                raw_log="",
                status=row_status,
            )
            self.session.add(row)
            await self.session.flush()
            steps.append(
                {
                    **step,
                    "status": row_status,
                    "id": row.id,
                    "_tempId": f"step-{row.id}",
                }
            )

        draft.status = "imported"
        await self.session.commit()
        return {
            "draft_id": draft.id,
            "name": draft.name,
            "steps": steps,
            "validation": result["validation"],
            "replaced": replaced_count,
        }

    async def chain_context(self, session_row: AgentSession, user: User) -> str:
        """compact, bounded snapshot of the chain for ask mode."""
        if session_row.chain_id is None:
            return ""
        chain = await self._owned_chain(session_row.chain_id, user)
        current = await self.session.scalar(
            select(CurrentAttackPhase.phase).where(
                CurrentAttackPhase.chain_id == chain.id
            )
        )
        steps = await self.session.scalars(
            select(AttackStep)
            .where(AttackStep.chain_id == chain.id)
            .order_by(AttackStep.id)
        )
        lines = [
            f"Chain: {chain.chain_name}",
            f"Current phase: {current or 'unknown'}",
            "Steps (id | phase | type | tool | status | command | output):",
        ]
        for step in steps:
            command = (step.command or "").replace("\n", " ")[:180]
            output = (step.raw_log or "").replace("\n", " ")[:180]
            lines.append(
                f"- {step.id} | {step.phase} | {step.step_type} | {step.tool_name} "
                f"| {step.status} | {command} | {output}"
            )
            if sum(len(line) for line in lines) > _MAX_CHAIN_CONTEXT_CHARS:
                lines.append("- … chain truncated")
                break

        return "\n".join(lines)

    async def chain_for_edit(
        self, session_row: AgentSession, user: User
    ) -> AttackChain:
        if session_row.chain_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="agent session is not bound to a chain",
            )
        return await self._owned_chain(session_row.chain_id, user)

    async def apply_edits(
        self,
        operations: list[dict[str, Any]],
        chain: AttackChain,
        user: User,
        *,
        runner: Callable[[AttackStep], Awaitable[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """execute validated chain operations; failures are per-op, not fatal."""
        results: list[dict[str, Any]] = []
        for raw in operations[:10]:
            op = str(raw.get("op") or "")
            try:
                if op == "add_step":
                    results.append(await self._edit_add_step(raw, chain))
                elif op == "remove_step":
                    results.append(await self._edit_remove_step(raw, chain))
                elif op == "run_step":
                    results.append(await self._edit_run_step(raw, chain, runner))
                elif op == "set_phase":
                    results.append(await self._edit_set_phase(raw, chain))
                else:
                    raise EditError(f"unknown operation '{op}'")
            except EditError as exc:
                # validation failure, nothing was written: keep the transaction
                results.append({"op": op, "status": "error", "detail": str(exc)[:200]})
            except SQLAlchemyError as exc:
                await self.session.rollback()
                results.append({"op": op, "status": "error", "detail": str(exc)[:200]})
            except Exception as exc:
                results.append({"op": op, "status": "error", "detail": str(exc)[:200]})

        return results

    async def _edit_add_step(
        self, op: dict[str, Any], chain: AttackChain
    ) -> dict[str, Any]:
        phase = op.get("phase")
        if phase not in phases:
            raise EditError(f"unknown phase '{phase}'")
        step_type = op.get("step_type")
        if step_type not in _EDIT_STEP_TYPES:
            raise EditError(f"unsupported step_type '{step_type}'")
        command = str(op.get("command") or "").strip()
        if not command:
            raise EditError("add_step needs a command")

        row = AttackStep(
            chain_id=chain.id,
            phase=phase,
            step_type=step_type,
            tool_name=str(op.get("tool_name") or "shell")[:64],
            command=command[:4000],
            mythic_task_id=0,
            mythic_payload_id=0,
            mythic_payload_uuid=str(uuid.uuid4()),
            raw_log="",
            status="pending",
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return {"op": "add_step", "status": "ok", "step_id": row.id}

    async def _chain_step(self, op: dict[str, Any], chain: AttackChain) -> AttackStep:
        try:
            step_id = int(op.get("step_id") or 0)
        except (TypeError, ValueError) as exc:
            raise EditError("invalid step_id") from exc
        step = await self.session.scalar(
            select(AttackStep).where(
                AttackStep.id == step_id, AttackStep.chain_id == chain.id
            )
        )
        if step is None:
            raise EditError(f"step {step_id} is not in this chain")
        return step

    async def _edit_remove_step(
        self, op: dict[str, Any], chain: AttackChain
    ) -> dict[str, Any]:
        step = await self._chain_step(op, chain)
        if step.status not in _EDITABLE_STATUSES:
            raise EditError(
                f"step {step.id} is {step.status}; only unexecuted steps can be removed"
            )

        step_id = step.id
        await self.session.delete(step)
        await self.session.commit()
        return {"op": "remove_step", "status": "ok", "step_id": step_id}

    async def _edit_run_step(
        self,
        op: dict[str, Any],
        chain: AttackChain,
        runner: Callable[[AttackStep], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        step = await self._chain_step(op, chain)
        if step.status not in _EDITABLE_STATUSES:
            raise EditError(
                f"step {step.id} is {step.status}; only unexecuted steps can run"
            )
        if not step.command.strip():
            raise EditError(f"step {step.id} has no command")
        # capture before any commit expires the instance
        step_id = step.id
        outcome = await runner(step)
        new_id = outcome.get("new_step_id")
        if new_id and new_id != step_id:
            # the run creates its own row; drop the placeholder
            await self.session.execute(
                delete(AttackStep).where(AttackStep.id == step_id)
            )
            await self.session.commit()

        return {
            "op": "run_step",
            "status": "ok",
            "step_id": step_id,
            "new_step_id": new_id,
            "run_status": outcome.get("status"),
        }

    async def _edit_set_phase(
        self, op: dict[str, Any], chain: AttackChain
    ) -> dict[str, Any]:
        phase = op.get("phase")
        if phase not in phases:
            raise EditError(f"unknown phase '{phase}'")
        current = await self.session.scalar(
            select(CurrentAttackPhase).where(CurrentAttackPhase.chain_id == chain.id)
        )
        if current is None:
            current = CurrentAttackPhase(chain_id=chain.id, phase=phase)
            self.session.add(current)
        else:
            current.phase = phase

        await self.session.commit()
        return {"op": "set_phase", "status": "ok", "phase": phase}

    async def _owned_chain(self, chain_id: int, user: User) -> AttackChain:
        chain = await self.session.scalar(
            select(AttackChain).where(
                AttackChain.id == chain_id, AttackChain.user_id == user.user_id
            )
        )
        if chain is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="chain not found"
            )
        return chain


def _workspace_dir() -> Path:
    AGENT_WORKSPACE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return AGENT_WORKSPACE_DIR


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = ["AgentService"]
