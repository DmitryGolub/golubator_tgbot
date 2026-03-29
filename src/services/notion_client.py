import logging
from dataclasses import dataclass, field

from notion_client import AsyncClient
from notion_client.errors import APIResponseError

logger = logging.getLogger(__name__)

# Properties that are NOT cohort types (system/service properties)
EXCLUDED_PROPERTIES = frozenset(
    {
        "Doc name",
        "Telegram ID",
        "Договор",
        "Версия договора с ментором",
        "Истекает договор",
        "Оценка ученика (0-10)",
        "Last edited time",
        "Стажор",
        "Author",
    }
)

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
        self._data_source_id: str | None = None

    async def _resolve_data_source_id(self) -> str:
        ds_id = self._data_source_id
        if ds_id is None:
            db = await self._client.databases.retrieve(database_id=self._database_id)
            sources = db.get("data_sources", [])
            if not sources:
                raise RuntimeError(
                    f"No data sources found for database {self._database_id}"
                )
            ds_id = sources[0]["id"]
            self._data_source_id = ds_id
        return ds_id

    # === Pages (users) ===

    async def create_page(self, username: str, telegram_id: int) -> dict | None:
        clean = username.lstrip("@")
        try:
            ds_id = await self._resolve_data_source_id()
            return await self._client.pages.create(
                parent={"data_source_id": ds_id},
                properties={
                    "Doc name": {"title": [{"text": {"content": f"@{clean}"}}]},
                    "Telegram ID": {"number": telegram_id},
                },
            )
        except APIResponseError as e:
            logger.error("Notion create page for @%s failed: %s", clean, e)
            return None

    async def get_all_pages(self) -> list[dict]:
        pages: list[dict] = []
        try:
            cursor = None
            while True:
                ds_id = await self._resolve_data_source_id()
                kwargs: dict = {
                    "data_source_id": ds_id,
                    "page_size": 100,
                }
                if cursor:
                    kwargs["start_cursor"] = cursor
                resp = await self._client.data_sources.query(**kwargs)
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
            ds_id = await self._resolve_data_source_id()
            db = await self._client.data_sources.retrieve(data_source_id=ds_id)
            properties = db.get("properties", {})
            return properties
        except APIResponseError as e:
            logger.error("Notion get_database_schema failed: %s", e)
            return {}

    @staticmethod
    def _extract_options(prop_config: dict, prop_type: str) -> list[str]:
        """Extract option names from a property config.

        Supports both databases API and data_sources API response formats.
        """
        if prop_type in ("multi_select", "select"):
            # data_sources format: options at top level
            # databases format: options nested under type key
            options_list = prop_config.get("options") or (
                prop_config.get(prop_type, {}).get("options", [])
            )
            return [o["name"] for o in options_list if o.get("name")]

        if prop_type == "status":
            names: list[str] = []
            status_block = prop_config.get("status", {})

            # Primary: options directly (like select/multi_select)
            options_list = prop_config.get("options") or status_block.get("options", [])
            if options_list:
                names = [o["name"] for o in options_list if o.get("name")]

            # Fallback: extract from groups
            if not names:
                groups = prop_config.get("groups")
                if groups is None:
                    groups = status_block.get("groups")

                if isinstance(groups, dict):
                    for group_items in groups.values():
                        if isinstance(group_items, list):
                            for opt in group_items:
                                if isinstance(opt, dict) and opt.get("name"):
                                    names.append(opt["name"])
                elif isinstance(groups, list):
                    for group in groups:
                        for opt in group.get("options", []):
                            if opt.get("name"):
                                names.append(opt["name"])

            return names

        return []

    @staticmethod
    def _read_raw_options(prop_config: dict, prop_type: str) -> list[dict]:
        """Read raw option dicts for multi_select/select (for CRUD operations)."""
        return prop_config.get("options") or (
            prop_config.get(prop_type, {}).get("options", [])
        )

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

            if prop_type in ("multi_select", "select"):
                options = self._extract_options(prop_config, prop_type)
                editable = True
            elif prop_type == "status":
                options = self._extract_options(prop_config, prop_type)
                editable = False
            elif prop_type == "person":
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

        if prop_type in ("multi_select", "select", "status"):
            return self._extract_options(prop, prop_type)
        return []

    async def add_option(self, property_name: str, option_name: str) -> bool:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type not in ("multi_select", "select"):
            logger.warning("Cannot add option to %s type %s", property_name, prop_type)
            return False

        existing = self._read_raw_options(prop, prop_type)
        new_options = existing + [{"name": option_name}]

        try:
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
                properties={
                    property_name: {prop_type: {"options": new_options}},
                },
            )
            return True
        except APIResponseError as e:
            logger.error(
                "Notion add_option '%s' to '%s' failed: %s",
                option_name,
                property_name,
                e,
            )
            return False

    async def rename_option(
        self, property_name: str, old_name: str, new_name: str
    ) -> bool:
        schema = await self.get_database_schema()
        prop = schema.get(property_name, {})
        prop_type = prop.get("type", "")

        if prop_type not in ("multi_select", "select"):
            return False

        options = self._read_raw_options(prop, prop_type)
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
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
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

        options = self._read_raw_options(prop, prop_type)
        filtered = [o for o in options if o["name"] != option_name]

        if len(filtered) == len(options):
            return False  # option not found

        try:
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
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
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
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
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
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
            ds_id = await self._resolve_data_source_id()
            await self._client.data_sources.update(
                data_source_id=ds_id,
                properties={old_name: {"name": new_name}},
            )
            return True
        except APIResponseError as e:
            logger.error("Notion rename_cohort_type failed: %s", e)
            return False

    async def close(self) -> None:
        await self._client.aclose()
