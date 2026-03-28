from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
            try:
                async with session.begin():
                    if event_key:
                        existing = await session.execute(
                            select(TriggerExecution).where(
                                TriggerExecution.rule_id == rule_id,
                                TriggerExecution.event_key == event_key,
                                TriggerExecution.recipient_id == recipient_id,
                            )
                        )
                        existing_exec = existing.scalar_one_or_none()
                        if existing_exec:
                            return existing_exec, True

                    execution = TriggerExecution(
                        rule_id=rule_id,
                        event_key=event_key,
                        recipient_id=recipient_id,
                        status=ExecutionStatus.pending,
                        scheduled_at=scheduled_at,
                        context=context,
                    )
                    session.add(execution)
                await session.refresh(execution)
            except IntegrityError:
                await session.rollback()
                if event_key:
                    existing = await session.execute(
                        select(TriggerExecution).where(
                            TriggerExecution.rule_id == rule_id,
                            TriggerExecution.event_key == event_key,
                            TriggerExecution.recipient_id == recipient_id,
                        )
                    )
                    existing_exec = existing.scalar_one_or_none()
                    if existing_exec:
                        return existing_exec, True
                raise

            return execution, False

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
