import logging
from dataclasses import dataclass, field

from notion_client import AsyncClient
from notion_client.errors import APIResponseError

logger = logging.getLogger(__name__)

# Properties that are NOT cohort types (system/service properties)
EXCLUDED_PROPERTIES = frozenset({
    "Doc name",
    "Telegram ID",
    "Договор",
    "Версия договора с ментором",
    "Истекает договор",
    "Оценка ученика (0-10)",
    "Last edited time",
    "Стажор",
    "Author",
})

# Notion property types that represent cohort groupings
COHORT_PROPERTY_TYPES = frozenset({"multi_select", "status", "person", "select"})

# Built-in types that cannot be deleted/renamed via bot
PROTECTED_TYPES = frozenset({"Status", "Mentor"})


@dataclass
class CohortTypeInfo:
    name: str
    notion_type: str  # "multi_select" | "status" | "person" | "select"
    options: list[str] = field(default_factory=list)
    editable: bool = False  # can CRUD options via API
    type_editable: bool = False  # can delete/rename the type itself


def get_notion_service() -> "NotionService | None":
    """Factory for NotionService. Returns None if Notion is not configured."""
    from src.core.config import settings

    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        return None
    return NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)


class NotionService:
    """Wrapper around Notion API for cohort management."""

    def __init__(self, token: str, database_id: str):
        self._client = AsyncClient(auth=token)
        self._database_id = database_id

    # === Pages (users) ===

    async def find_page_by_username(self, username: str) -> dict | None:
        clean = username.lstrip("@")
        for query_val in [f"@{clean}", clean]:
            try:
                resp = await self._client.databases.query(
                    database_id=self._database_id,
                    filter={
                        "property": "Doc name",
                        "title": {"equals": query_val},
                    },
                    page_size=1,
                )
                if resp["results"]:
                    return resp["results"][0]
            except APIResponseError as e:
                logger.error("Notion query by username '%s' failed: %s", query_val, e)
                return None
        return None

    async def find_page_by_telegram_id(self, tg_id: int) -> dict | None:
        try:
            resp = await self._client.databases.query(
                database_id=self._database_id,
                filter={
                    "property": "Telegram ID",
                    "number": {"equals": tg_id},
                },
                page_size=1,
            )
            return resp["results"][0] if resp["results"] else None
        except APIResponseError as e:
            logger.error("Notion query by telegram_id %s failed: %s", tg_id, e)
            return None

    async def create_page(self, username: str, telegram_id: int) -> dict | None:
        clean = username.lstrip("@")
        try:
            return await self._client.pages.create(
                parent={"database_id": self._database_id},
                properties={
                    "Doc name": {"title": [{"text": {"content": f"@{clean}"}}]},
                    "Telegram ID": {"number": telegram_id},
                },
            )
        except APIResponseError as e:
            logger.error("Notion create page for @%s failed: %s", clean, e)
            return None

    async def update_page_properties(
        self, page_id: str, properties: dict
    ) -> dict | None:
        try:
            return await self._client.pages.update(
                page_id=page_id, properties=properties
            )
        except APIResponseError as e:
            logger.error("Notion update page %s failed: %s", page_id, e)
            return None

    async def get_all_pages(self) -> list[dict]:
        pages: list[dict] = []
        try:
            cursor = None
            while True:
                kwargs: dict = {
                    "database_id": self._database_id,
                    "page_size": 100,
                }
                if cursor:
                    kwargs["start_cursor"] = cursor
                resp = await self._client.databases.query(**kwargs)
                pages.extend(resp["results"])
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
        except APIResponseError as e:
            logger.error("Notion get_all_pages failed: %s", e)
        return pages

    # === Database schema (cohort types) ===

    async def get_database_schema(self) -> dict:
        try:
            db = await self._client.databases.retrieve(
                database_id=self._database_id
            )
            return db.get("properties", {})
        except APIResponseError as e:
            logger.error("Notion get_database_schema failed: %s", e)
            return {}

    async def get_cohort_types(self) -> list[CohortTypeInfo]:
        schema = await self.get_database_schema()
        result: list[CohortTypeInfo] = []

        for prop_name, prop_config in schema.items():
            if prop_name in EXCLUDED_PROPERTIES:
                continue
            prop_type = prop_config.get("type", "")
            if prop_type not in COHORT_PROPERTY_TYPES:
                continue

            options: list[str] = []
            editable = False
            type_editable = prop_name not in PROTECTED_TYPES

            if prop_type == "multi_select":
                options = [
                    o["name"]
                    for o in prop_config.get("multi_select", {}).get("options", [])
                ]
                editable = True
            elif prop_type == "select":
                options = [
                    o["name"]
                    for o in prop_config.get("select", {}).get("options", [])
                ]
                editable = True
            elif prop_type == "status":
                groups = prop_config.get("status", {}).get("groups", [])
                for group in groups:
                    for opt in group.get("options", []):
                        if opt.get("name"):
                            options.append(opt["name"])
                # status options are not editable via API
                editable = False
            elif prop_type == "person":
                # person type has no predefined options
                editable = False

            result.append(
                CohortTypeInfo(
                    name=prop_name,
                    notion_type=prop_type,
                    options=options,
                    editable=editable,
                    type_editable=type_editable,
                )
            )

        return result

    # === CRUD options within a type ===

    async def get_options(self, property_name: str) -> list[str]:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type == "multi_select":
            return [
                o["name"]
                for o in prop.get("multi_select", {}).get("options", [])
            ]
        elif prop_type == "select":
            return [
                o["name"] for o in prop.get("select", {}).get("options", [])
            ]
        elif prop_type == "status":
            options = []
            for group in prop.get("status", {}).get("groups", []):
                for opt in group.get("options", []):
                    if opt.get("name"):
                        options.append(opt["name"])
            return options
        return []

    async def add_option(self, property_name: str, option_name: str) -> bool:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type not in ("multi_select", "select"):
            logger.warning("Cannot add option to %s type %s", property_name, prop_type)
            return False

        existing = prop.get(prop_type, {}).get("options", [])
        new_options = existing + [{"name": option_name}]

        try:
            await self._client.databases.update(
                database_id=self._database_id,
                properties={
                    property_name: {prop_type: {"options": new_options}},
                },
            )
            return True
        except APIResponseError as e:
            logger.error("Notion add_option '%s' to '%s' failed: %s", option_name, property_name, e)
            return False

    async def rename_option(
        self, property_name: str, old_name: str, new_name: str
    ) -> bool:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type not in ("multi_select", "select"):
            return False

        options = prop.get(prop_type, {}).get("options", [])
        updated = []
        found = False
        for opt in options:
            if opt["name"] == old_name:
                updated.append({"id": opt.get("id"), "name": new_name})
                found = True
            else:
                updated.append(opt)

        if not found:
            return False

        try:
            await self._client.databases.update(
                database_id=self._database_id,
                properties={
                    property_name: {prop_type: {"options": updated}},
                },
            )
            return True
        except APIResponseError as e:
            logger.error("Notion rename_option failed: %s", e)
            return False

    async def remove_option(self, property_name: str, option_name: str) -> bool:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type not in ("multi_select", "select"):
            return False

        options = prop.get(prop_type, {}).get("options", [])
        filtered = [o for o in options if o["name"] != option_name]

        if len(filtered) == len(options):
            return False  # option not found

        try:
            await self._client.databases.update(
                database_id=self._database_id,
                properties={
                    property_name: {prop_type: {"options": filtered}},
                },
            )
            return True
        except APIResponseError as e:
            logger.error("Notion remove_option failed: %s", e)
            return False

    # === CRUD cohort types (database properties) ===

    async def create_cohort_type(self, property_name: str) -> bool:
        try:
            await self._client.databases.update(
                database_id=self._database_id,
                properties={
                    property_name: {"multi_select": {"options": []}},
                },
            )
            return True
        except APIResponseError as e:
            logger.error("Notion create_cohort_type '%s' failed: %s", property_name, e)
            return False

    async def delete_cohort_type(self, property_name: str) -> bool:
        if property_name in PROTECTED_TYPES:
            logger.warning("Cannot delete protected type: %s", property_name)
            return False

        try:
            # Notion API: set property to None to delete it
            await self._client.databases.update(
                database_id=self._database_id,
                properties={property_name: None},
            )
            return True
        except APIResponseError as e:
            logger.error("Notion delete_cohort_type '%s' failed: %s", property_name, e)
            return False

    async def rename_cohort_type(self, old_name: str, new_name: str) -> bool:
        if old_name in PROTECTED_TYPES:
            logger.warning("Cannot rename protected type: %s", old_name)
            return False

        try:
            await self._client.databases.update(
                database_id=self._database_id,
                properties={old_name: {"name": new_name}},
            )
            return True
        except APIResponseError as e:
            logger.error("Notion rename_cohort_type failed: %s", e)
            return False

    async def close(self) -> None:
        await self._client.aclose()
