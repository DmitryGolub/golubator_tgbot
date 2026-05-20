"""CalDAV calendar connection flow for mentors."""

from __future__ import annotations

import logging
from datetime import timezone

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.caldav import caldav_cancel_keyboard, caldav_status_keyboard
from src.bot.keyboards.menu import menu_keyboard
from src.bot.states.caldav import CalDAVSetupFSM
from src.bot.utils import safe_edit_text
from src.core.config import settings
from src.dao.caldav_account import CalDAVAccountDAO
from src.dao.mentor import MentorDAO
from src.services.auth import AuthService
from src.services.encryption import encrypt
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="caldav")


async def _menu_kb(user_id: int):
    perms = await AuthService.get_user_permissions(user_id)
    return await menu_keyboard(perms)


async def _is_mentor(user_id: int) -> bool:
    mentor = await MentorDAO.find_by_telegram_id(user_id)
    return mentor is not None


def _format_status(account) -> str:
    if account is None:
        return (
            "📅 <b>Синхронизация календаря</b>\n\n"
            "Созвоны автоматически появятся в твоём iCloud или Yandex-календаре.\n"
            "Нажми «Подключить», чтобы начать."
        )
    status = "включена" if account.sync_enabled else "отключена"
    calendar = (
        e(account.calendar_display_name) if account.calendar_display_name else "—"
    )
    verified_at = (
        account.last_verified_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if account.last_verified_at
        else "никогда"
    )
    error = (
        f"\n⚠️ Последняя ошибка: <i>{e(account.last_error)}</i>"
        if account.last_error
        else ""
    )
    return (
        "📅 <b>Синхронизация календаря</b>\n\n"
        f"Сервер: <code>{e(account.base_url)}</code>\n"
        f"Логин: <code>{e(account.username)}</code>\n"
        f"Календарь: <b>{calendar}</b>\n"
        f"Синхронизация: <b>{status}</b>\n"
        f"Последняя проверка: {verified_at}{error}"
    )


async def _show_status(
    user_id: int,
    reply_func,
) -> None:
    account = await CalDAVAccountDAO.get_for_mentor(user_id)
    await reply_func(
        _format_status(account),
        reply_markup=caldav_status_keyboard(
            has_account=account is not None,
            sync_enabled=bool(account and account.sync_enabled),
        ),
    )


@router.message(Command("calendar"))
async def cmd_calendar(message: Message) -> None:
    if not settings.CALDAV_ENABLED:
        await message.answer("📅 Синхронизация календаря сейчас отключена.")
        return
    if not await _is_mentor(message.from_user.id):
        await message.answer(
            "Эта функция доступна только менторам.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return
    await _show_status(message.from_user.id, message.answer)


@router.callback_query(F.data == "menu_calendar")
async def cb_calendar_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if not settings.CALDAV_ENABLED:
        await safe_edit_text(
            callback,
            "📅 Синхронизация календаря сейчас отключена.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return
    if not await _is_mentor(callback.from_user.id):
        await safe_edit_text(
            callback,
            "Эта функция доступна только менторам.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return
    await _show_status(
        callback.from_user.id,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
    )


@router.callback_query(F.data == "caldav_connect")
async def cb_connect(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not settings.CALDAV_ENABLED:
        return
    if not await _is_mentor(callback.from_user.id):
        return
    await state.set_state(CalDAVSetupFSM.entering_base_url)
    await safe_edit_text(
        callback,
        (
            "Введи URL CalDAV-сервера.\n\n"
            "Примеры:\n"
            "• <code>https://caldav.icloud.com</code>\n"
            "• <code>https://caldav.yandex.ru</code>"
        ),
        reply_markup=caldav_cancel_keyboard(),
    )


@router.callback_query(F.data == "caldav_verify")
async def cb_verify(callback: CallbackQuery) -> None:
    await callback.answer()
    if not settings.CALDAV_ENABLED:
        return
    account = await CalDAVAccountDAO.get_for_mentor(callback.from_user.id)
    if account is None:
        await safe_edit_text(
            callback,
            "Нет подключённого аккаунта.",
            reply_markup=caldav_status_keyboard(has_account=False, sync_enabled=False),
        )
        return
    from src.tasks.caldav import verify_account

    verify_account.delay(account.id)
    await safe_edit_text(
        callback,
        "⏳ Проверяем подключение… Результат придёт отдельным сообщением.",
        reply_markup=caldav_status_keyboard(
            has_account=True, sync_enabled=account.sync_enabled
        ),
    )


@router.callback_query(F.data == "caldav_disable")
async def cb_disable(callback: CallbackQuery) -> None:
    await callback.answer()
    if not settings.CALDAV_ENABLED:
        return
    account = await CalDAVAccountDAO.get_for_mentor(callback.from_user.id)
    if account is None:
        return
    await CalDAVAccountDAO.set_sync_enabled(account.id, False)
    await _show_status(
        callback.from_user.id,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
    )


@router.callback_query(F.data == "caldav_enable")
async def cb_enable(callback: CallbackQuery) -> None:
    await callback.answer()
    if not settings.CALDAV_ENABLED:
        return
    account = await CalDAVAccountDAO.get_for_mentor(callback.from_user.id)
    if account is None:
        return
    await CalDAVAccountDAO.set_sync_enabled(account.id, True)
    await _show_status(
        callback.from_user.id,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
    )


@router.callback_query(
    StateFilter(
        CalDAVSetupFSM.entering_base_url,
        CalDAVSetupFSM.entering_username,
        CalDAVSetupFSM.entering_password,
    ),
    F.data == "caldav_cancel",
)
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_status(
        callback.from_user.id,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
    )


@router.message(StateFilter(CalDAVSetupFSM.entering_base_url))
async def msg_base_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not url.lower().startswith("https://"):
        await message.answer(
            "URL должен начинаться с <code>https://</code>. Попробуй ещё раз.",
            reply_markup=caldav_cancel_keyboard(),
        )
        return
    await state.update_data(base_url=url)
    await state.set_state(CalDAVSetupFSM.entering_username)
    await message.answer(
        "Введи логин (email для iCloud, имя пользователя для Yandex):",
        reply_markup=caldav_cancel_keyboard(),
    )


@router.message(StateFilter(CalDAVSetupFSM.entering_username))
async def msg_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(
            "Логин не может быть пустым.",
            reply_markup=caldav_cancel_keyboard(),
        )
        return
    await state.update_data(username=username)
    await state.set_state(CalDAVSetupFSM.entering_password)
    await message.answer(
        (
            "Введи <b>пароль приложения</b> (не основной пароль).\n\n"
            "🍎 iCloud: appleid.apple.com → Sign-In and Security → App-Specific "
            "Passwords.\n"
            "🟡 Yandex: id.yandex.ru/security/app-passwords → CalDAV.\n\n"
            "Сообщение с паролем будет удалено сразу после получения."
        ),
        reply_markup=caldav_cancel_keyboard(),
    )


@router.message(StateFilter(CalDAVSetupFSM.entering_password))
async def msg_password(message: Message, state: FSMContext) -> None:
    password = message.text or ""
    # Delete the password message ASAP — we never want it to linger in chat.
    try:
        await message.delete()
    except Exception:
        logger.exception("caldav: failed to delete password message")

    data = await state.get_data()
    base_url = data.get("base_url")
    username = data.get("username")
    if not base_url or not username or not password.strip():
        await state.clear()
        await message.answer(
            "Что-то пошло не так. Попробуй подключить календарь заново.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return

    try:
        encrypted = encrypt(password)
    except Exception:
        logger.exception("caldav: failed to encrypt password")
        await state.clear()
        await message.answer(
            "Не удалось зашифровать пароль. Проверьте конфигурацию сервера.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return
    finally:
        password = "•" * 8  # overwrite local binding

    account = await CalDAVAccountDAO.upsert(
        telegram_id=message.from_user.id,
        base_url=base_url,
        username=username,
        encrypted_password=encrypted,
    )
    await state.clear()

    await message.answer(
        "Пароль получен: <code>••••••••</code>\n⏳ Проверяем подключение…",
    )

    from src.tasks.caldav import verify_account

    verify_account.delay(account.id)
