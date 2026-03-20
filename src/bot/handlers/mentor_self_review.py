from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.role import RoleFilter
from src.bot.states.mentor_self_review import MentorSelfReviewFSM
from src.dao.mentor_self_review import MentorSelfReviewDAO
from src.models.user import Role

router = Router(name="mentor-self-review")
router.message.filter(RoleFilter([Role.mentor]))
router.callback_query.filter(RoleFilter([Role.mentor]))


def _current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _period_from_callback(data: str) -> str | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None
    period = parts[3]
    if len(period) != 7:
        return None
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        return None
    return period


def _rating_keyboard(prefix: str, min_value: int, max_value: int, period: str):
    kb = InlineKeyboardBuilder()
    for value in range(min_value, max_value + 1):
        kb.button(text=str(value), callback_data=f"mentor_self_review:{prefix}:{value}:{period}")
    kb.adjust(5)
    return kb.as_markup()


async def _already_submitted_message(message: Message, period: str) -> None:
    await message.answer(f"Самооценка за период <b>{period}</b> уже заполнена.")


@router.callback_query(F.data.startswith("mentor_self_review:start:"))
async def cb_start_self_review(callback: CallbackQuery, state: FSMContext):
    period = _period_from_callback(callback.data)
    if not period:
        await callback.answer("Некорректный период", show_alert=True)
        return

    if await MentorSelfReviewDAO.exists_for_period(callback.from_user.id, period):
        await callback.answer("Уже заполнено", show_alert=True)
        await callback.message.answer(
            f"Самооценка за период <b>{period}</b> уже заполнена."
        )
        await state.clear()
        return

    await state.clear()
    await state.update_data(period=period)
    await state.set_state(MentorSelfReviewFSM.waiting_workload)

    await callback.answer()
    await callback.message.answer(
        "Ежемесячная самооценка ментора\n\n"
        "1) Оцените вашу загрузку (1-5):",
        reply_markup=_rating_keyboard("workload", 1, 5, period),
    )


@router.message(Command("self_review"))
async def cmd_self_review(message: Message, state: FSMContext):
    period = _current_period()

    if await MentorSelfReviewDAO.exists_for_period(message.from_user.id, period):
        await _already_submitted_message(message, period)
        await state.clear()
        return

    await state.clear()
    await state.update_data(period=period)
    await state.set_state(MentorSelfReviewFSM.waiting_workload)

    await message.answer(
        "Ежемесячная самооценка ментора\n\n"
        "1) Оцените вашу загрузку (1-5):",
        reply_markup=_rating_keyboard("workload", 1, 5, period),
    )


@router.callback_query(MentorSelfReviewFSM.waiting_workload, F.data.startswith("mentor_self_review:workload:"))
async def cb_choose_workload(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    period = data.get("period")
    if not period:
        await callback.answer("Сессия истекла", show_alert=True)
        await state.clear()
        return

    if await MentorSelfReviewDAO.exists_for_period(callback.from_user.id, period):
        await callback.answer("Уже заполнено", show_alert=True)
        await callback.message.answer(f"Самооценка за период <b>{period}</b> уже заполнена.")
        await state.clear()
        return

    value = int(callback.data.split(":")[2])
    await state.update_data(workload=value)
    await state.set_state(MentorSelfReviewFSM.waiting_pigeon_stupidity)

    await callback.answer()
    await callback.message.answer(
        "2) Насколько вас раздражает "
        "\"тупость голубя\" в задачах (1-5):",
        reply_markup=_rating_keyboard("pigeon", 1, 5, period),
    )


@router.callback_query(MentorSelfReviewFSM.waiting_pigeon_stupidity, F.data.startswith("mentor_self_review:pigeon:"))
async def cb_choose_pigeon_stupidity(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    period = data.get("period")
    if not period:
        await callback.answer("Сессия истекла", show_alert=True)
        await state.clear()
        return

    if await MentorSelfReviewDAO.exists_for_period(callback.from_user.id, period):
        await callback.answer("Уже заполнено", show_alert=True)
        await callback.message.answer(f"Самооценка за период <b>{period}</b> уже заполнена.")
        await state.clear()
        return

    value = int(callback.data.split(":")[2])
    await state.update_data(pigeon_stupidity=value)
    await state.set_state(MentorSelfReviewFSM.waiting_avg_neuromutation)

    await callback.answer()
    await callback.message.answer(
        "3) Оцените среднюю нейромутацию (1-10):",
        reply_markup=_rating_keyboard("neuromutation", 1, 10, period),
    )


@router.callback_query(MentorSelfReviewFSM.waiting_avg_neuromutation, F.data.startswith("mentor_self_review:neuromutation:"))
async def cb_choose_avg_neuromutation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    period = data.get("period")
    if not period:
        await callback.answer("Сессия истекла", show_alert=True)
        await state.clear()
        return

    if await MentorSelfReviewDAO.exists_for_period(callback.from_user.id, period):
        await callback.answer("Уже заполнено", show_alert=True)
        await callback.message.answer(f"Самооценка за период <b>{period}</b> уже заполнена.")
        await state.clear()
        return

    value = int(callback.data.split(":")[2])
    await state.update_data(avg_neuromutation=value)
    await state.set_state(MentorSelfReviewFSM.waiting_comment)

    await callback.answer()
    await callback.message.answer(
        "4) Добавьте комментарий или отправьте '-' без комментария."
    )


@router.message(MentorSelfReviewFSM.waiting_comment)
async def msg_comment_and_save(message: Message, state: FSMContext):
    data = await state.get_data()
    period = data.get("period")
    workload = data.get("workload")
    pigeon_stupidity = data.get("pigeon_stupidity")
    avg_neuromutation = data.get("avg_neuromutation")

    if not period or workload is None or pigeon_stupidity is None or avg_neuromutation is None:
        await state.clear()
        await message.answer("Сессия заполнения не найдена. Начните заново командой /self_review")
        return

    comment = (message.text or "").strip()
    if comment in {"", "-"}:
        comment = None

    _, already_submitted = await MentorSelfReviewDAO.submit_review(
        mentor_id=message.from_user.id,
        workload=workload,
        pigeon_stupidity=pigeon_stupidity,
        avg_neuromutation=avg_neuromutation,
        comment=comment,
        period=period,
    )
    await state.clear()

    if already_submitted:
        await _already_submitted_message(message, period)
        return

    await message.answer(
        "Спасибо! Самооценка сохранена.\n"
        f"Период: <b>{period}</b>."
    )
