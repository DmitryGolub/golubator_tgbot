from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramAPIError

from src.services.invite_link import LINK_UNAVAILABLE, InviteLinkService


async def test_generate_links_mentor_with_channel():
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = MagicMock(
        invite_link="https://t.me/+abc123"
    )

    mentor = MagicMock(channel_id=-1001234567890)
    mentee = MagicMock(mentor=mentor)

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=-1009999999999,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=mentee,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == "https://t.me/+abc123"
    assert result["mentor_channel_link"] == "https://t.me/+abc123"
    assert bot.create_chat_invite_link.call_count == 2


async def test_generate_links_mentor_without_channel():
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = MagicMock(
        invite_link="https://t.me/+general"
    )

    mentor = MagicMock(channel_id=None)
    mentee = MagicMock(mentor=mentor)

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=-1009999999999,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=mentee,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == "https://t.me/+general"
    assert result["mentor_channel_link"] == LINK_UNAVAILABLE
    assert bot.create_chat_invite_link.call_count == 1


async def test_generate_links_mentee_without_mentor():
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = MagicMock(
        invite_link="https://t.me/+general"
    )

    mentee = MagicMock(mentor=None)

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=-1009999999999,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=mentee,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == "https://t.me/+general"
    assert result["mentor_channel_link"] == LINK_UNAVAILABLE


async def test_generate_links_mentee_not_found():
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = MagicMock(
        invite_link="https://t.me/+general"
    )

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=-1009999999999,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == "https://t.me/+general"
    assert result["mentor_channel_link"] == LINK_UNAVAILABLE


async def test_generate_links_api_error_fallback():
    bot = AsyncMock()
    bot.create_chat_invite_link.side_effect = TelegramAPIError(
        method=MagicMock(), message="Bot is not a member"
    )

    mentor = MagicMock(channel_id=-1001234567890)
    mentee = MagicMock(mentor=mentor)

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=-1009999999999,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=mentee,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == LINK_UNAVAILABLE
    assert result["mentor_channel_link"] == LINK_UNAVAILABLE


async def test_generate_links_no_general_chat_id():
    bot = AsyncMock()

    with (
        patch(
            "src.services.invite_link.settings",
            GENERAL_CHAT_ID=None,
        ),
        patch(
            "src.services.invite_link.MenteeDAO.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await InviteLinkService.generate_links_for_mentee(bot, 12345)

    assert result["general_chat_link"] == LINK_UNAVAILABLE
    assert result["mentor_channel_link"] == LINK_UNAVAILABLE
    bot.create_chat_invite_link.assert_not_called()
