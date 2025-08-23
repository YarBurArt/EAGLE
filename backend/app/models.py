""" Module for SQL Alchemy models declaration """
# https://docs.sqlalchemy.org/en/20/orm/quickstart.html#declare-models
# mapped_column syntax from SQLAlchemy 2.0.

# https://alembic.sqlalchemy.org/en/latest/tutorial.html
# Note, it is used by alembic migrations logic, see `alembic/env.py`

# Alembic shortcuts:
# # create migration
# alembic revision --autogenerate -m "migration_name"

# # apply all migrations
# alembic upgrade head


import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey,
    String, Uuid, func, Text, Integer
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "user_account"

    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True,
        default=lambda _: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(
        String(256), nullable=True, unique=True, index=True
    )
    role: Mapped[str] = mapped_column(
        String(64), nullable=True, unique=False
    )
    email: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    refresh_tokens: Mapped[list["RefreshToken"]
                           ] = relationship(back_populates="user")
    attack_chain: Mapped[list["AttackChain"]
                         ] = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    refresh_token: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.user_id", ondelete="CASCADE"),
    )
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class AttackChain(Base):
    __tablename__ = "attack_chain"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.user_id", ondelete="CASCADE"),
    )
    chain_name: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True
    )
    final_status: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    user: Mapped["User"] = relationship(back_populates="attack_chain")
    attack_step: Mapped[list["AttackStep"]] = relationship(
        back_populates="attack_chain")
    # audit may take several days, so storing it in the database is easier
    current_phase: Mapped["CurrentAttackPhase"] = relationship(
        back_populates="attack_chain",
        uselist=False,  # each chain has only one current phase.
        cascade="all, delete-orphan"  # del if c_phase is null
    )


class AttackStep(Base):
    __tablename__ = "attack_step"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    chain_id: Mapped[str] = mapped_column(
        ForeignKey("attack_chain.id", ondelete="CASCADE"),
    )
    # each step has a specific phase, which can differs from the current
    phase: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    tool_name: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    command: Mapped[str] = mapped_column(
        Text, nullable=False, unique=False
    )
    mythic_task_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=False
    )
    # only for downloading payload link
    mythic_payload_uuid: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), nullable=False, unique=False
    )
    mythic_payload_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=False
    )
    # raw command output from task, without llm
    raw_log: Mapped[str] = mapped_column(
        Text, nullable=True, unique=False
    )
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attack_chain: Mapped["AttackChain"] = relationship(
        back_populates="attack_step")
    agent: Mapped[list["Agent"]] = relationship(back_populates="attack_step")


class CurrentAttackPhase(Base):
    __tablename__ = "current_attack_phase"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    # chain always start with Reconnaissance
    phase: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Reconnaissance"
    )
    # user_id from attack_chain.user_id if necessary
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("attack_chain.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    # and update_time from base
    attack_chain: Mapped["AttackChain"] = relationship(
        back_populates="current_phase"
    )


class Agent(Base):
    __tablename__ = "agent"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    step_id: Mapped[str] = mapped_column(
        ForeignKey("attack_step.id", ondelete="CASCADE"),
    )
    agent_name: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=False
    )
    os_type: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=False
    )
    # id from mythic for performing tasks
    callback_display_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=False
    )
    attack_step: Mapped["AttackStep"] = relationship(back_populates="agent")
