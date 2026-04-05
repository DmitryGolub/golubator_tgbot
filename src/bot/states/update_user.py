from aiogram.fsm.state import StatesGroup, State


class UpdateUserFSM(StatesGroup):
    choosing_user = State()  # Step 1: choose WHO to edit
    viewing_user = State()  # Step 2: show info + param buttons
    choosing_cohort_type = State()  # Step 2.5: choose cohort type (only for COHORT)
    choosing_value = State()  # Step 3: choose new value
