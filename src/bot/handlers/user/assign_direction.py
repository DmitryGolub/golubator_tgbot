from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

from src.bot.callbacks.direction import SaveDirectionsCB, ToggleDirectionCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.direction import direction_cohorts_keyboard
from src.dao.cohort import CohortDAO
from src.services.ui_text import UiTextService

router = Router(name="assign_direction")
router.callback_query.filter(PermissionFilter("view_direction_students"))


class AssignDirectionFSM(StatesGroup):
    choosing = State()


@router.callback_query(F.data == "lead_direction_students")
async def cb_start_direction(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cohorts = await CohortDAO.get_cohorts_by_type("Category")
    if not cohorts:
        text = await UiTextService.get("direction.no_categories")
        await callback.message.edit_text(text)
        return

    user_cohorts = await CohortDAO.get_user_cohorts(callback.from_user.id)
    selected = {uc.cohort_id for uc in user_cohorts}
    cohort_ids = {c.id for c in cohorts}
    selected &= cohort_ids

    await state.set_state(AssignDirectionFSM.choosing)
    await state.update_data(
        selected=list(selected),
        cohort_cache={c.id: c.value for c in cohorts},
    )

    text = await UiTextService.get("direction.choose_cohorts")
    await callback.message.edit_text(
        text,
        reply_markup=direction_cohorts_keyboard(cohorts, selected),
    )


@router.callback_query(AssignDirectionFSM.choosing, ToggleDirectionCB.filter())
async def cb_toggle_direction(
    callback: CallbackQuery, callback_data: ToggleDirectionCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    selected = set(data.get("selected", []))
    cid = callback_data.cohort_id

    if cid in selected:
        selected.discard(cid)
    else:
        selected.add(cid)

    await state.update_data(selected=list(selected))

    cohorts = await CohortDAO.get_cohorts_by_type("Category")
    await callback.message.edit_reply_markup(
        reply_markup=direction_cohorts_keyboard(cohorts, selected),
    )


@router.callback_query(AssignDirectionFSM.choosing, SaveDirectionsCB.filter())
async def cb_save_directions(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    selected = set(data.get("selected", []))
    cohort_cache = data.get("cohort_cache", {})

    memberships = [
        ("Category", cohort_cache[cid]) for cid in selected if cid in cohort_cache
    ]

    await CohortDAO.replace_user_cohorts(callback.from_user.id, memberships)
    await state.clear()

    text = await UiTextService.get("direction.saved")
    await callback.message.edit_text(text)
