from __future__ import annotations

import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError, MessageIdInvalidError
from telethon.tl.custom import Message


class _RateLimiter:
    """Guarantees minimum interval between any Telegram API calls."""

    def __init__(self, min_interval: float = 0.5):
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = asyncio.get_event_loop().time()


_limiter = _RateLimiter(min_interval=0.5)  # 2 req/s


async def _guarded_call(coro_fn, *args, **kwargs):
    """Rate-limited wrapper with FloodWait retry for any Telethon API call."""
    for attempt in range(3):
        await _limiter.acquire()
        try:
            return await coro_fn(*args, **kwargs)
        except FloodWaitError as e:
            if e.seconds > 300:
                raise AssertionError(
                    f"Telegram FloodWait {e.seconds}s — aborting"
                ) from e
            await asyncio.sleep(min(e.seconds + 1, 120))
    await _limiter.acquire()
    return await coro_fn(*args, **kwargs)


def _markup_signature(markup) -> tuple:
    """Extract button data as a hashable tuple for comparison."""
    if not markup or not hasattr(markup, "rows"):
        return ()
    return tuple((btn.text, btn.data) for row in markup.rows for btn in row.buttons)


class TelegramTestClient:
    """Wrapper over Telethon for E2E test convenience."""

    def __init__(self, client: TelegramClient, bot_username: str):
        self._client = client
        self._bot = bot_username

    async def send_command(self, command: str, timeout: float = 15) -> Message:
        """Send a command to the bot and get the first response."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _guarded_call(conv.send_message, command)
            return await _guarded_call(conv.get_response)

    async def send_command_multi(
        self, command: str, count: int = 2, timeout: float = 15
    ) -> list[Message]:
        """Send a command and get multiple responses (e.g. welcome + menu)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _guarded_call(conv.send_message, command)
            responses = []
            for _ in range(count):
                try:
                    responses.append(await _guarded_call(conv.get_response))
                except asyncio.TimeoutError:
                    break
            return responses

    async def click_button(
        self,
        message: Message,
        text: str | None = None,
        index: int | None = None,
        data: str | None = None,
        timeout: float = 30,
    ) -> Message:
        """Click an inline button and wait for the bot response (edit or new message).

        Uses polling approach: remembers last messages before click,
        then polls until a new/edited message appears.

        Args:
            text: Match button by display text (first match — ambiguous if duplicates).
            index: Match button by position index.
            data: Match button by callback_data (exact match — unambiguous).
        """
        # Remember state before click
        old_messages = await _guarded_call(
            self._client.get_messages, self._bot, limit=3
        )
        old_snapshots = {
            m.id: (m.text, m.edit_date, m.reply_markup) for m in old_messages
        }
        max_old_id = max(m.id for m in old_messages) if old_messages else 0

        # Perform click with retry on stale message
        for attempt in range(3):
            try:
                if data is not None:
                    await _guarded_call(
                        message.click,
                        data=data.encode() if isinstance(data, str) else data,
                    )
                elif text is not None:
                    await _guarded_call(message.click, text=text)
                elif index is not None:
                    await _guarded_call(message.click, index)
                else:
                    raise ValueError("Specify text, index, or data")
                break
            except MessageIdInvalidError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5)
                fresh_messages = await _guarded_call(
                    self._client.get_messages, self._bot, limit=5
                )
                matched = None
                for m in fresh_messages:
                    if not m.reply_markup or not hasattr(m.reply_markup, "rows"):
                        continue
                    for row in m.reply_markup.rows:
                        for btn in row.buttons:
                            if data is not None:
                                btn_data = btn.data.decode() if btn.data else None
                                if btn_data == (
                                    data if isinstance(data, str) else data.decode()
                                ):
                                    matched = m
                            elif (
                                text is not None
                                and hasattr(btn, "text")
                                and btn.text == text
                            ):
                                matched = m
                        if matched:
                            break
                    if matched:
                        break
                if matched is None:
                    raise
                message = matched
                old_messages = fresh_messages
                old_snapshots = {
                    m.id: (m.text, m.edit_date, m.reply_markup) for m in old_messages
                }
                max_old_id = max(m.id for m in old_messages) if old_messages else 0

        # Poll for changes
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.5
        clicked_id = message.id
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 2.0)
            new_messages = await _guarded_call(
                self._client.get_messages, self._bot, limit=5
            )

            # Priority 1: edit of the CLICKED message (most reliable)
            for m in new_messages:
                if m.id == clicked_id and m.id in old_snapshots:
                    old_text, old_edit_date, old_markup = old_snapshots[m.id]
                    if (
                        m.text != old_text
                        or m.edit_date != old_edit_date
                        or _markup_signature(m.reply_markup)
                        != _markup_signature(old_markup)
                    ):
                        return m

            # Priority 2: edit of any other known message
            for m in new_messages:
                if m.id in old_snapshots and m.id != clicked_id:
                    old_text, old_edit_date, old_markup = old_snapshots[m.id]
                    if (
                        m.text != old_text
                        or m.edit_date != old_edit_date
                        or _markup_signature(m.reply_markup)
                        != _markup_signature(old_markup)
                    ):
                        return m

            # Priority 3: new message (fallback for .answer() handlers)
            new_msgs = [m for m in new_messages if m.id > max_old_id]
            if new_msgs:
                with_kb = [
                    m
                    for m in new_msgs
                    if m.reply_markup and hasattr(m.reply_markup, "rows")
                ]
                return with_kb[0] if with_kb else new_msgs[0]

        raise TimeoutError(
            f"No response from bot within {timeout}s after clicking button"
        )

    async def send_text_in_fsm(self, text: str, timeout: float = 15) -> Message:
        """Send text in an FSM dialog and get the next prompt/confirmation."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _guarded_call(conv.send_message, text)
            return await _guarded_call(conv.get_response)

    async def fsm_dialog(self, steps: list[str], timeout: float = 15) -> list[Message]:
        """Run an FSM dialog: send a series of messages, collect all responses."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            responses = []
            for step in steps:
                await _guarded_call(conv.send_message, step)
                responses.append(await _guarded_call(conv.get_response))
            return responses

    async def snapshot_last_message_id(self) -> int:
        """Capture the current last message id for later use with wait_for_message_after."""
        messages = await _guarded_call(self._client.get_messages, self._bot, limit=1)
        return max((m.id for m in messages), default=0)

    async def wait_for_message_after(
        self, after_id: int, timeout: float = 30
    ) -> Message:
        """Wait for a message with id > after_id.

        Use with snapshot_last_message_id() taken BEFORE the action that triggers
        the expected message, to avoid race conditions.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.5
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 2.0)
            new_messages = await _guarded_call(
                self._client.get_messages, self._bot, limit=5
            )
            for m in new_messages:
                if m.id > after_id:
                    return m
        raise asyncio.TimeoutError(
            f"No new message from bot within {timeout}s (after_id={after_id})"
        )

    async def wait_for_message(self, timeout: float = 30) -> Message:
        """Wait for an incoming message from the bot (for notifications/triggers).

        Uses polling: remembers the latest message id, then polls until a new one appears.
        """
        old_messages = await _guarded_call(
            self._client.get_messages, self._bot, limit=1
        )
        max_old_id = max((m.id for m in old_messages), default=0)
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.5
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 2.0)
            new_messages = await _guarded_call(
                self._client.get_messages, self._bot, limit=3
            )
            for m in new_messages:
                if m.id > max_old_id:
                    return m
        raise asyncio.TimeoutError(f"No new message from bot within {timeout}s")

    async def press_callback(
        self,
        callback_data: str,
        button_text: str = "→",
        timeout: float = 15,
    ) -> Message:
        """Trigger an arbitrary callback_data by sending a bot message with an inline button.

        Steps:
        1. Bot API sends a message to the user with an inline button carrying callback_data
        2. Telethon clicks that button
        3. Bot handles the callback and edits/sends a response

        Useful for triggering callbacks not reachable via menu navigation (e.g. my_surveys).
        """
        import os

        import httpx

        # Step 1: Send message with inline button via Bot API
        me = await _guarded_call(self._client.get_me)
        token = os.environ["BOT_TOKEN"]
        keyboard = {
            "inline_keyboard": [[{"text": button_text, "callback_data": callback_data}]]
        }
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": me.id,
                    "text": "⏳",
                    "reply_markup": keyboard,
                },
            )
            resp.raise_for_status()

        # Step 2: Wait for the message to appear and click the button
        await asyncio.sleep(1)
        messages = await _guarded_call(self._client.get_messages, self._bot, limit=3)
        target = None
        for m in messages:
            if m.reply_markup and hasattr(m.reply_markup, "rows"):
                for row in m.reply_markup.rows:
                    for btn in row.buttons:
                        if btn.data and btn.data.decode() == callback_data:
                            target = m
                            break
            if target:
                break

        if target is None:
            raise ValueError(
                f"Could not find bot message with button '{callback_data}'"
            )

        return await self.click_button(target, text=button_text, timeout=timeout)

    async def get_last_messages(self, limit: int = 5) -> list[Message]:
        """Get last messages from the bot chat."""
        return await _guarded_call(self._client.get_messages, self._bot, limit=limit)

    async def drain_messages(self, settle_time: float = 1.5) -> None:
        """Wait for pending messages to arrive, then discard them.

        Useful after multi-step flows (e.g. create_meeting) where Telethon
        may have stale messages queued that interfere with the next command.
        """
        await asyncio.sleep(settle_time)
        await _guarded_call(self._client.get_messages, self._bot, limit=10)

    @property
    def raw(self) -> TelegramClient:
        return self._client
