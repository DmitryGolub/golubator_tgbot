import enum


class MentorFeedbackStatus(str, enum.Enum):
    not_ready = "not_ready"
    bad = "bad"
    ok = "ok"
    great = "great"


class MentorFeedbackDuration(str, enum.Enum):
    lt_30 = "lt_30"
    min_30_60 = "min_30_60"
    min_60_90 = "min_60_90"
    ge_90 = "ge_90"


MENTOR_FEEDBACK_STATUS_SQL = ", ".join(
    f"'{value.value}'" for value in MentorFeedbackStatus
)
MENTOR_FEEDBACK_DURATION_SQL = ", ".join(
    f"'{value.value}'" for value in MentorFeedbackDuration
)
