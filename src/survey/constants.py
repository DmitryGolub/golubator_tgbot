import enum


class DurationOption(str, enum.Enum):
    lt_30 = "lt_30"
    between_30_45 = "30_45"
    between_45_60 = "45_60"
    gt_60 = "gt_60"


DURATION_OPTION_LABELS: dict[DurationOption, str] = {
    DurationOption.lt_30: "<30 минут",
    DurationOption.between_30_45: "30-45 минут",
    DurationOption.between_45_60: "45-60 минут",
    DurationOption.gt_60: ">60 минут",
}
