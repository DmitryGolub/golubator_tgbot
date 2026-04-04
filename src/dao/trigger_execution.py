from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.database import async_session_maker
from src.models.trigger import ExecutionStatus, TriggerExecution


class TriggerExecutionDAO:
    @classmethod
    async def create(
        cls,
        *,
        rule_id: int,
        event_key: str | None,
        recipient_id: int,
        scheduled_at: datetime | None = None,
        context: dict | None = None,
    ) -> tuple[TriggerExecution, bool]:
        """Create execution record. Returns (execution, already_existed)."""
        async with async_session_maker() as session:
            stmt = (
                pg_insert(TriggerExecution)
                .values(
                    rule_id=rule_id,
                    event_key=event_key,
                    recipient_id=recipient_id,
                    status=ExecutionStatus.pending,
                    scheduled_at=scheduled_at,
                    context=context,
                )
                .on_conflict_do_nothing()
                .returning(TriggerExecution)
            )
            result = await session.execute(stmt)
            execution = result.scalar_one_or_none()
            await session.commit()

            if execution:
                return execution, False

            # Conflict — fetch existing
            if event_key:
                existing = await session.execute(
                    select(TriggerExecution).where(
                        TriggerExecution.rule_id == rule_id,
                        TriggerExecution.event_key == event_key,
                        TriggerExecution.recipient_id == recipient_id,
                    )
                )
            else:
                existing = await session.execute(
                    select(TriggerExecution).where(
                        TriggerExecution.rule_id == rule_id,
                        TriggerExecution.recipient_id == recipient_id,
                        TriggerExecution.event_key.is_(None),
                    )
                )
            return existing.scalar_one(), True

    @classmethod
    async def mark_sent(cls, execution_id: int) -> None:
        async with async_session_maker() as session:
            execution = await session.get(TriggerExecution, execution_id)
            if execution:
                execution.status = ExecutionStatus.sent
                execution.executed_at = datetime.now(timezone.utc)
                await session.commit()

    @classmethod
    async def mark_failed(cls, execution_id: int, error: str) -> None:
        async with async_session_maker() as session:
            execution = await session.get(TriggerExecution, execution_id)
            if execution:
                execution.status = ExecutionStatus.failed
                execution.executed_at = datetime.now(timezone.utc)
                execution.error_message = error
                await session.commit()

    @classmethod
    async def get_pending_due(cls) -> list[TriggerExecution]:
        """Get pending executions where scheduled_at <= now."""
        async with async_session_maker() as session:
            now = datetime.now(timezone.utc)
            query = (
                select(TriggerExecution)
                .where(
                    TriggerExecution.status == ExecutionStatus.pending,
                    TriggerExecution.scheduled_at <= now,
                )
                .order_by(TriggerExecution.scheduled_at)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def claim_pending(cls, execution_id: int) -> TriggerExecution | None:
        """Atomically claim pending -> processing. Returns None if already claimed."""
        async with async_session_maker() as session:
            stmt = (
                update(TriggerExecution)
                .where(
                    TriggerExecution.id == execution_id,
                    TriggerExecution.status == ExecutionStatus.pending,
                )
                .values(status=ExecutionStatus.processing)
                .returning(TriggerExecution)
            )
            result = await session.execute(stmt)
            obj = result.scalar_one_or_none()
            await session.commit()
            return obj

    @classmethod
    async def claim_pending_batch(cls) -> list[TriggerExecution]:
        """Atomically claim all due pending -> processing."""
        async with async_session_maker() as session:
            now = datetime.now(timezone.utc)
            stmt = (
                update(TriggerExecution)
                .where(
                    TriggerExecution.status == ExecutionStatus.pending,
                    TriggerExecution.scheduled_at <= now,
                )
                .values(status=ExecutionStatus.processing)
                .returning(TriggerExecution)
            )
            result = await session.execute(stmt)
            claimed = list(result.scalars().all())
            await session.commit()
            return claimed
