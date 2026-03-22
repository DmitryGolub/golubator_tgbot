from abc import ABC, abstractmethod

from src.models.trigger import TriggerRule


class BaseAction(ABC):
    @abstractmethod
    async def execute(
        self,
        *,
        rule: TriggerRule,
        recipient_id: int,
        context: dict,
        bot,
    ) -> None:
        pass
