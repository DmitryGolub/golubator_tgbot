from notion_client import AsyncClient


class NotionAssertions:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def get_page(self, page_id: str) -> dict:
        return await self._client.pages.retrieve(page_id=page_id)

    async def assert_page_property(
        self, page_id: str, property_name: str, expected_value: str
    ):
        page = await self.get_page(page_id)
        props = page["properties"]
        assert property_name in props, f"Property {property_name} not found"
        prop = props[property_name]
        actual = self._extract_value(prop)
        assert actual == expected_value, f"Expected {expected_value}, got {actual}"

    async def find_page_by_telegram_id(
        self, database_id: str, telegram_id: int
    ) -> dict | None:
        result = await self._client.databases.query(
            database_id=database_id,
            filter={"property": "Telegram ID", "number": {"equals": telegram_id}},
        )
        pages = result.get("results", [])
        return pages[0] if pages else None

    async def assert_page_exists_for_user(
        self, database_id: str, telegram_id: int
    ) -> dict:
        page = await self.find_page_by_telegram_id(database_id, telegram_id)
        assert page is not None, f"Notion page not found for telegram_id={telegram_id}"
        return page

    async def assert_page_property_status(
        self, page_id: str, property_name: str, expected: str
    ):
        """Assert a Status-type property has the expected value."""
        page = await self.get_page(page_id)
        props = page["properties"]
        assert property_name in props, f"Property {property_name} not found"
        prop = props[property_name]
        assert prop["type"] == "status", f"Expected status type, got {prop['type']}"
        actual = prop["status"]["name"] if prop["status"] else ""
        assert actual == expected, (
            f"Property {property_name}: expected '{expected}', got '{actual}'"
        )

    async def assert_page_has_people(
        self, page_id: str, property_name: str, min_count: int = 1
    ):
        """Assert a People/Relation property has at least min_count entries."""
        page = await self.get_page(page_id)
        props = page["properties"]
        assert property_name in props, f"Property {property_name} not found"
        prop = props[property_name]
        t = prop["type"]
        if t == "people":
            count = len(prop["people"])
        elif t == "relation":
            count = len(prop["relation"])
        else:
            count = 0
        assert count >= min_count, (
            f"Property {property_name}: expected >= {min_count} entries, got {count}"
        )

    async def find_pages_by_run_id(self, database_id: str, run_id: str) -> list[dict]:
        """Find event pages created during a specific test run."""
        results = await self._client.databases.query(
            database_id=database_id,
            filter={"property": "Name", "title": {"contains": f"[E2E-{run_id}]"}},
        )
        return results.get("results", [])

    @staticmethod
    def _extract_value(prop: dict) -> str:
        """Extract text value from a Notion property."""
        t = prop["type"]
        if t == "title":
            return prop["title"][0]["plain_text"] if prop["title"] else ""
        elif t == "rich_text":
            return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
        elif t == "number":
            return str(prop["number"]) if prop["number"] is not None else ""
        elif t == "select":
            return prop["select"]["name"] if prop["select"] else ""
        elif t == "multi_select":
            return ", ".join(o["name"] for o in prop["multi_select"])
        return str(prop.get(t, ""))
