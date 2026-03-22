import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.models.notion_cache import NotionCohortCache
from src.models.user import User
from src.services.notion_client import (
    COHORT_PROPERTY_TYPES,
    EXCLUDED_PROPERTIES,
    NotionService,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    synced_users: int = 0
    cache_entries: int = 0
    errors: int = 0


class NotionSyncService:
    """Syncs cohort data from Notion database to local notion_cohort_cache."""

    def __init__(self, notion: NotionService):
        self._notion = notion

    async def sync_all(self) -> SyncResult:
        result = SyncResult()

        # 1. Get DB schema to determine cohort properties
        schema = await self._notion.get_database_schema()
        cohort_props = [
            name
            for name, conf in schema.items()
            if name not in EXCLUDED_PROPERTIES
            and conf.get("type", "") in COHORT_PROPERTY_TYPES
        ]

        if not cohort_props:
            logger.warning("No cohort properties found in Notion schema")
            return result

        # 2. Get all pages
        pages = await self._notion.get_all_pages()
        if not pages:
            return result

        # 3. Process pages
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)

        try:
            async with session_factory() as session:
                for page in pages:
                    try:
                        await self._process_page(session, page, cohort_props, now)
                        result.synced_users += 1
                    except Exception:
                        logger.exception(
                            "Error processing Notion page %s", page.get("id")
                        )
                        result.errors += 1

                await session.commit()
        finally:
            await engine.dispose()

        logger.info(
            "Notion sync complete: synced=%d, errors=%d",
            result.synced_users,
            result.errors,
        )
        return result

    async def _process_page(
        self,
        session: AsyncSession,
        page: dict,
        cohort_props: list[str],
        now: datetime,
    ) -> None:
        page_id = page["id"]
        props = page.get("properties", {})

        # Extract username from Doc name
        username = self._extract_title(props.get("Doc name", {}))
        if not username:
            return

        clean_username = username.lstrip("@")

        # Extract telegram_id from Notion page if present
        notion_tg_id = self._extract_number(props.get("Telegram ID", {}))

        # Find local user
        user = await self._find_user(session, page_id, clean_username, notion_tg_id)
        if not user:
            return

        # Update notion_page_id if not set
        if not user.notion_page_id:
            user.notion_page_id = page_id

        # Extract cohort memberships
        memberships = self._extract_memberships(props, cohort_props)

        # Replace cache entries for this user
        await session.execute(
            delete(NotionCohortCache).where(
                NotionCohortCache.user_telegram_id == user.telegram_id
            )
        )

        for cohort_type, cohort_value in memberships:
            session.add(
                NotionCohortCache(
                    user_telegram_id=user.telegram_id,
                    cohort_type=cohort_type,
                    cohort_value=cohort_value,
                    synced_at=now,
                )
            )

    async def _find_user(
        self,
        session: AsyncSession,
        page_id: str,
        username: str,
        telegram_id: int | None,
    ) -> User | None:
        # Try by telegram_id first (most reliable)
        if telegram_id:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                return user

        # Try by notion_page_id
        result = await session.execute(
            select(User).where(User.notion_page_id == page_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        # Try by username
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    def _extract_memberships(
        self, props: dict, cohort_props: list[str]
    ) -> list[tuple[str, str]]:
        memberships: list[tuple[str, str]] = []

        for prop_name in cohort_props:
            prop_data = props.get(prop_name, {})
            prop_type = prop_data.get("type", "")

            if prop_type == "multi_select":
                for item in prop_data.get("multi_select") or []:
                    if name := item.get("name"):
                        memberships.append((prop_name, name))

            elif prop_type == "select":
                sel = prop_data.get("select")
                if sel and (name := sel.get("name")):
                    memberships.append((prop_name, name))

            elif prop_type == "status":
                status = prop_data.get("status")
                if status and (name := status.get("name")):
                    memberships.append((prop_name, name))

            elif prop_type == "person":
                for person in prop_data.get("person") or []:
                    person_name = person.get("name") or person.get("id", "")
                    if person_name:
                        memberships.append((prop_name, person_name))

        return memberships

    @staticmethod
    def _extract_title(prop: dict) -> str | None:
        title_list = prop.get("title") or []
        if not title_list:
            return None
        return title_list[0].get("plain_text", "").strip() or None

    @staticmethod
    def _extract_number(prop: dict) -> int | None:
        val = prop.get("number")
        return int(val) if val is not None else None
