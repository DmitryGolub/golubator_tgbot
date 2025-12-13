from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.filters.role import RoleFilter
from src.bot.keyboards.cohort import cohort_cancel_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.states.create_cohort import CreateCohortFSM
from src.dao.cohort import CohortDAO
from src.models.user import Role


router = Router(name="cohort-create")
router.message.filter(RoleFilter([Role.admin]))
router.callback_query.filter(RoleFilter([Role.admin]))


@router.callback_query(F.data == "cohort_create")
async def start_create_cohort(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateCohortFSM.waiting_name)
    await callback.answer()
    await callback.message.edit_text(
        "Введите название когорты:",
        reply_markup=cohort_cancel_keyboard(),
    )


@router.message(StateFilter(CreateCohortFSM.waiting_name))
async def process_cohort_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""

    if not name:
        await message.answer(
            "Название не может быть пустым. Введите название или отмените.",
            reply_markup=cohort_cancel_keyboard(),
        )
        return

    cohort = await CohortDAO.add(name=name)
    await state.clear()

    await message.answer(
        f'Когорта "{cohort.name}" успешно создана.',
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "cohort_create_cancel")
async def cancel_create_cohort(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Создание когорты отменено.",
        reply_markup=back_to_menu_keyboard(),
    )

