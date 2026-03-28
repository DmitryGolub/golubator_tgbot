from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models.trigger import ActionType, DelayMode, TriggerType
from src.services.events.dispatcher import EventDispatcher


class TestBuildEventKey:
    def test_meeting_created(self):
        rule = SimpleNamespace(id=1, trigger_type=TriggerType.meeting_created)
        key = EventDispatcher._build_event_key(rule, {"meeting_id": 42})
        assert key == "meeting_created:42:1"

    def test_call_ended(self):
        rule = SimpleNamespace(id=2, trigger_type=TriggerType.call_ended)
        key = EventDispatcher._build_event_key(rule, {"meeting_id": 10})
        assert key == "call_ended:10:2"

    def test_periodic_cron(self):
        rule = SimpleNamespace(id=3, trigger_type=TriggerType.periodic_cron)
        key = EventDispatcher._build_event_key(rule, {})
        now_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        assert key == f"periodic:{now_key}:3"

    def test_manual_returns_none(self):
        rule = SimpleNamespace(id=4, trigger_type=TriggerType.manual)
        assert EventDispatcher._build_event_key(rule, {}) is None

    def test_unknown_type(self):
        rule = SimpleNamespace(id=5, trigger_type=TriggerType.user_state_changed)
        key = EventDispatcher._build_event_key(rule, {})
        assert key == "user_state_changed:5"


class TestCalculateEta:
    def test_after_trigger(self):
        rule = SimpleNamespace(
            delay_seconds=60,
            delay_mode=DelayMode.after_trigger,
        )
        before = datetime.now(timezone.utc)
        eta = EventDispatcher._calculate_eta(rule, {})
        after = datetime.now(timezone.utc)
        assert before + timedelta(seconds=60) <= eta <= after + timedelta(seconds=60)

    def test_before_scheduled(self):
        scheduled = datetime.now(timezone.utc) + timedelta(hours=1)
        rule = SimpleNamespace(
            delay_seconds=300,
            delay_mode=DelayMode.before_scheduled,
        )
        ctx = {"scheduled_at": scheduled.isoformat()}
        eta = EventDispatcher._calculate_eta(rule, ctx)
        expected = scheduled - timedelta(seconds=300)
        assert abs((eta - expected).total_seconds()) < 2

    def test_before_scheduled_past_returns_now(self):
        scheduled = datetime.now(timezone.utc) - timedelta(hours=1)
        rule = SimpleNamespace(
            delay_seconds=300,
            delay_mode=DelayMode.before_scheduled,
        )
        ctx = {"scheduled_at": scheduled.isoformat()}
        before = datetime.now(timezone.utc)
        eta = EventDispatcher._calculate_eta(rule, ctx)
        assert eta >= before - timedelta(seconds=1)

    def test_before_scheduled_no_scheduled_at_falls_back(self):
        rule = SimpleNamespace(
            delay_seconds=60,
            delay_mode=DelayMode.before_scheduled,
        )
        before = datetime.now(timezone.utc)
        eta = EventDispatcher._calculate_eta(rule, {})
        assert eta >= before + timedelta(seconds=59)


@patch("src.services.events.dispatcher.TriggerRuleDAO")
class TestEmit:
    async def test_no_rules_returns_early(self, mock_dao):
        mock_dao.get_active_by_trigger = AsyncMock(return_value=[])
        await EventDispatcher.emit(TriggerType.manual, {})
        mock_dao.get_active_by_trigger.assert_called_once()

    @patch("src.services.events.dispatcher.RecipientResolver")
    @patch("src.services.events.dispatcher.TriggerExecutionDAO")
    async def test_immediate_skips_existed(
        self, mock_exec_dao, mock_resolver, mock_rule_dao
    ):
        rule = SimpleNamespace(
            id=1,
            trigger_type=TriggerType.manual,
            delay_seconds=0,
            action_type=ActionType.send_notification,
            action_config={"text": "hi"},
        )
        mock_rule_dao.get_active_by_trigger = AsyncMock(return_value=[rule])
        mock_resolver.resolve = AsyncMock(return_value=[100])
        execution = SimpleNamespace(id=1)
        mock_exec_dao.create = AsyncMock(return_value=(execution, True))

        await EventDispatcher.emit(TriggerType.manual, {})
        mock_exec_dao.mark_sent.assert_not_called()


@patch("src.services.events.dispatcher.ACTION_MAP", {})
class TestExecuteAction:
    async def test_unknown_action_type(self):
        rule = SimpleNamespace(action_type="unknown_type")
        with pytest.raises(ValueError, match="Unknown action_type"):
            await EventDispatcher.execute_action(rule, 100, {}, None)
