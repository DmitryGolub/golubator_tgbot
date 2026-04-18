from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.caldav import CalDAVAccount
from src.models.mentor import Mentor


class CalDAVAccountDAO(BaseDAO):
    model = CalDAVAccount

    @classmethod
    async def get_for_mentor(cls, telegram_id: int) -> Optional[CalDAVAccount]:
        async with async_session_maker() as session:
            query = (
                select(CalDAVAccount)
                .join(Mentor, Mentor.telegram_id == CalDAVAccount.telegram_id)
                .where(CalDAVAccount.telegram_id == telegram_id)
            )
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def get_by_id(cls, account_id: int) -> Optional[CalDAVAccount]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CalDAVAccount).where(CalDAVAccount.id == account_id)
            )
            return result.scalars().one_or_none()

    @classmethod
    async def upsert(
        cls,
        *,
        telegram_id: int,
        base_url: str,
        username: str,
        encrypted_password: str,
    ) -> CalDAVAccount:
        async with async_session_maker() as session:
            existing = await session.execute(
                select(CalDAVAccount).where(CalDAVAccount.telegram_id == telegram_id)
            )
            account = existing.scalars().one_or_none()
            if account is None:
                account = CalDAVAccount(
                    telegram_id=telegram_id,
                    base_url=base_url,
                    username=username,
                    encrypted_password=encrypted_password,
                    sync_enabled=False,
                )
                session.add(account)
            else:
                account.base_url = base_url
                account.username = username
                account.encrypted_password = encrypted_password
                account.sync_enabled = False
                account.last_error = None
                account.last_error_at = None
                account.consecutive_failures = 0
            await session.commit()
            await session.refresh(account)
            return account

    @classmethod
    async def set_calendars(
        cls,
        account_id: int,
        *,
        principal_url: Optional[str],
        calendar_home_url: Optional[str],
        default_calendar_url: Optional[str],
        calendar_display_name: Optional[str],
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(CalDAVAccount)
                .where(CalDAVAccount.id == account_id)
                .values(
                    principal_url=principal_url,
                    calendar_home_url=calendar_home_url,
                    default_calendar_url=default_calendar_url,
                    calendar_display_name=calendar_display_name,
                )
            )
            await session.commit()

    @classmethod
    async def mark_verified(cls, account_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(CalDAVAccount)
                .where(CalDAVAccount.id == account_id)
                .values(
                    sync_enabled=True,
                    last_verified_at=datetime.now(timezone.utc),
                    last_error=None,
                    last_error_at=None,
                    consecutive_failures=0,
                )
            )
            await session.commit()

    @classmethod
    async def mark_error(
        cls,
        account_id: int,
        error: str,
        *,
        disable_after: int = 5,
    ) -> bool:
        """Record an error; disable the account when failures exceed the threshold.

        Returns True if the account was auto-disabled.
        """
        async with async_session_maker() as session:
            res = await session.execute(
                select(CalDAVAccount).where(CalDAVAccount.id == account_id)
            )
            account = res.scalars().one_or_none()
            if account is None:
                return False
            account.consecutive_failures += 1
            account.last_error = error[:2000]
            account.last_error_at = datetime.now(timezone.utc)
            disabled = False
            if account.consecutive_failures >= disable_after:
                account.sync_enabled = False
                disabled = True
            await session.commit()
            return disabled

    @classmethod
    async def disable(cls, account_id: int, reason: Optional[str] = None) -> None:
        async with async_session_maker() as session:
            values = {"sync_enabled": False}
            if reason:
                values["last_error"] = reason[:2000]
                values["last_error_at"] = datetime.now(timezone.utc)
            await session.execute(
                update(CalDAVAccount)
                .where(CalDAVAccount.id == account_id)
                .values(**values)
            )
            await session.commit()

    @classmethod
    async def set_sync_enabled(cls, account_id: int, enabled: bool) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(CalDAVAccount)
                .where(CalDAVAccount.id == account_id)
                .values(sync_enabled=enabled)
            )
            await session.commit()
